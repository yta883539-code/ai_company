"""Stripe Webhookの署名検証・`checkout.session.completed`/`customer.subscription.deleted`/
`customer.subscription.updated`受信処理(stripe-webhook-checkout-completed-design.md
フェーズ51、subscription-canceled-webhook-design.md フェーズ53、契約者向け解約完了通知の
配線はsubscription-cancellation-notification-design.md フェーズ54、解約予約受理・
解約取り消し通知の配線はsubscription-cancellation-scheduled-notification-design.md
フェーズ55)。

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
from typing import Optional

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


@dataclass
class CheckoutSessionCompletedResult:
    """handle_checkout_session_completed()の戻り値(design 2節)。"""

    workshop_id: Optional[str] = None
    stripe_customer_id_written: bool = False
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

    return CheckoutSessionCompletedResult(
        workshop_id=workshop_id,
        stripe_customer_id_written=stripe_customer_id_written,
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
    """
    stripe_customer_id = data_object.get("customer")
    if not stripe_customer_id:
        return CustomerSubscriptionDeletedResult(invalid=True)

    workshop_id = workshop_store.get_workshop_id_by_stripe_customer_id(stripe_customer_id)
    if workshop_id is None:
        return CustomerSubscriptionDeletedResult(unresolved=True)

    workshop_store.set_subscription_status(workshop_id, "canceled")

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
    通知を送信しない。本イベントは`set_subscription_status`等の状態変更を一切伴わない
    (design 6節)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")
    if not stripe_customer_id:
        return CustomerSubscriptionUpdatedResult(invalid=True)

    workshop_id = workshop_store.get_workshop_id_by_stripe_customer_id(stripe_customer_id)
    if workshop_id is None:
        return CustomerSubscriptionUpdatedResult(unresolved=True)

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
class StripeWebhookReceiverResult:
    """design 3節。`unresolved_customer`はsubscription-canceled-webhook-design.md
    2節対応(フェーズ53追加): `customer.subscription.deleted`のstripe_customer_idが
    どのworkshopにも紐付いていなかった場合に`True`となる(Stripe側へは200を返す)。
    """

    status_code: int
    workshop_id: Optional[str] = None
    ignored_type: Optional[str] = None
    error: Optional[str] = None
    unresolved_customer: bool = False


def receive_stripe_webhook(
    body: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    workshop_store: Optional[WorkshopStoreProtocol] = None,
    push_client: Optional[LinePushClient] = None,
) -> StripeWebhookReceiverResult:
    """design 3節。署名検証→JSONパース→`checkout.session.completed`/
    `customer.subscription.deleted`をディスパッチする薄いHTTPエントリポイント。
    未対応のイベント種別は無視して200を返す(Stripe側の無限リトライを避ける、
    course-set-pasha/aircon-pashaと同じ方針)。
    """
    if not verify_stripe_signature(body, sig_header, webhook_secret):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_signature")

    try:
        event = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(event, dict):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    event_type = event.get("type")
    if event_type not in (
        "checkout.session.completed",
        "customer.subscription.deleted",
        "customer.subscription.updated",
    ):
        return StripeWebhookReceiverResult(status_code=200, ignored_type=event_type)

    data_object = event.get("data", {}).get("object", {})
    if workshop_store is None:
        return StripeWebhookReceiverResult(status_code=400, error="missing_workshop_store")

    if event_type == "checkout.session.completed":
        result = handle_checkout_session_completed(data_object, workshop_store)
        if result.invalid:
            return StripeWebhookReceiverResult(status_code=400, error="missing_client_reference_id")
        return StripeWebhookReceiverResult(status_code=200, workshop_id=result.workshop_id)

    if event_type == "customer.subscription.updated":
        updated_result = handle_customer_subscription_updated(
            event, workshop_store, push_client=push_client
        )
        if updated_result.invalid:
            return StripeWebhookReceiverResult(status_code=400, error="missing_customer")
        if updated_result.unresolved:
            return StripeWebhookReceiverResult(status_code=200, unresolved_customer=True)
        return StripeWebhookReceiverResult(status_code=200, workshop_id=updated_result.workshop_id)

    deleted_result = handle_customer_subscription_deleted(
        data_object, workshop_store, push_client=push_client
    )
    if deleted_result.invalid:
        return StripeWebhookReceiverResult(status_code=400, error="missing_customer")
    if deleted_result.unresolved:
        return StripeWebhookReceiverResult(status_code=200, unresolved_customer=True)

    return StripeWebhookReceiverResult(status_code=200, workshop_id=deleted_result.workshop_id)
