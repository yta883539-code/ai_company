"""Stripe Webhookの署名検証・`checkout.session.completed`/`customer.subscription.deleted`/
`customer.subscription.updated`/`invoice.payment_failed`/`invoice.payment_succeeded`受信処理
(stripe-webhook-checkout-completed-design.md フェーズ51、subscription-canceled-webhook-
design.md フェーズ53、契約者向け解約完了通知の配線はsubscription-cancellation-notification-
design.md フェーズ54、解約予約受理・解約取り消し通知の配線はsubscription-cancellation-
scheduled-notification-design.md フェーズ55、決済失敗ダニングの配線はpayment-failure-
dunning-design.md フェーズ56、`event.id`によるべき等性チェックはstripe-event-
idempotency-design.md フェーズ77)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジック・各イベントハンドラ・両者を結ぶHTTPエントリポイントのみを切り出した
モジュール。`usage_counter_workshop.py`・`checkout_session.py`とは独立した別ファイルとし、
既存コードには一切影響を与えない。

`verify_stripe_signature()`はcourse-set-pasha/prototype/stripe_webhook.py(フェーズ93)・
aircon-pasha/prototype/stripe_webhook.py(フェーズ125)と同一アルゴリズム
(design 1節の通り、venture固有の差異は無い)。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from blocked_but_billing_owner_notification import clear_blocked_but_billing_owner_notified_at
from checkout_session import VALID_PLAN_IDS
from payment_failure_notification import (
    OUTCOME_NOT_APPLICABLE,
    handle_payment_failure_detected,
    handle_payment_succeeded,
)
from subscription_cancellation_notification import (
    OUTCOME_NO_CHANGE,
    LinePushClient,
    handle_subscription_cancellation_update,
    handle_subscription_cancelled,
)
from usage_counter_workshop import WorkshopStoreProtocol


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """`Stripe-Signature`ヘッダを検証する(design 1節のアルゴリズムどおり)。

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


# ---------------------------------------------------------------------------
# event.idべき等性チェック(フェーズ77、stripe-event-idempotency-design.md)
#
# aircon-pashaフェーズ177の同名設計を本venture固有のディスパッチ構造(workshop_store
# 単位のイベントハンドラ群)へそのまま翻案する。`WorkshopStoreProtocol`とはキーの性質
# (`event_id`か`workshop_id`か)が異なるため独立したProtocolとする(design 2節)。
# ---------------------------------------------------------------------------

class StripeEventIdStoreProtocol(Protocol):
    """`event.id`単位の処理済み記録を保持するストアのインターフェース
    (stripe-event-idempotency-design.md 2節)。"""

    def has_processed(self, event_id: str) -> bool:
        ...

    def mark_processed(self, event_id: str) -> None:
        ...


class InMemoryStripeEventIdStore:
    """design 3節: 検証用のインメモリ実装。プロセス起動ごとに初期化されるため、実Cloud
    Functions環境では呼び出しをまたいで保持されない(他のInMemory系ストアと同じ既知の
    限界)。"""

    def __init__(self) -> None:
        self._processed_event_ids: set = set()

    def has_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def mark_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)


@dataclass
class CheckoutSessionCompletedResult:
    """handle_checkout_session_completed()の戻り値(design 2節、plan_written追加は
    craftsman-account-linking-design.md フェーズ66追記7節の暫定plan_id上書き配線)。"""

    workshop_id: Optional[str] = None
    stripe_customer_id_written: bool = False
    plan_written: bool = False
    invalid: bool = False


