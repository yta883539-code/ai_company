"""Stripe Webhookの署名検証(stripe-webhook-signature-verification-design.md フェーズ125)・
HTTPエントリポイント(stripe-webhook-http-entry-point-design.md フェーズ127)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジック・`dispatch_stripe_event()`への配線のみを切り出したモジュール。
`cloud_function_webhook.py`(LINE側)・`deletion_candidate.py`とは独立した別ファイルとし、
既存コードには一切影響を与えない。

course-set-pasha/prototype/stripe_webhook.py(フェーズ93・95)の`verify_stripe_signature()`・
`receive_stripe_webhook()`と同一のアルゴリズム(design 2節のとおり、venture固有の差異は無い)。

`checkout.session.completed`の受信配線(フェーズ127「残課題」)は
checkout-session-completed-handling-design.mdで設計し、本フェーズで追加した。
user-account-linking-design.md 4節のとおり、本ventureは`client_reference_id`に
既にuser_profile上で判明済みの`user_id`をそのまま設定できる前提のため、
course-set-pashaのような別動線の連携コード方式は不要で、course-set-pashaの
`handle_checkout_session_completed()`とほぼ同じ処理をそのまま踏襲できる。

trial-end-scheduler-design.md 2節「今後の課題」で残っていた`upgraded_at`書き込み
配線(フェーズ135)を`handle_checkout_session_completed()`に追加した。本venture
側は`UserProfileStoreProtocol`が`upgraded_at`を直接保持する設計(course-set-pashaの
`usage_counter.set_upgraded_at_if_unset()`のような別オブジェクトへの委譲ではない)
のため、`store.get(user_id).upgraded_at is None`を呼び出し側で確認してから
`store.set_upgraded_at()`を呼ぶ形で「一度設定されたら以降不変」(UserProfile
docstring)を守る。

`payment_store`/`push_client`/`recovery_push_client`(フェーズ149追加): stripe_dispatch.py
の`dispatch_stripe_event()`はフェーズ140・147・148で`invoice.payment_failed`/
`invoice.payment_succeeded`(決済失敗検知・復旧通知)を扱えるようになっていたが、
本モジュールの`receive_stripe_webhook()`はこれら3引数を受け取らずダイジェストを
`dispatch_stripe_event()`へそのまま委譲していたため、実際のHTTPエントリポイント経由
では`payment_store`が常に`None`扱いになり、決済失敗の検知・復旧通知の両イベントが
実際には`ignored_types`として処理されないまま素通りしてしまう配線漏れがあった
(payment-failure-dunning-design.md 6節の一連の実装〈フェーズ141〜148〉が
`dispatch_stripe_event()`単体では検証済みでも、HTTPエントリポイントを経由した
一気通貫の経路ではまだ検証されていなかった)。本フェーズで3引数を追加し、そのまま
`dispatch_stripe_event()`へ委譲するだけの薄い配線で解消した。

`plan_store`(フェーズ161追加): user-account-linking-design.md 4節が「`customer.
subscription.*`受信のたびに更新する」と確定していた`current_plan_id`の同期処理
(subscription_plan_sync.py)を`dispatch_stripe_event()`が受け取れるようになったのに
合わせ、本モジュールでも`payment_store`等と同じ薄い委譲配線を追加した。

`blocked_but_billing_store`(フェーズ175追加): blocked-but-billing-owner-notification-
design.md 6節「クリア配線」対応。`dispatch_stripe_event()`が新たに受け取れるように
なった`blocked_but_billing_store`をそのまま委譲する薄い配線で、`payment_store`等と
同じく実HTTPエントリポイント経由でも`customer.subscription.deleted`受信時の
`blocked_but_billing_owner_notified_at`クリアが機能するようにする。省略時(`None`)は
クリアを行わない(既存呼び出し経路への後方互換措置)。

`event_id_store`(フェーズ177追加): stripe-event-idempotency-design.mdで設計した、
`event.id`によるべき等性チェック。指定時、同一`event.id`を持つイベントが2回目以降
届いた場合はハンドラを一切呼び出さずに200を返す(決済失敗検知・復旧通知等の
非べき等なLINE Push送信が重複配信により複数回実行されるのを防ぐ)。省略時(`None`)は
従来通りべき等性チェックを行わない(既存呼び出し経路への後方互換措置)。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional

from blocked_but_billing_owner_notification import (
    BlockedButBillingOwnerNotifiedAtStoreProtocol,
)
from deletion_candidate import InMemoryProfileDeletionCandidateStore
from payment_failure import LinePushClient, PaymentFailureStoreProtocol
from payment_recovery_notification import LinePushClient as RecoveryPushClient
from stripe_dispatch import (
    ProfileDeletionCandidateStoreProtocol,
    StripeDispatchResult,
    dispatch_stripe_event,
)
from subscription_plan_sync import CurrentPlanStoreProtocol
from user_id_linking import InMemoryUserProfileStore, UserProfileStoreProtocol


class StripeEventIdStoreProtocol:
    """stripe-event-idempotency-design.md 2節: `event.id`単位の処理済み記録を
    保持するストアのインターフェース。`user_id`単位の各種Protocolとはキーの性質が
    異なるため独立させた(design 2節参照)。"""

    def has_processed(self, event_id: str) -> bool:
        raise NotImplementedError

    def mark_processed(self, event_id: str) -> None:
        raise NotImplementedError


class InMemoryStripeEventIdStore:
    """design 3節: 検証用のインメモリ実装。プロセス起動ごとに初期化されるため、
    実Cloud Functions環境では呼び出しをまたいで保持されない(既存の各種InMemory
    ストアと同じ既知の限界)。"""

    def __init__(self) -> None:
        self._processed_event_ids: set = set()

    def has_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def mark_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)


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
    v1_signatures: List[str] = []
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


@dataclass
class CheckoutSessionLinkResult:
    """handle_checkout_session_completed()の結果
    (checkout-session-completed-handling-design.md 1節)。"""

    linked: bool
    user_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    error: Optional[str] = None
    upgraded_at_written: bool = False


def handle_checkout_session_completed(
    event: dict,
    store: UserProfileStoreProtocol,
    *,
    now: Optional[datetime] = None,
) -> CheckoutSessionLinkResult:
    """`checkout.session.completed`イベントから`client_reference_id`(=user_id、
    Checkout Session作成時にuser-account-linking-design.md 4節のとおり既知の値を
    そのまま設定してある)と`customer`(=stripe_customer_id)を取り出し、`store`に
    紐付けを書き込む(checkout-session-completed-handling-design.md 1節)。

    course-set-pashaと異なり、本ventureは決済前に`user_profile`が既に存在している
    前提(design 4節)のため、`client_reference_id`・`customer`の形式が正しくても
    対応する`user_profile`が見つからない場合は異常系として区別し、`store`への
    書き込みは行わない(想定外の順序でCheckout Sessionが作成された場合に、
    存在しないuser_idへ書き込んでデータを汚さないための安全策)。

    紐付けに成功した場合、trial-end-scheduler-design.md 2節で残っていた`upgraded_at`
    書き込み(フェーズ135)もあわせて行う。`upgraded_at`は「有料転換時に1回だけ書き込む」
    フィールド(UserProfile docstring)のため、既に設定済みの場合は上書きしない
    (Stripeの再送・重複配信でこのイベントが複数回届いても、最初の転換日時を保持する)。
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
        return CheckoutSessionLinkResult(linked=False, error="missing_fields")

    profile = store.get(user_id)
    if profile is None:
        return CheckoutSessionLinkResult(
            linked=False, user_id=user_id, error="user_profile_not_found"
        )

    store.set_stripe_customer_id(user_id, stripe_customer_id)

    upgraded_at_written = False
    if profile.upgraded_at is None:
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        store.set_upgraded_at(user_id, resolved_now)
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
    (checkout-session-completed-handling-design.md 2節、course-set-pashaの
    `make_resolve_user_id()`と同じ位置づけ)。"""
    return user_profile_store.get_user_id_by_stripe_customer_id


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果(stripe-webhook-http-entry-point-design.md 1節、
    checkout-session-completed-handling-design.md 1節で`checkout_link_result`を追加)。"""

    status_code: int
    dispatch_result: Optional[StripeDispatchResult] = None
    checkout_link_result: Optional[CheckoutSessionLinkResult] = None
    error: Optional[str] = None
    # フェーズ177追加: event_id_store指定時、`event.id`が処理済みのため
    # ハンドラを呼び出さずに200を返した場合`True`。
    duplicate: bool = False


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    user_profile_store: Optional[UserProfileStoreProtocol] = None,
    payment_store: Optional[PaymentFailureStoreProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    recovery_push_client: Optional[RecoveryPushClient] = None,
    plan_store: Optional[CurrentPlanStoreProtocol] = None,
    blocked_but_billing_store: Optional[BlockedButBillingOwnerNotifiedAtStoreProtocol] = None,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版)。生のリクエストボディ(bytes)を
    受け取り、署名検証(verify_stripe_signature)・JSONパース・イベント種別に応じた
    ディスパッチまでを行う(stripe-webhook-http-entry-point-design.mdで設計した、
    verify_stripe_signature()とdispatch_stripe_event()を結ぶエントリポイントに、
    checkout-session-completed-handling-design.mdで`checkout.session.completed`の
    振り分けを追加)。

    - 署名検証に失敗した場合は401相当を返し、JSONパース以降の配線を一切行わない
      (不正なリクエストへの余計な処理を避ける、LINE側receive_webhook()と同じ方針)。
    - 署名検証後にbodyをJSONとしてパースする。パース失敗、またはパース結果がdictでない
      場合は400相当を返す(Stripeからの実際のリクエストでは通常発生しないはずの異常系だが、
      エントリポイントとして不正な入力にも例外を外に漏らさない設計とする)。
    - イベント種別が`checkout.session.completed`の場合は`dispatch_stripe_event()`
      (`customer.subscription.*`専用)へは渡さず`handle_checkout_session_completed()`へ
      振り分ける(`user_profile_store`が渡されていない場合は何もせず200を返す、
      course-set-pashaのreceive_stripe_webhook()と同じ方針)。
    - それ以外のイベント種別はこれまで通りdispatch_stripe_event()にそのまま委譲し200を
      返す。resolve_user_idが解決できなかった場合・対象外のイベント種別であっても、
      Stripe側の再送ループを避けるためリクエスト自体は200(受理)として扱う。

    `payment_store`・`push_client`・`recovery_push_client`はpayment-failure-dunning-
    design.md 6節対応(フェーズ149追加)。`dispatch_stripe_event()`は`invoice.payment_
    failed`/`invoice.payment_succeeded`を処理するために既にこれら3引数を受け取れる
    設計になっていた(フェーズ140・147・148)が、本関数はそのままこれらを内部で握り
    つぶしており、実際のHTTPエントリポイント経由では`payment_store`が常に`None`扱いに
    なって決済失敗検知・復旧通知の両イベントが`ignored_types`に落ちてしまう配線漏れが
    あった。本フェーズはそのままdispatch_stripe_event()へ委譲するだけの薄い配線を追加
    して解消する。3引数とも省略時(`None`)の挙動はこれまでと変わらない(後方互換)。

    `plan_store`はuser-account-linking-design.md 4節対応(フェーズ161追加)。
    `dispatch_stripe_event()`が新たに受け取れるようになった`plan_store`をそのまま
    委譲する薄い配線で、`payment_store`等と同じく実HTTPエントリポイント経由でも
    `customer.subscription.*`受信時のプランID同期が機能するようにする。省略時
    (`None`)は同期を行わない(既存呼び出し経路への後方互換措置)。

    `event_id_store`はstripe-event-idempotency-design.md対応(フェーズ177追加)。
    指定時、パース済みイベントの`id`が既に処理済みであれば`checkout.session.
    completed`分岐・`dispatch_stripe_event()`のいずれも呼び出さず、`duplicate=True`
    とともに200を返す(副作用ゼロ)。`id`が欠落・非文字列の場合はチェックを
    スキップし従来通り処理する(安全側)。省略時(`None`)はべき等性チェックを
    一切行わない(既存呼び出し経路への後方互換措置)。
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

    event_id = parsed.get("id")
    check_idempotency = event_id_store is not None and isinstance(event_id, str)
    if check_idempotency and event_id_store.has_processed(event_id):
        return StripeWebhookReceiverResult(status_code=200, duplicate=True)

    if parsed.get("type") == "checkout.session.completed":
        checkout_link_result = (
            handle_checkout_session_completed(
                parsed, user_profile_store, now=resolved_now
            )
            if user_profile_store is not None
            else CheckoutSessionLinkResult(linked=False, error="store_not_configured")
        )
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200, checkout_link_result=checkout_link_result
        )

    dispatch_result = dispatch_stripe_event(
        parsed,
        store=store,
        resolve_user_id=resolve_user_id,
        payment_store=payment_store,
        push_client=push_client,
        recovery_push_client=recovery_push_client,
        plan_store=plan_store,
        blocked_but_billing_store=blocked_but_billing_store,
        now=resolved_now,
    )
    if check_idempotency:
        event_id_store.mark_processed(event_id)
    return StripeWebhookReceiverResult(status_code=200, dispatch_result=dispatch_result)


