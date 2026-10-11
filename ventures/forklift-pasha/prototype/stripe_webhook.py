#!/usr/bin/env python3
"""Stripe Webhookの署名検証・HTTPエントリポイント(stripe-webhook-entry-point-design.md
フェーズ127)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジックと`checkout.session.completed`受信時の紐付け処理のみを切り出したモジュール
(aircon-pasha/course-set-pashaのprototype/stripe_webhook.pyと同じ位置づけ)。

フェーズ127時点では`checkout.session.completed`の受信・署名検証のみに限定していたが、
フェーズ128で`customer.subscription.updated`受信時のplan_id同期
(`handle_customer_subscription_updated()`、stripe-subscription-updated-dispatch-
design.md)を追加し、フェーズ129で`customer.subscription.deleted`受信時の
`canceled_at`書き込み(`handle_customer_subscription_deleted()`、
subscription-canceled-immediate-block-design.md相当)を追加した。決済失敗検知
(`payment_failure.py`相当)・解約完了案内の送信等はまだ一切存在しないため、それ以外の
イベント種別は常に200(受理・無視)を返す。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from plan_id_resolution import (
    sync_plan_id_on_subscription_event,
    write_plan_id_from_checkout_session_metadata,
)
from trial_management import FleetOperatorStoreProtocol, InMemoryFleetOperatorStore


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """`Stripe-Signature`ヘッダを検証する(aircon-pasha/course-set-pashaの
    verify_stripe_signature()と同一のアルゴリズム、design 2節)。

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
    """handle_checkout_session_completed()の結果(design 3節)。"""

    linked: bool
    internal_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    error: Optional[str] = None
    plan_id_written: bool = False
    upgraded_at_written: bool = False


def handle_checkout_session_completed(
    event: dict,
    store: FleetOperatorStoreProtocol,
    *,
    now: Optional[datetime] = None,
) -> CheckoutSessionLinkResult:
    """`checkout.session.completed`イベントから`client_reference_id`(= `internal_id`、
    checkout_session.build_checkout_session_params()が設定した値)・`customer`
    (= `stripe_customer_id`)・`metadata.plan`を取り出し、`store`へ書き込む
    (stripe-webhook-entry-point-design.md 3節)。

    aircon-pashaと異なり、対応する`fleet_operator`の事前存在チェックは行わない
    (design 3節「本venture固有の設計判断」参照)。`internal_id`・`stripe_customer_id`の
    いずれかが欠落・非文字列・空文字列の場合のみ異常系として書き込みを行わない。
    """
    data_object = event.get("data", {}).get("object", {})
    internal_id = data_object.get("client_reference_id")
    stripe_customer_id = data_object.get("customer")

    if (
        not isinstance(internal_id, str)
        or not internal_id
        or not isinstance(stripe_customer_id, str)
        or not stripe_customer_id
    ):
        return CheckoutSessionLinkResult(linked=False, error="missing_fields")

    store.set_stripe_customer_id(internal_id, stripe_customer_id)

    plan_id_written = write_plan_id_from_checkout_session_metadata(
        store, internal_id, data_object.get("metadata", {})
    )

    upgraded_at_written = False
    if store.get_upgraded_at(internal_id) is None:
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        store.set_upgraded_at(internal_id, resolved_now)
        upgraded_at_written = True

    return CheckoutSessionLinkResult(
        linked=True,
        internal_id=internal_id,
        stripe_customer_id=stripe_customer_id,
        plan_id_written=plan_id_written,
        upgraded_at_written=upgraded_at_written,
    )


@dataclass
class SubscriptionUpdatedSyncResult:
    """handle_customer_subscription_updated()の結果
    (stripe-subscription-updated-dispatch-design.md 2節)。"""

    synced: bool
    internal_id: Optional[str] = None
    plan_id_written: bool = False
    error: Optional[str] = None