def handle_checkout_session_completed(
    data_object: dict,
    workshop_store: WorkshopStoreProtocol,
) -> CheckoutSessionCompletedResult:
    """design 2節。`checkout.session.completed`イベントの`data.object`を受け取り、
    workshop側のStripe顧客ID・subscription_statusを更新する。

    `client_reference_id`(=workshop_id、checkout-initiation-flow-design.md 3節の通り
    `build_checkout_session_params()`が設定したもの)が空・欠落の場合は不正なイベントとして
    `invalid=True`を返し、以降の書き込みは一切行わない。

    `metadata.plan_id`(`checkout_session.build_checkout_session_params()`がSession作成時に
    設定したもの、line_itemsのexpand等の追加API呼び出し不要)に既知のplan_id
    (`VALID_PLAN_IDS`)が入っている場合、`workshop_store.set_plan()`で上書きする
    (craftsman-account-linking-design.md フェーズ66追記7節: workshop作成時は暫定で
    最安プランを仮設定し、Checkout完了時に実際に選ばれたプランへ上書きする2段階運用の
    2段階目)。`metadata`欠落・`plan_id`欠落・未知の値の場合は何も書き込まない
    (安全側。古いCheckout Session実装〈metadata省略〉からのイベントでも
    顧客ID紐付け自体は従来通り行える)。
    """
    workshop_id = data_object.get("client_reference_id")
    if not workshop_id:
        return CheckoutSessionCompletedResult(invalid=True)

    stripe_customer_id_written = False
    if workshop_store.get_stripe_customer_id(workshop_id) is None:
        stripe_customer_id = data_object.get("customer")
        if stripe_customer_id:
            workshop_store.set_stripe_customer_id(workshop_id, stripe_customer_id)
            stripe_customer_id_written = True

    workshop_store.set_subscription_status(workshop_id, "active")

    plan_written = False
    metadata = data_object.get("metadata")
    plan_id = metadata.get("plan_id") if isinstance(metadata, dict) else None
    if isinstance(plan_id, str) and plan_id in VALID_PLAN_IDS:
        workshop_store.set_plan(workshop_id, plan_id)
        plan_written = True

    return CheckoutSessionCompletedResult(
        workshop_id=workshop_id,
        stripe_customer_id_written=stripe_customer_id_written,
        plan_written=plan_written,
    )


@dataclass
class CustomerSubscriptionDeletedResult:
    """handle_customer_subscription_deleted()の戻り値(design 2節、
    subscription-cancellation-notification-design.md フェーズ54で`notified`追加)。"""

    workshop_id: Optional[str] = None
    invalid: bool = False
    unresolved: bool = False
    notified: bool = False


def handle_customer_subscription_deleted(
    data_object: dict,
    workshop_store: WorkshopStoreProtocol,
    *,
    push_client: Optional[LinePushClient] = None,
) -> CustomerSubscriptionDeletedResult:
    """subscription-canceled-webhook-design.md 2節。`customer.subscription.deleted`
    イベントの`data.object`を受け取り、対応するworkshopの`subscription_status`を
    `"canceled"`へ更新する。

    このイベントは`checkout.session.completed`と異なり`client_reference_id`を
    持たないため、`data_object["customer"]`(Stripe顧客ID)を
    `workshop_store.get_workshop_id_by_stripe_customer_id()`で逆引きしてworkshop_idを
    解決する。`customer`が空・欠落の場合は`invalid=True`、逆引きで解決できなかった
    場合は`unresolved=True`を返し、いずれも`set_subscription_status`は呼ばない。

    `push_client`指定時(subscription-cancellation-notification-design.md フェーズ54)は
    `set_subscription_status`成功後に契約者(`contractor_user_id`)へLINE通知を送信する。
    通知の送信成否は状態更新の成否と独立とし(design 4節)、`push_client`省略時は従来通り
    通知なし(既存呼び出し元への後方互換)。

    (フェーズ81、blocked-but-billing-owner-notification-design.md 6節)`set_subscription_
    status(workshop_id, "canceled")`成功時、常に`clear_blocked_but_billing_owner_
    notified_at(workshop_store, workshop_id)`を呼ぶ(解約確定=もう課金されないため、
    ブロック中かつ契約継続中というオーナー通知の前提が解消したことを表す)。
    `workshop_store`自体が`BlockedButBillingOwnerNotifiedAtStoreProtocol`を構造的に
    満たすため、追加の引数は不要。
    """
    stripe_customer_id = data_object.get("customer")
    if not stripe_customer_id:
        return CustomerSubscriptionDeletedResult(invalid=True)

    workshop_id = workshop_store.get_workshop_id_by_stripe_customer_id(stripe_customer_id)
    if workshop_id is None:
        return CustomerSubscriptionDeletedResult(unresolved=True)

    workshop_store.set_subscription_status(workshop_id, "canceled")
    clear_blocked_but_billing_owner_notified_at(workshop_store, workshop_id)

    notified = False
    if push_client is not None:
        notification_result = handle_subscription_cancelled(
            workshop_id, workshop_store, push_client
        )
        notified = notification_result.notified

    return CustomerSubscriptionDeletedResult(workshop_id=workshop_id, notified=notified)


@dataclass
class CustomerSubscriptionUpdatedResult:
    """handle_customer_subscription_updated()の戻り値
    (subscription-cancellation-scheduled-notification-design.md フェーズ55 6節)。
    `invalid`/`unresolved`はhandle_customer_subscription_deleted()と同じ意味。"""

    workshop_id: Optional[str] = None
    invalid: bool = False
    unresolved: bool = False
    outcome: str = OUTCOME_NO_CHANGE
    notified: bool = False


