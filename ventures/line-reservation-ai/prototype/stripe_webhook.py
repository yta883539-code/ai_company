#!/usr/bin/env python3
"""stripe-webhook-signature-verification-design.md(フェーズ続き158)で設計した、Stripe
Webhook受信時の`Stripe-Signature`ヘッダ署名検証。

位置づけ:
- 実Stripeアカウント作成・Webhookエンドポイント登録・`webhook_secret`の取得はいずれも
  「アカウント作成」に該当し、オーナー承認待ち(pending-approval.md参照)。本モジュールは
  それとは独立に、公開されているStripe公式の署名検証アルゴリズムのみを実HTTPリクエスト
  なしで検証可能にしたもの(aircon-pasha/course-set-pashaの同名モジュールと同一アルゴリズム)。
- `route_stripe_event()`(フェーズ続き159で追加)は、stripe-webhook-event-dispatch-
  design.mdで設計したイベント種別判定・store_id解決のみを行う薄い関数。実際に
  `handle_payment_succeeded()`等のハンドラを呼び出し、Firestoreへ状態を読み書きする層は
  design「残課題」のとおり本モジュールのスコープ外で、次回以降の課題として残る。

設計の参照元: stripe-webhook-signature-verification-design.md・
stripe-webhook-event-dispatch-design.md
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Callable, Optional


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """design 2節のアルゴリズムをそのまま実装する。

    未検証時(ヘッダ欠落・形式不正・署名不一致・許容範囲外)はいずれも`False`を返す
    「安全側で拒否」方針(本venture既存の`verify_line_signature()`と同じ考え方)。
    """
    if not sig_header:
        return False

    timestamp: Optional[str] = None
    v1_signatures: list[str] = []
    for part in sig_header.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t" and timestamp is None:
            timestamp = value
        elif key == "v1" and value:
            v1_signatures.append(value)

    if not timestamp or not v1_signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    current_time = time.time() if now is None else now
    if abs(current_time - timestamp_int) > tolerance_seconds:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()

    return any(
        hmac.compare_digest(expected_signature, candidate)
        for candidate in v1_signatures
    )


# route_stripe_event()が扱う3種(stripe-webhook-event-dispatch-design.md 1節)。
EVENT_CHECKOUT_SESSION_COMPLETED = "checkout.session.completed"
EVENT_INVOICE_PAYMENT_SUCCEEDED = "invoice.payment_succeeded"
EVENT_INVOICE_PAYMENT_FAILED = "invoice.payment_failed"

_ROUTABLE_EVENT_TYPES = (
    EVENT_CHECKOUT_SESSION_COMPLETED,
    EVENT_INVOICE_PAYMENT_SUCCEEDED,
    EVENT_INVOICE_PAYMENT_FAILED,
)


@dataclass
class StripeEventRoute:
    """route_stripe_event()の結果(design 3節)。

    store_idがNoneでない場合のみ、呼び出し側は対応するハンドラ(handle_payment_succeeded()/
    handle_subscription_activated()/handle_payment_failed())へ処理を委ねられる。
    """

    event_type: Optional[str]
    store_id: Optional[str] = None
    customer_id: Optional[str] = None
    ignored: bool = False
    unresolved_customer: bool = False


def route_stripe_event(
    event: dict,
    *,
    resolve_store_id_by_customer: Callable[[str], Optional[str]],
) -> StripeEventRoute:
    """design 3節のとおり、イベント種別の判定とstore_id解決のみを行う。

    実際のFirestore状態の読み込み・ハンドラ呼び出し・書き戻しは呼び出し側の責務
    (design「残課題」参照)。
    """
    event_type = event.get("type")
    if event_type not in _ROUTABLE_EVENT_TYPES:
        return StripeEventRoute(event_type=event_type, ignored=True)

    data_object = event.get("data", {}).get("object", {})

    if event_type == EVENT_CHECKOUT_SESSION_COMPLETED:
        # design 2節: client_reference_idに店舗のuser_idが直接入っているため、
        # resolve_store_id_by_customer()は呼ばない。
        store_id = data_object.get("client_reference_id")
        customer_id = data_object.get("customer")
        if not store_id:
            return StripeEventRoute(
                event_type=event_type,
                customer_id=customer_id,
                unresolved_customer=True,
            )
        return StripeEventRoute(
            event_type=event_type, store_id=store_id, customer_id=customer_id
        )

    customer_id = data_object.get("customer")
    if not customer_id:
        return StripeEventRoute(event_type=event_type, unresolved_customer=True)

    store_id = resolve_store_id_by_customer(customer_id)
    if store_id is None:
        return StripeEventRoute(
            event_type=event_type, customer_id=customer_id, unresolved_customer=True
        )
    return StripeEventRoute(
        event_type=event_type, store_id=store_id, customer_id=customer_id
    )