def handle_customer_subscription_updated(
    event: dict,
    store: FleetOperatorStoreProtocol,
) -> SubscriptionUpdatedSyncResult:
    """`customer.subscription.updated`イベントからplan_idの同期のみを行う
    (stripe-subscription-updated-dispatch-design.md 2節)。

    `customer`(= `stripe_customer_id`)を取り出し、
    `store.get_internal_id_by_stripe_customer_id()`で`internal_id`を逆引きする
    (checkout.session.completed受信時にstripe_webhook.handle_checkout_session_completed()
    が書き込んだ逆引きインデックスに依存する)。逆引きできない場合(未知の
    stripe_customer_id、または本venture未着手のCustomer Portal経由のプラン変更以外の
    経路で作成されたcustomer)は`error="unknown_customer"`として同期を行わない。

    plan_idの解決・差分書き込み自体は`plan_id_resolution.sync_plan_id_on_subscription_
    event()`にそのまま委譲する(lookup_keyが未知・欠落、または既存値と同一の場合は
    `plan_id_written=False`)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")

    if not isinstance(stripe_customer_id, str) or not stripe_customer_id:
        return SubscriptionUpdatedSyncResult(synced=False, error="missing_customer")

    internal_id = store.get_internal_id_by_stripe_customer_id(stripe_customer_id)
    if internal_id is None:
        return SubscriptionUpdatedSyncResult(synced=False, error="unknown_customer")

    plan_id_written = sync_plan_id_on_subscription_event(store, internal_id, data_object)

    return SubscriptionUpdatedSyncResult(
        synced=True, internal_id=internal_id, plan_id_written=plan_id_written
    )


@dataclass
class SubscriptionDeletedResult:
    """handle_customer_subscription_deleted()の結果
    (subscription-canceled-immediate-block-design.md相当、フェーズ129)。"""

    canceled: bool
    internal_id: Optional[str] = None
    error: Optional[str] = None


def handle_customer_subscription_deleted(
    event: dict,
    store: FleetOperatorStoreProtocol,
    *,
    now: Optional[datetime] = None,
) -> SubscriptionDeletedResult:
    """`customer.subscription.deleted`イベントから`canceled_at`を書き込む。

    kura-pasha/course-set-pasha/aircon-pashaで発見された欠落(有料転換済み
    〈upgraded_atが非null〉のユーザーが解約後も`is_generation_paused()`の対象に
    ならず無期限に生成を使い続けられる)が本venture自体にも存在することを確認し、
    同型の修正として追加した。`handle_customer_subscription_updated()`と同じく
    `customer`から`internal_id`を逆引きする。決済失敗の有無によらず常に`canceled_at`
    を書き込む(aircon-pashaのdesign「3. 修正内容」と同じ方針)。逆引きできない場合は
    `error="unknown_customer"`として書き込みを行わない。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")

    if not isinstance(stripe_customer_id, str) or not stripe_customer_id:
        return SubscriptionDeletedResult(canceled=False, error="missing_customer")

    internal_id = store.get_internal_id_by_stripe_customer_id(stripe_customer_id)
    if internal_id is None:
        return SubscriptionDeletedResult(canceled=False, error="unknown_customer")

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    store.set_canceled_at(internal_id, resolved_now)

    return SubscriptionDeletedResult(canceled=True, internal_id=internal_id)


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果(design 1節)。"""

    status_code: int
    checkout_link_result: Optional[CheckoutSessionLinkResult] = None
    subscription_updated_result: Optional[SubscriptionUpdatedSyncResult] = None
    subscription_deleted_result: Optional[SubscriptionDeletedResult] = None
    error: Optional[str] = None


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: FleetOperatorStoreProtocol,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント。生のリクエストボディ(bytes)を受け取り、
    署名検証(verify_stripe_signature)・JSONパース・`checkout.session.completed`の
    振り分けまでを行う(design 1節、本venture未着手のイベント種別は常に200で無視する)。

    - 署名検証に失敗した場合は401相当を返し、JSONパース以降の配線を一切行わない。
    - 署名検証後にbodyをJSONとしてパースする。パース失敗、またはパース結果がdictでない
      場合は400相当を返す。
    - イベント種別が`checkout.session.completed`の場合のみ
      `handle_checkout_session_completed()`へ振り分ける。それ以外のイベント種別は
      Stripe側の再送ループを避けるため200(受理・無視)として扱う。
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

    event_type = parsed.get("type")

    if event_type == "checkout.session.completed":
        checkout_link_result = handle_checkout_session_completed(
            parsed, store, now=resolved_now
        )
        return StripeWebhookReceiverResult(
            status_code=200, checkout_link_result=checkout_link_result
        )

    if event_type == "customer.subscription.updated":
        subscription_updated_result = handle_customer_subscription_updated(parsed, store)
        return StripeWebhookReceiverResult(
            status_code=200, subscription_updated_result=subscription_updated_result
        )

    if event_type == "customer.subscription.deleted":
        subscription_deleted_result = handle_customer_subscription_deleted(
            parsed, store, now=resolved_now
        )
        return StripeWebhookReceiverResult(
            status_code=200, subscription_deleted_result=subscription_deleted_result
        )

    return StripeWebhookReceiverResult(status_code=200)


def get_stripe_runtime_dependencies() -> dict:
    """receive_stripe_webhook()に渡す依存関係一式を組み立てるファクトリ
    (aircon-pasha/course-set-pashaのget_stripe_runtime_dependencies()と同じ位置づけ)。

    `store`: `InMemoryFleetOperatorStore()`を1つ生成する。プロセス起動ごとに初期化
    されるため、実Cloud Functions環境では呼び出しをまたいで紐付け・plan_id・
    upgraded_atが保持されない(他ventureと同じ既知の限界、実Firestore接続後に解消)。
    """
    return {"store": InMemoryFleetOperatorStore()}


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    実リクエストオブジェクトからのbody(`request.get_data()`)・署名ヘッダ
    (`request.headers.get("Stripe-Signature")`)取り出し配線のみを行い、
    receive_stripe_webhook()に委譲する。`webhook_secret`は環境変数
    `STRIPE_WEBHOOK_SECRET`から取得する。
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