def handle_customer_subscription_updated(
    event: dict,
    workshop_store: WorkshopStoreProtocol,
    *,
    push_client: Optional[LinePushClient] = None,
) -> CustomerSubscriptionUpdatedResult:
    """subscription-cancellation-scheduled-notification-design.md フェーズ55。
    `customer.subscription.updated`イベント全体(`data.object`と`data.previous_attributes`
    の両方が必要なため、`data_object`のみを受け取る他ハンドラと異なり`event`全体を
    受け取る)を処理し、`cancel_at_period_end`の前後比較(design 3節)から
    解約予約受理・解約取り消しを分類して契約者へLINE通知する。

    `client_reference_id`を持たないイベントのため、`customer.subscription.deleted`と
    同じ`get_workshop_id_by_stripe_customer_id()`逆引きでworkshop_idを解決する
    (design 2節)。`push_client`省略時、または分類結果が`OUTCOME_NO_CHANGE`の場合は
    通知を送信しない。本イベントは`set_subscription_status`等の状態変更を一切伴わないが
    (design 6節)、`current_period_end`(Unixタイムスタンプ)のみは、
    subscription-billing-data-model-design.md「4. 未検証・残課題」(フェーズ91→92で対応)の
    通りworkshop側へ`set_current_period_end`で永続化する(通知の要否とは独立に行う)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")
    if not stripe_customer_id:
        return CustomerSubscriptionUpdatedResult(invalid=True)

    workshop_id = workshop_store.get_workshop_id_by_stripe_customer_id(stripe_customer_id)
    if workshop_id is None:
        return CustomerSubscriptionUpdatedResult(unresolved=True)

    raw_current_period_end = data_object.get("current_period_end")
    if isinstance(raw_current_period_end, (int, float)) and not isinstance(
        raw_current_period_end, bool
    ):
        workshop_store.set_current_period_end(
            workshop_id, datetime.fromtimestamp(raw_current_period_end, tz=timezone.utc)
        )

    if push_client is None:
        return CustomerSubscriptionUpdatedResult(workshop_id=workshop_id)

    previous_attrs = event.get("data", {}).get("previous_attributes", {})
    after = data_object.get("cancel_at_period_end", False)
    before = previous_attrs.get("cancel_at_period_end", after)

    update_result = handle_subscription_cancellation_update(
        workshop_id,
        before,
        after,
        data_object.get("current_period_end"),
        workshop_store,
        push_client,
    )
    return CustomerSubscriptionUpdatedResult(
        workshop_id=workshop_id,
        outcome=update_result.outcome,
        notified=update_result.notified,
    )


@dataclass
class InvoicePaymentFailedResult:
    """handle_invoice_payment_failed()の戻り値(payment-failure-dunning-design.md
    フェーズ56 5節)。`invalid`/`unresolved`は他イベントハンドラと同じ意味。"""

    workshop_id: Optional[str] = None
    invalid: bool = False
    unresolved: bool = False
    notified: bool = False


def handle_invoice_payment_failed(
    data_object: dict,
    workshop_store: WorkshopStoreProtocol,
    *,
    push_client: Optional[LinePushClient] = None,
    now: Optional[datetime] = None,
) -> InvoicePaymentFailedResult:
    """payment-failure-dunning-design.md 5節。`invoice.payment_failed`イベントの
    `data.object`を受け取り、対応するworkshopの`subscription_status`を`"past_due"`へ、
    `payment_failure_detected_at`を検知時刻へ更新する。

    `customer.subscription.deleted`と同じ`get_workshop_id_by_stripe_customer_id()`逆引きで
    workshop_idを解決する。検知時刻は`data_object.created`(Unixタイムスタンプ)を優先し、
    存在しない場合は`now`(省略時は`datetime.now(timezone.utc)`)にフォールバックする。

    `push_client`指定時は状態更新後に契約者へLINE通知を送信する(design 4節「決済失敗
    検知時」)。通知の送信成否は状態更新の成否と独立とし、`push_client`省略時は通知なし。
    """
    stripe_customer_id = data_object.get("customer")
    if not stripe_customer_id:
        return InvoicePaymentFailedResult(invalid=True)

    workshop_id = workshop_store.get_workshop_id_by_stripe_customer_id(stripe_customer_id)
    if workshop_id is None:
        return InvoicePaymentFailedResult(unresolved=True)

    created = data_object.get("created")
    if isinstance(created, (int, float)) and not isinstance(created, bool):
        detected_at = datetime.fromtimestamp(created, tz=timezone.utc)
    else:
        detected_at = now if now is not None else datetime.now(timezone.utc)

    workshop_store.set_subscription_status(workshop_id, "past_due")
    workshop_store.set_payment_failure_detected_at(workshop_id, detected_at)

    notified = False
    if push_client is not None:
        detection_result = handle_payment_failure_detected(workshop_id, workshop_store, push_client)
        notified = detection_result.notified

    return InvoicePaymentFailedResult(workshop_id=workshop_id, notified=notified)


@dataclass
class InvoicePaymentSucceededResult:
    """handle_invoice_payment_succeeded()の戻り値(payment-failure-dunning-design.md
    フェーズ56 5節)。`invalid`/`unresolved`は他イベントハンドラと同じ意味。"""

    workshop_id: Optional[str] = None
    invalid: bool = False
    unresolved: bool = False
    outcome: str = OUTCOME_NOT_APPLICABLE
    notified: bool = False


def handle_invoice_payment_succeeded(
    data_object: dict,
    workshop_store: WorkshopStoreProtocol,
    *,
    push_client: Optional[LinePushClient] = None,
    now: Optional[datetime] = None,
) -> InvoicePaymentSucceededResult:
    """payment-failure-dunning-design.md 5節。`invoice.payment_succeeded`イベントの
    `data.object`を受け取り、対応するworkshopの`subscription_status`を`"active"`へ戻す
    (design 1節: 既存の`checkout.session.completed`と同じ値へ揃える)。

    `push_client`指定時は`payment_failure_notification.handle_payment_succeeded()`へ
    委譲し、分類(design 4節2分岐)・通知・`payment_failure_detected_at`クリアを行う。
    送信失敗時(OUTCOME_SEND_FAILED)は`payment_failure_detected_at`をクリアせずWebhook
    リトライに委ねる(`subscription_status`の"active"化自体は既に完了しているため、
    リトライは通知・状態クリアのみをやり直す)。`push_client`省略時は通知を行わず
    `payment_failure_detected_at`が設定済みであれば直接クリアする(後方互換経路)。
    """
    stripe_customer_id = data_object.get("customer")
    if not stripe_customer_id:
        return InvoicePaymentSucceededResult(invalid=True)

    workshop_id = workshop_store.get_workshop_id_by_stripe_customer_id(stripe_customer_id)
    if workshop_id is None:
        return InvoicePaymentSucceededResult(unresolved=True)

    workshop_store.set_subscription_status(workshop_id, "active")

    if push_client is not None:
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        recovery_result = handle_payment_succeeded(workshop_id, resolved_now, workshop_store, push_client)
        return InvoicePaymentSucceededResult(
            workshop_id=workshop_id,
            outcome=recovery_result.outcome,
            notified=recovery_result.notified,
        )

    if workshop_store.get_payment_failure_detected_at(workshop_id) is not None:
        workshop_store.clear_payment_failure_detected_at(workshop_id)

    return InvoicePaymentSucceededResult(workshop_id=workshop_id)


@dataclass
class StripeWebhookReceiverResult:
    """design 3節。`unresolved_customer`はsubscription-canceled-webhook-design.md
    2節対応(フェーズ53追加): `customer.subscription.deleted`のstripe_customer_idが
    どのworkshopにも紐付いていなかった場合に`True`となる(Stripe側へは200を返す)。
    `duplicate_event`はstripe-event-idempotency-design.md対応(フェーズ77追加):
    `event_id_store`指定時、既に処理済みの`event.id`を再受信した場合に`True`となる
    (200を返し、いずれのハンドラも呼び出さない)。
    """

    status_code: int
    workshop_id: Optional[str] = None
    ignored_type: Optional[str] = None
    error: Optional[str] = None
    unresolved_customer: bool = False
    duplicate_event: bool = False


def receive_stripe_webhook(
    body: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    workshop_store: Optional[WorkshopStoreProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
) -> StripeWebhookReceiverResult:
    """design 3節。署名検証→JSONパース→(フェーズ77追加)event.idべき等性チェック→
    `checkout.session.completed`/`customer.subscription.deleted`/
    `customer.subscription.updated`/`invoice.payment_failed`/`invoice.payment_succeeded`を
    ディスパッチする薄いHTTPエントリポイント。未対応のイベント種別は無視して200を返す
    (Stripe側の無限リトライを避ける、course-set-pasha/aircon-pashaと同じ方針)。

    `event_id_store`(stripe-event-idempotency-design.md、フェーズ77新設): 指定時、
    パース済みイベントの`id`が既に処理済みであれば以降のいずれの分岐・ハンドラも
    呼び出さず`duplicate_event=True`とともに200を返す(副作用ゼロ)。Stripeは
    「at least once」配信のため、`customer.subscription.deleted`の解約完了通知・
    `invoice.payment_failed`の決済失敗検知通知等、通知送信を伴うハンドラは同一
    イベントの再配信時に二重送信してしまう(individual各ハンドラでべき等性を
    作り込むのではなく、本関数エントリポイント層で一括して弾く。design 2節、
    aircon-pashaフェーズ177と同じ方針)。`id`が欠落・非文字列の場合はチェックを
    スキップし従来通り処理する(Stripeの実イベントでは通常発生しないが、テスト用の
    最小イベントdict等では省略されうるため安全側〈処理を止めない〉に倒す)。
    省略時(`None`)はべき等性チェックを一切行わない(既存呼び出し経路への後方互換
    措置)。記録(`mark_processed`)はハンドラ呼び出し「後」、かつ`invalid`
    (400、不正なイベント)以外の場合に限り行う。`invalid`のまま処理済みにしてしまうと
    Stripe側の本物の不具合(データ欠落した不正イベント)が2回目以降400を返さなくなり
    Stripeダッシュボード上のエラー可視性が失われるため、あえて対象外とした
    (`unresolved_customer`は逆引き失敗というアプリケーション側では正常な結果のため
    処理済みとして記録する)。
    """
    if not verify_stripe_signature(body, sig_header, webhook_secret):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_signature")

    try:
        event = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(event, dict):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    event_id = event.get("id")
    check_idempotency = event_id_store is not None and isinstance(event_id, str)
    if check_idempotency and event_id_store.has_processed(event_id):
        return StripeWebhookReceiverResult(status_code=200, duplicate_event=True)

    event_type = event.get("type")
    if event_type not in (
        "checkout.session.completed",
        "customer.subscription.deleted",
        "customer.subscription.updated",
        "invoice.payment_failed",
        "invoice.payment_succeeded",
    ):
        return StripeWebhookReceiverResult(status_code=200, ignored_type=event_type)

    data_object = event.get("data", {}).get("object", {})
    if workshop_store is None:
        return StripeWebhookReceiverResult(status_code=400, error="missing_workshop_store")

    if event_type == "checkout.session.completed":
        result = handle_checkout_session_completed(data_object, workshop_store)
        if result.invalid:
            return StripeWebhookReceiverResult(status_code=400, error="missing_client_reference_id")
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(status_code=200, workshop_id=result.workshop_id)

    if event_type == "customer.subscription.updated":
        updated_result = handle_customer_subscription_updated(
            event, workshop_store, push_client=push_client
        )
        if updated_result.invalid:
            return StripeWebhookReceiverResult(status_code=400, error="missing_customer")
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        if updated_result.unresolved:
            return StripeWebhookReceiverResult(status_code=200, unresolved_customer=True)
        return StripeWebhookReceiverResult(status_code=200, workshop_id=updated_result.workshop_id)

    if event_type == "customer.subscription.deleted":
        deleted_result = handle_customer_subscription_deleted(
            data_object, workshop_store, push_client=push_client
        )
        if deleted_result.invalid:
            return StripeWebhookReceiverResult(status_code=400, error="missing_customer")
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        if deleted_result.unresolved:
            return StripeWebhookReceiverResult(status_code=200, unresolved_customer=True)
        return StripeWebhookReceiverResult(status_code=200, workshop_id=deleted_result.workshop_id)

    if event_type == "invoice.payment_failed":
        failed_result = handle_invoice_payment_failed(
            data_object, workshop_store, push_client=push_client
        )
        if failed_result.invalid:
            return StripeWebhookReceiverResult(status_code=400, error="missing_customer")
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        if failed_result.unresolved:
            return StripeWebhookReceiverResult(status_code=200, unresolved_customer=True)
        return StripeWebhookReceiverResult(status_code=200, workshop_id=failed_result.workshop_id)

    succeeded_result = handle_invoice_payment_succeeded(
        data_object, workshop_store, push_client=push_client
    )
    if succeeded_result.invalid:
        return StripeWebhookReceiverResult(status_code=400, error="missing_customer")
    if check_idempotency:
        event_id_store.mark_processed(event_id)
    if succeeded_result.unresolved:
        return StripeWebhookReceiverResult(status_code=200, unresolved_customer=True)

    return StripeWebhookReceiverResult(status_code=200, workshop_id=succeeded_result.workshop_id)
