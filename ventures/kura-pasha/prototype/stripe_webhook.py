"""Stripe Webhookの署名検証・`checkout.session.completed`受信処理
(stripe-webhook-checkout-completed-design.md フェーズ51)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジック・`checkout.session.completed`ハンドラ・両者を結ぶHTTPエントリポイントのみを
切り出したモジュール。`usage_counter_workshop.py`・`checkout_session.py`とは独立した
別ファイルとし、既存コードには一切影響を与えない。

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
class StripeWebhookReceiverResult:
    """design 3節。"""

    status_code: int
    workshop_id: Optional[str] = None
    ignored_type: Optional[str] = None
    error: Optional[str] = None


def receive_stripe_webhook(
    body: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    workshop_store: Optional[WorkshopStoreProtocol] = None,
) -> StripeWebhookReceiverResult:
    """design 3節。署名検証→JSONパース→`checkout.session.completed`のみディスパッチする
    薄いHTTPエントリポイント。未対応のイベント種別は無視して200を返す(Stripe側の
    無限リトライを避ける、course-set-pasha/aircon-pashaと同じ方針)。
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
    if event_type != "checkout.session.completed":
        return StripeWebhookReceiverResult(status_code=200, ignored_type=event_type)

    data_object = event.get("data", {}).get("object", {})
    if workshop_store is None:
        return StripeWebhookReceiverResult(status_code=400, error="missing_workshop_store")

    result = handle_checkout_session_completed(data_object, workshop_store)
    if result.invalid:
        return StripeWebhookReceiverResult(status_code=400, error="missing_client_reference_id")

    return StripeWebhookReceiverResult(status_code=200, workshop_id=result.workshop_id)
