"""Stripe Webhookの署名検証・イベント種別ディスパッチ
(stripe-webhook-signature-verification-design.md フェーズ93、
stripe-webhook-event-dispatch-design.md フェーズ94)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジック・イベント種別ディスパッチロジックを切り出したモジュール。
`cloud_function_webhook.py`(LINE側)とは独立した別ファイルとし、既存のLINE側コードには
一切影響を与えない。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from application_form_submission_flow import (
    InMemoryUserProfileStore,
    UserProfileStoreProtocol,
)
from cloud_function_webhook import InMemoryUsageCounter, PortalLinkProvider
from deletion_candidate import (
    InMemoryProfileDeletionCandidateStore,
    ProfileDeletionCandidateStoreProtocol,
    clear_deletion_candidate_on_subscription_reactivated,
    mark_deletion_candidate_on_subscription_deleted,
)
from payment_recovery_notification import (
    OUTCOME_SEND_FAILED,
    handle_payment_failure_detected,
    handle_payment_succeeded,
)
from trial_end_scheduler import LinePushClient


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """`Stripe-Signature`ヘッダを検証する(design 2節のアルゴリズムどおり)。

    - `sig_header`が無い/空文字列、または`t`・`v1`を含まない不正な形式なら`False`。
    - `v1`が複数含まれる場合(シークレットローテーション中)、いずれか1つでも一致すれば
      検証成功とする。`v0`(旧方式)は一切参照しない。
    - 署名が一致してもタイムスタンプが`tolerance_seconds`(デフォルト300秒)の許容範囲外
      なら`False`とする(リプレイ攻撃対策)。
    """
    if not sig_header:
        return False

    timestamp: Optional[str] = None
    v1_signatures: list[str] = []
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t":
            timestamp = value
        elif key == "v1":
            v1_signatures.append(value)

    if timestamp is None or not v1_signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()

    signature_matches = any(
        hmac.compare_digest(expected, candidate) for candidate in v1_signatures
    )
    if not signature_matches:
        return False

    resolved_now = now if now is not None else time.time()
    if abs(resolved_now - timestamp_int) > tolerance_seconds:
        return False

    return True


_HANDLED_EVENT_TYPES = frozenset(
    {
        "customer.subscription.deleted",
        "customer.subscription.created",
        "customer.subscription.updated",
        "invoice.payment_failed",
        "invoice.payment_succeeded",
    }
)

_REACTIVATED_STATUSES = frozenset({"active", "trialing"})


@dataclass
class StripeDispatchResult:
    """stripe-webhook-event-dispatch-design.md 2節。"""

    marked_user_ids: list = field(default_factory=list)
    cleared_user_ids: list = field(default_factory=list)
    ignored_types: list = field(default_factory=list)
    unresolved_customers: list = field(default_factory=list)
    invalid_events: list = field(default_factory=list)
    # payment-failure-dunning-design.md(フェーズ117)6節対応、フェーズ119で追加。
    payment_failure_detected_user_ids: list = field(default_factory=list)
    payment_recovered_user_ids: list = field(default_factory=list)
    # フェーズ122追加: push_client指定時、決済成功復旧通知の送信に失敗したuser_id
    # (状態は書き込まれておらず、Webhookリトライでの再試行に委ねる想定)。
    payment_recovery_notification_failed_user_ids: list = field(default_factory=list)
    # フェーズ124追加: push_client指定時、決済失敗検知時(段階1)通知の送信に失敗したuser_id
    # (状態は書き込まれておらず、Webhookリトライでの再試行に委ねる想定)。
    payment_failure_detection_notification_failed_user_ids: list = field(
        default_factory=list
    )


class PaymentFailureUsageCounterProtocol(Protocol):
    """`UsageCounterProtocol`(cloud_function_webhook.py)のうち、`invoice.payment_failed`/
    `invoice.payment_succeeded`受信時に必要な2メソッドのみを切り出した薄いインターフェース。
    `UpgradedAtWriterProtocol`と同じ理由(このファイル冒頭の位置づけ説明どおり構造的部分型付けで
    独立性を保つ)で新設した。"""

    def set_payment_failure_detected_at(self, user_id: str, detected_at: datetime) -> None:
        ...

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        ...

    def clear_payment_failure_detected_at(self, user_id: str) -> None:
        ...

    def clear_payment_failure_reminder_sent_at(self, user_id: str) -> None:
        """payment-failure-reminder-scheduler-design.md 3節(フェーズ120で追加)。
        リマインド送信済みフラグも決済成功と同時に消去し、再度の決済失敗時に
        リマインドが送信されなくなる不具合を防ぐ。"""
        ...


def dispatch_stripe_event(
    event: dict,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    usage_counter: Optional[PaymentFailureUsageCounterProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    now: Optional[datetime] = None,
) -> StripeDispatchResult:
    """stripe-webhook-event-dispatch-design.md 1節のとおり、Stripe Webhookイベント1件を
    種別に応じて`prototype/deletion_candidate.py`の関数へ振り分ける。

    `usage_counter`はpayment-failure-dunning-design.md(フェーズ117)6節対応
    (フェーズ119で追加)。`invoice.payment_failed`/`invoice.payment_succeeded`受信時のみ
    参照し、未指定(`None`)の場合はこれら2種別を`ignored_types`として扱う(既存の
    `customer.subscription.*`専用の呼び出し経路に影響を与えないための後方互換措置、
    aircon-pashaのstripe_dispatch.py`payment_store`引数と同じ方針)。

    `push_client`はpayment-failure-dunning-design.md 6節「Stripe側の実際のイベント受信
    配線」対応(フェーズ122で追加)。指定時、`invoice.payment_succeeded`受信時に
    `payment_recovery_notification.handle_payment_succeeded()`経由で実際に通知を送信して
    から状態をクリアする。未指定(`None`)の場合は従来通り状態のクリアのみを行い、
    通知は送信しない(既存呼び出し経路への後方互換措置)。本ventureは
    `payment_recovery_notification.py`が`trial_end_scheduler.py`の
    `LinePushClient`/`LinePushDeliveryError`をそのまま再利用しており、aircon-pashaの
    `payment_failure.py`のようにモジュールごとに別クラスの例外を定義していないため、
    aircon-pashaのフェーズ147時点で先送りされていた「復旧通知側の配線」を本ventureでは
    そのまま行える。

    フェーズ124で`invoice.payment_failed`側も同様に対応した。`push_client`指定時は
    `payment_recovery_notification.handle_payment_failure_detected()`経由で
    決済失敗検知時(段階1)の通知を実際に送信してから状態を書き込む(送信失敗時は状態を
    書き込まずWebhookリトライに委ねる)。未指定時は従来通り通知なしで状態のみ書き込む。

    `portal_link_provider`はフェーズ127で追加。決済失敗検知時通知の文面がStripeカスタマー
    ポータルURLを差し込むよう変わったため(`render_payment_failure_detected_message()`)、
    `cloud_function_webhook.render_payment_suspended_message()`と同じ`PortalLinkProvider`を
    そのまま`handle_payment_failure_detected()`へ受け渡す。未指定(`None`)時は
    `PORTAL_LINK_UNAVAILABLE_FALLBACK`が送られる(既存の安全側デフォルトと同じ)。
    """
    result = StripeDispatchResult()

    event_type = event.get("type")
    if event_type not in _HANDLED_EVENT_TYPES:
        if event_type is not None:
            result.ignored_types.append(event_type)
        return result

    data_object = event.get("data", {}).get("object", {})
    customer = data_object.get("customer")
    user_id = resolve_user_id(customer) if customer is not None else None
    if user_id is None:
        result.unresolved_customers.append(customer)
        return result

    if event_type == "customer.subscription.deleted":
        created = event.get("created")
        if not isinstance(created, (int, float)) or isinstance(created, bool):
            result.invalid_events.append(event_type)
            return result
        event_time = datetime.fromtimestamp(created, tz=timezone.utc)
        mark_deletion_candidate_on_subscription_deleted(store, user_id, event_time)
        result.marked_user_ids.append(user_id)
        return result

    if event_type == "customer.subscription.created":
        clear_deletion_candidate_on_subscription_reactivated(store, user_id)
        result.cleared_user_ids.append(user_id)
        return result

    if event_type == "customer.subscription.updated":
        # active/trialing 以外への変化は対象外(design 1節5.)。
        # 記録すべき異常があるわけではないので、result には何も追加せず終える。
        if data_object.get("status") in _REACTIVATED_STATUSES:
            clear_deletion_candidate_on_subscription_reactivated(store, user_id)
            result.cleared_user_ids.append(user_id)
        return result

    if usage_counter is None:
        result.ignored_types.append(event_type)
        return result

    if event_type == "invoice.payment_failed":
        created = event.get("created")
        if not isinstance(created, (int, float)) or isinstance(created, bool):
            result.invalid_events.append(event_type)
            return result
        event_time = datetime.fromtimestamp(created, tz=timezone.utc)

        if push_client is not None:
            # フェーズ124: 通知の実送信・状態書き込みはhandle_payment_failure_detected()に
            # 委譲する(usage_counterはPaymentFailureUsageCounterProtocol/PaymentFailure
            # DetectionUsageCounterProtocolの両方を構造的に満たす、InMemoryUsageCounterで
            # 確認済み)。
            detection_result = handle_payment_failure_detected(
                user_id,
                usage_counter,  # type: ignore[arg-type]
                push_client,
                event_time,
                portal_link_provider,
            )
            if detection_result.notified:
                result.payment_failure_detected_user_ids.append(user_id)
            else:
                result.payment_failure_detection_notification_failed_user_ids.append(
                    user_id
                )
            return result

        usage_counter.set_payment_failure_detected_at(user_id, event_time)
        result.payment_failure_detected_user_ids.append(user_id)
        return result

    # invoice.payment_succeeded: design 4節「決済成功による復旧時」。
    resolved_now = now if now is not None else datetime.now(timezone.utc)

    if push_client is not None:
        # フェーズ122: 分類・通知・状態クリアはすべてhandle_payment_succeeded()に委譲する
        # (usage_counterはPaymentFailureUsageCounterProtocol/PaymentRecoveryUsageCounter
        # Protocolの両方を構造的に満たす、InMemoryUsageCounterで確認済み)。
        recovery_result = handle_payment_succeeded(
            user_id,
            usage_counter,  # type: ignore[arg-type]
            push_client,
            resolved_now,
        )
        if recovery_result.outcome == OUTCOME_SEND_FAILED:
            result.payment_recovery_notification_failed_user_ids.append(user_id)
        elif recovery_result.state_reset:
            # OUTCOME_RECOVERED_FROM_SUSPENSION・OUTCOME_CONFIRMED_IN_GRACE(通知あり)、
            # OUTCOME_SILENT_RESET(通知なし)のいずれも状態はクリアされるため、
            # push_client未指定時の既存フィールドの意味(状態がクリアされたか)を保つ。
            result.payment_recovered_user_ids.append(user_id)
        return result

    # payment-failure-dunning-design.mdはaircon-pashaと異なり別立ての`payment_suspended_at`を
    # 持たない設計(制限モードは検知時刻+猶予日数から都度算出、フェーズ118)のため、
    # クリア対象は`payment_failure_detected_at`のみでよかったが、フェーズ120で
    # `payment_failure_reminder_sent_at`(送信済みフラグ)を新設したため、これも
    # あわせてクリアする(消去しないと再度の決済失敗時にリマインドが送信されなくなるため、
    # payment-failure-reminder-scheduler-design.md 3節)。push_client未指定時の
    # 後方互換経路(通知なし)としてそのまま残す。
    if usage_counter.get_payment_failure_detected_at(user_id) is not None:
        usage_counter.clear_payment_failure_detected_at(user_id)
        usage_counter.clear_payment_failure_reminder_sent_at(user_id)
        result.payment_recovered_user_ids.append(user_id)

    return result


class UpgradedAtWriterProtocol(Protocol):
    """trial-end-scheduler-design.md 2節: usage_counter側の`upgraded_at`書き込み経路を
    表す最小限のProtocol。`cloud_function_webhook.py`(LINE側)を直接importせず、
    構造的部分型付け(`InMemoryUsageCounter.set_upgraded_at_if_unset()`が同じ
    シグネチャを持つだけで満たされる)によって独立性を保つ
    (このファイル冒頭の位置づけ説明どおり)。"""

    def set_upgraded_at_if_unset(self, user_id: str, upgraded_at: datetime) -> None:
        ...


@dataclass
class CheckoutSessionLinkResult:
    """handle_checkout_session_completed()の結果
    (stripe-customer-id-linking-design.md 3節、trial-end-scheduler-design.md 2節)。"""

    linked: bool
    user_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    upgraded_at_written: bool = False


def handle_checkout_session_completed(
    event: dict,
    store: UserProfileStoreProtocol,
    *,
    usage_counter: Optional[UpgradedAtWriterProtocol] = None,
    now: Optional[datetime] = None,
) -> CheckoutSessionLinkResult:
    """`checkout.session.completed`イベントから`client_reference_id`(=user_id)と
    `customer`(=stripe_customer_id)を取り出し、`store`に紐付けを書き込む
    (stripe-customer-id-linking-design.md 3節)。いずれかが欠落・非文字列・空文字列の
    場合は何も書き込まない(安全側。resolve_user_idが引き続きNoneを返すだけで実害はない)。

    `usage_counter`が渡された場合は、紐付け成功時に`set_upgraded_at_if_unset()`で
    `upgraded_at`も同時に書き込む(trial-end-scheduler-design.md 2節で残っていた
    「有料転換済みユーザーの除外」に必要なフィールドの書き込み配線)。trial_start_atと
    同じ「既に値がある場合は上書きしない」冪等性は書き込み先(InMemoryUsageCounter等)側の
    契約であり、本関数は無条件に呼び出すのみ。`usage_counter`未指定時は従来通り
    upgraded_atの書き込みを行わない(後方互換、テストでも指定なしのまま動作する)。
    """
    data_object = event.get("data", {}).get("object", {})
    user_id = data_object.get("client_reference_id")
    stripe_customer_id = data_object.get("customer")

    if (
        not isinstance(user_id, str)
        or not user_id
        or not isinstance(stripe_customer_id, str)
        or not stripe_customer_id
    ):
        return CheckoutSessionLinkResult(linked=False)

    store.set_stripe_customer_id(user_id, stripe_customer_id)

    upgraded_at_written = False
    if usage_counter is not None:
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        usage_counter.set_upgraded_at_if_unset(user_id, resolved_now)
        upgraded_at_written = True

    return CheckoutSessionLinkResult(
        linked=True,
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        upgraded_at_written=upgraded_at_written,
    )


def make_resolve_user_id(
    user_profile_store: UserProfileStoreProtocol,
) -> Callable[[str], Optional[str]]:
    """`dispatch_stripe_event()`の`resolve_user_id`引数の型に合わせた薄いファクトリ
    (stripe-customer-id-linking-design.md 3節)。"""
    return user_profile_store.get_user_id_by_stripe_customer_id


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果(stripe-webhook-http-entry-point-design.md 1節)。"""

    status_code: int
    dispatch_result: Optional[StripeDispatchResult] = None
    checkout_link_result: Optional[CheckoutSessionLinkResult] = None
    error: Optional[str] = None


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    user_profile_store: Optional[UserProfileStoreProtocol] = None,
    usage_counter: Optional[UpgradedAtWriterProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版)。生のリクエストボディ(bytes)を
    受け取り、署名検証(verify_stripe_signature)・JSONパース・dispatch_stripe_event()への
    配線までを行う(stripe-webhook-http-entry-point-design.mdで設計した、
    verify_stripe_signature()とdispatch_stripe_event()を結ぶエントリポイント)。

    - 署名検証に失敗した場合は401相当を返し、JSONパース以降の配線を一切行わない
      (不正なリクエストへの余計な処理を避ける、LINE側receive_webhook()と同じ方針)。
    - 署名検証後にbodyをJSONとしてパースする。パース失敗、またはパース結果がdictでない
      場合は400相当を返す(Stripeからの実際のリクエストでは通常発生しないはずの異常系だが、
      エントリポイントとして不正な入力にも例外を外に漏らさない設計とする)。
    - イベント種別が`checkout.session.completed`の場合は`dispatch_stripe_event()`
      (`customer.subscription.*`専用)へは渡さず、`handle_checkout_session_completed()`
      へ振り分ける(`user_profile_store`が渡されていない場合は何もせず200を返す、
      stripe-customer-id-linking-design.md 3節)。`usage_counter`が渡されていれば
      `upgraded_at`の書き込みも同時に行う(trial-end-scheduler-design.md 2節、
      未指定時は従来通り書き込まない)。
    - それ以外のイベント種別はこれまで通りdispatch_stripe_event()にそのまま委譲し200を
      返す。resolve_user_idが解決できなかった場合・対象外のイベント種別であっても、
      Stripe側の再送ループを避けるためリクエスト自体は200(受理)として扱う。
      `invoice.payment_failed`/`invoice.payment_succeeded`(payment-failure-dunning-
      design.md 6節対応、フェーズ119)もこの経路でdispatch_stripe_event()へ`usage_counter`
      ごと委譲する。`usage_counter`はUpgradedAtWriterProtocolとして型注釈しているが、
      dispatch_stripe_event()側ではPaymentFailureUsageCounterProtocol(set_payment_
      failure_detected_at等)としても参照される。InMemoryUsageCounterは両方のメソッド群を
      実装しており、構造的部分型付け上どちらのProtocolも満たすため実害はない。
    """
    resolved_now = now if now is not None else datetime.now(timezone.utc)
    if not verify_stripe_signature(
        body, signature_header, webhook_secret, now=resolved_now.timestamp()
    ):
        return StripeWebhookReceiverResult(status_code=401, error="invalid_signature")

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(parsed, dict):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_event")

    if parsed.get("type") == "checkout.session.completed":
        checkout_link_result = (
            handle_checkout_session_completed(
                parsed,
                user_profile_store,
                usage_counter=usage_counter,
                now=resolved_now,
            )
            if user_profile_store is not None
            else CheckoutSessionLinkResult(linked=False)
        )
        return StripeWebhookReceiverResult(
            status_code=200, checkout_link_result=checkout_link_result
        )

    dispatch_result = dispatch_stripe_event(
        parsed,
        store=store,
        resolve_user_id=resolve_user_id,
        usage_counter=usage_counter,
        push_client=push_client,
        now=resolved_now,
    )
    return StripeWebhookReceiverResult(status_code=200, dispatch_result=dispatch_result)


def get_stripe_runtime_dependencies() -> dict:
    """receive_stripe_webhook()に渡す依存関係一式を組み立てるファクトリ
    (stripe-webhook-cloud-function-entry-point-design.md 2節、
    stripe-customer-id-linking-design.md 4節)。

    LINE版get_runtime_dependencies()と異なり、`store`・`resolve_user_id`は
    receive_stripe_webhook()側でNoneを許容しない必須引数のため、空辞書では返せない。

    - store: InMemoryProfileDeletionCandidateStore()を暫定的に返す。実Firestore接続は
      実GCPプロジェクト作成(オーナー承認待ち)後の課題として別途残る。プロセス起動ごとに
      初期化されるため、実Cloud Functions環境では呼び出しをまたいで削除候補フラグが
      保持されない点に注意(design 2節)。
    - user_profile_store: InMemoryUserProfileStore()を1つ生成し、resolve_user_idと
      共有する(checkout.session.completedで書き込んだ紐付けを、同一プロセス内の
      customer.subscription.*解決で読めるようにするため)。storeと同様プロセス起動ごとに
      初期化されるため、実Cloud Functions環境では呼び出しをまたいで紐付けが保持されない
      (stripe-customer-id-linking-design.md 4節の既知の限界)。
    - resolve_user_id: make_resolve_user_id(user_profile_store)。紐付けがまだ無い
      stripe_customer_idに対してはNoneを返し、dispatch_stripe_event()はそれを
      unresolved_customersとして安全に扱い200を返す(フェーズ94で確認済み)。
    - usage_counter: cloud_function_webhook.InMemoryUsageCounter()を1つ生成する
      (trial-end-scheduler-design.md 2節、フェーズ102の残課題への対応)。実運用では
      LINE側Cloud FunctionとStripe側Cloud Functionが同一Firestoreの`usage_counter`
      コレクションを共有する想定だが、本プロセスではLINE側とは別プロセス・別インスタンス
      で初期化されるため、store・user_profile_storeと同様に呼び出しをまたいで
      upgraded_atが保持されない(実Firestore接続後に解消される既知の限界)。
    """
    user_profile_store = InMemoryUserProfileStore()
    return {
        "store": InMemoryProfileDeletionCandidateStore(),
        "resolve_user_id": make_resolve_user_id(user_profile_store),
        "user_profile_store": user_profile_store,
        "usage_counter": InMemoryUsageCounter(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、Stripe版)。

    stripe-webhook-http-entry-point-design.md「残課題」で未着手のまま残っていた、
    実リクエストオブジェクトからのbody(`request.get_data()`)・署名ヘッダ
    (`request.headers.get("Stripe-Signature")`)取り出し配線をここで行い、
    receive_stripe_webhook()に委譲する(LINE版cloud_function_webhook.main()と対称の構成、
    design 3節)。`webhook_secret`は環境変数`STRIPE_WEBHOOK_SECRET`から取得する。
    """
    body = request.get_data()
    signature_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    result = receive_stripe_webhook(
        body, signature_header, webhook_secret, **get_stripe_runtime_dependencies()
    )

    if result.status_code == 200:
        return "OK", 200
    return (result.error or "error"), result.status_code