def get_stripe_runtime_dependencies() -> dict:
    """receive_stripe_webhook()に渡す依存関係一式を組み立てるファクトリ
    (stripe-webhook-http-entry-point-design.md「残課題」で未着手のまま残っていた項目、
    course-set-pashaの`get_stripe_runtime_dependencies()`と同じ位置づけ)。

    - store: `InMemoryProfileDeletionCandidateStore()`を暫定的に返す。実Firestore接続は
      実GCPプロジェクト作成(オーナー承認待ち)後の課題として別途残る。プロセス起動ごとに
      初期化されるため、実Cloud Functions環境では呼び出しをまたいで削除候補フラグが
      保持されない点に注意(course-set-pashaの同名ファクトリと同じ既知の限界)。
    - user_profile_store: `InMemoryUserProfileStore()`を1つ生成する。本ventureは
      `PaymentFailureStoreProtocol`を専用のInMemoryスタブとして持たず、
      `UserProfileStoreProtocol`が構造的に(duck typing)満たす設計(payment_failure.py
      冒頭コメント参照)のため、同じインスタンスを`payment_store`としても渡せる。
      `CurrentPlanStoreProtocol`(subscription_plan_sync.py、フェーズ161追加)も同じ
      理由で構造的に満たすため、同じインスタンスを`plan_store`としても渡す。
      `BlockedButBillingOwnerNotifiedAtStoreProtocol`(blocked_but_billing_owner_
      notification.py、フェーズ175追加)も同じ理由で構造的に満たすため、同じ
      インスタンスを`blocked_but_billing_store`としても渡す。
      storeと同様プロセス起動ごとに初期化されるため、実Cloud Functions環境では
      呼び出しをまたいで紐付け・決済状態・プランID・通知済みフラグが保持されない
      (実Firestore接続後に解消される既知の限界)。
    - resolve_user_id: `make_resolve_user_id(user_profile_store)`。紐付けがまだ無い
      stripe_customer_idに対してはNoneを返し、dispatch_stripe_event()はそれを
      unresolved_customersとして安全に扱い200を返す。
    - push_client・recovery_push_client: 実LINE Push API接続(チャネルアクセストークン)は
      引き続きオーナー承認待ちのため、ここでは意図的に渡さない(省略時は`None`となり、
      決済失敗検知・復旧の状態書き込みは行われるが通知は送信されない。
      payment-failure-dunning-design.md 6節と同じ「配線はできているが実送信はまだ」
      という区別を保つ)。
    - event_id_store(フェーズ177追加): stripe-event-idempotency-design.md対応。
      `InMemoryStripeEventIdStore()`を`user_profile_store`とは独立に1つ生成する
      (design 2節のとおりキーの性質〈event_idかuser_idか〉が異なるため使い回さない)。
    """
    user_profile_store = InMemoryUserProfileStore()
    return {
        "store": InMemoryProfileDeletionCandidateStore(),
        "resolve_user_id": make_resolve_user_id(user_profile_store),
        "user_profile_store": user_profile_store,
        "payment_store": user_profile_store,
        "plan_store": user_profile_store,
        "blocked_but_billing_store": user_profile_store,
        "event_id_store": InMemoryStripeEventIdStore(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、Stripe版)。

    stripe-webhook-http-entry-point-design.md「残課題」で未着手のまま残っていた、
    実リクエストオブジェクトからのbody(`request.get_data()`)・署名ヘッダ
    (`request.headers.get("Stripe-Signature")`)取り出し配線をここで行い、
    receive_stripe_webhook()に委譲する(LINE版cloud_function_webhook.main()、
    course-set-pasha版stripe_webhook.main()と対称の構成)。`webhook_secret`は
    環境変数`STRIPE_WEBHOOK_SECRET`から取得する。
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


def _demo() -> None:
    secret = "whsec_demo_secret"
    payload = b'{"id":"evt_demo","type":"customer.subscription.deleted"}'
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={sig}"
    print("valid signature ->", verify_stripe_signature(payload, header, secret))
    print("missing header ->", verify_stripe_signature(payload, None, secret))


if __name__ == "__main__":
    _demo()
