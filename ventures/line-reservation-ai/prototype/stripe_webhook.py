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
- `event_id_store`(フェーズ続き179追加): stripe-event-idempotency-design.mdで設計した、
  `event.id`によるべき等性チェック。aircon-pashaがフェーズ177・course-set-pashaが
  フェーズ151で先行実装したのと同じ設計(venture固有の差異なし)を横展開したもの。本
  ventureは`receive_stripe_webhook()`相当の統合エントリポイントがまだ存在しない
  (design「残課題」のとおり次回以降の課題)ため、現時点で唯一の共通経路である
  `route_stripe_event()`にべき等性チェックを組み込む。指定時、同一`event.id`を持つ
  イベントが2回目以降届いた場合は`resolve_store_id_by_customer()`の呼び出しも含め
  一切の解決処理を行わずduplicate=Trueを返す。省略時(`None`)は従来通りべき等性
  チェックを行わない(既存呼び出し経路への後方互換措置)。

設計の参照元: stripe-webhook-signature-verification-design.md・
stripe-webhook-event-dispatch-design.md・stripe-event-idempotency-design.md
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Callable, Optional


class StripeEventIdStoreProtocol:
    """stripe-event-idempotency-design.mdで設計した、`event.id`単位の処理済み
    フラグを保持するストアのインターフェース(aircon-pasha/course-set-pashaの
    同名Protocolと同一の契約)。"""

    def has_processed(self, event_id: str) -> bool:
        raise NotImplementedError

    def mark_processed(self, event_id: str) -> None:
        raise NotImplementedError


class InMemoryStripeEventIdStore:
    """`StripeEventIdStoreProtocol`のインメモリ実装(デモ・テスト用)。実Firestore等への
    永続化は実GCPプロジェクト作成(オーナー承認待ち)後の課題として別途残る。"""

    def __init__(self) -> None:
        self._processed_event_ids: set[str] = set()

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


# route_stripe_event()が扱うイベント種別(stripe-webhook-event-dispatch-design.md 1節)。
# EVENT_CUSTOMER_SUBSCRIPTION_DELETED(フェーズ続き184、
# subscription-deleted-event-routing-design.md)で4種目として追加。
# EVENT_CUSTOMER_SUBSCRIPTION_UPDATED(フェーズ続き185、
# customer-subscription-updated-event-routing-design.md)で5種目として追加。
EVENT_CHECKOUT_SESSION_COMPLETED = "checkout.session.completed"
EVENT_INVOICE_PAYMENT_SUCCEEDED = "invoice.payment_succeeded"
EVENT_INVOICE_PAYMENT_FAILED = "invoice.payment_failed"
EVENT_CUSTOMER_SUBSCRIPTION_DELETED = "customer.subscription.deleted"
EVENT_CUSTOMER_SUBSCRIPTION_UPDATED = "customer.subscription.updated"

_ROUTABLE_EVENT_TYPES = (
    EVENT_CHECKOUT_SESSION_COMPLETED,
    EVENT_INVOICE_PAYMENT_SUCCEEDED,
    EVENT_INVOICE_PAYMENT_FAILED,
    EVENT_CUSTOMER_SUBSCRIPTION_DELETED,
    EVENT_CUSTOMER_SUBSCRIPTION_UPDATED,
)


@dataclass
class StripeEventRoute:
    """route_stripe_event()の結果(design 3節)。

    store_idがNoneでない場合のみ、呼び出し側は対応するハンドラ(handle_payment_succeeded()/
    handle_subscription_activated()/handle_payment_failed())へ処理を委ねられる。

    `duplicate`(フェーズ続き179追加): `event_id_store`指定時、`event.id`が既に処理済み
    だったため以降の解決処理を一切行わずに返した場合`True`。この場合`event_type`以外の
    フィールドは常にデフォルト値(`None`/`False`)のままとなる。
    """

    event_type: Optional[str]
    store_id: Optional[str] = None
    customer_id: Optional[str] = None
    ignored: bool = False
    unresolved_customer: bool = False
    duplicate: bool = False
    event_id: Optional[str] = None


def route_stripe_event(
    event: dict,
    *,
    resolve_store_id_by_customer: Callable[[str], Optional[str]],
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
) -> StripeEventRoute:
    """design 3節のとおり、イベント種別の判定とstore_id解決のみを行う。

    実際のFirestore状態の読み込み・ハンドラ呼び出し・書き戻しは呼び出し側の責務
    (design「残課題」参照)。

    `event_id_store`はstripe-event-idempotency-design.md対応(フェーズ続き179追加)。
    指定時、`event.get("id")`が既に処理済みであれば`resolve_store_id_by_customer()`を
    含む以降の処理を一切行わず`duplicate=True`のルートを返す(副作用ゼロ)。`id`が
    欠落・非文字列の場合はチェックをスキップし従来通り処理する(安全側)。省略時
    (`None`)はべき等性チェックを一切行わない(既存呼び出し経路への後方互換措置)。
    処理済みとして記録するのは`ignored`(対象外イベント種別)も含めた全ての非重複
    イベントで、aircon-pashaの`receive_stripe_webhook()`と同じ方針(Stripe側の再送
    ループを避けるため、対象外イベントも一度見たら処理済みとして扱う)を踏襲する。
    """
    event_type = event.get("type")
    event_id = event.get("id")
    check_idempotency = event_id_store is not None and isinstance(event_id, str)
    if check_idempotency and event_id_store.has_processed(event_id):
        return StripeEventRoute(event_type=event_type, duplicate=True)

    if event_type not in _ROUTABLE_EVENT_TYPES:
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeEventRoute(event_type=event_type, ignored=True, event_id=event_id)

    data_object = event.get("data", {}).get("object", {})

    if event_type == EVENT_CHECKOUT_SESSION_COMPLETED:
        # design 2節: client_reference_idに店舗のuser_idが直接入っているため、
        # resolve_store_id_by_customer()は呼ばない。
        store_id = data_object.get("client_reference_id")
        customer_id = data_object.get("customer")
        if not store_id:
            route = StripeEventRoute(
                event_type=event_type,
                customer_id=customer_id,
                unresolved_customer=True,
            )
        else:
            route = StripeEventRoute(
                event_type=event_type, store_id=store_id, customer_id=customer_id
            )
    else:
        customer_id = data_object.get("customer")
        if not customer_id:
            route = StripeEventRoute(event_type=event_type, unresolved_customer=True)
        else:
            store_id = resolve_store_id_by_customer(customer_id)
            if store_id is None:
                route = StripeEventRoute(
                    event_type=event_type,
                    customer_id=customer_id,
                    unresolved_customer=True,
                )
            else:
                route = StripeEventRoute(
                    event_type=event_type, store_id=store_id, customer_id=customer_id
                )

    if check_idempotency:
        event_id_store.mark_processed(event_id)
    route.event_id = event_id
    return route
