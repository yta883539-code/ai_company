#!/usr/bin/env python3
"""stripe-webhook-http-entry-point-design.md(フェーズ続き183)で設計した、
`route_stripe_event()`(ルート解決のみ)と各Stripeイベントハンドラ
(`handle_subscription_activated()`・`handle_payment_succeeded()`・
`handle_payment_failed()`)を結ぶ統合エントリポイント`receive_stripe_webhook()`。

位置づけ:
- 実Stripeアカウント接続・Webhookエンドポイント公開・Firestore書き込みは引き続き
  オーナー承認待ち(pending-approval.md参照)。本モジュールは実クラウド接続なしで
  検証可能な「判断・配線ロジック自体」のみを実装する。
- course-set-pasha/aircon-pashaの`stripe_webhook.py`の`receive_stripe_webhook()`と
  同じ位置づけだが、本ventureは状態モデルが`StoreDunningState`(dunning・復旧)と
  `StoreSubscriptionState`(トライアル後の初回プラン選択)の2つに分かれているため、
  それぞれ専用のストアProtocolを介して読み書きする(design 0節参照)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from cloud_function_payment_webhook import (
    OUTCOME_SEND_FAILED as PAYMENT_OUTCOME_SEND_FAILED,
    handle_payment_failed,
    handle_payment_succeeded,
)
from cloud_function_process_event import LinePushClient
from cloud_function_send_dunning_notifications import StoreDunningState
from cloud_function_subscription_activated_webhook import (
    OUTCOME_SEND_FAILED as SUBSCRIPTION_OUTCOME_SEND_FAILED,
    StoreSubscriptionState,
    handle_subscription_activated,
)
from stripe_webhook import (
    EVENT_CHECKOUT_SESSION_COMPLETED,
    EVENT_INVOICE_PAYMENT_FAILED,
    EVENT_INVOICE_PAYMENT_SUCCEEDED,
    StripeEventIdStoreProtocol,
    StripeEventRoute,
    route_stripe_event,
    verify_stripe_signature,
)


class StoreDunningStateStoreProtocol(Protocol):
    def get_dunning_state(self, store_id: str) -> Optional[StoreDunningState]: ...

    def set_dunning_state(self, store_id: str, state: StoreDunningState) -> None: ...


class InMemoryStoreDunningStateStore:
    """`StoreDunningStateStoreProtocol`のインメモリ実装(デモ・テスト用)。実Firestoreへの
    永続化は実GCPプロジェクト作成(オーナー承認待ち)後の課題として別途残る。"""

    def __init__(self) -> None:
        self._states: dict[str, StoreDunningState] = {}

    def get_dunning_state(self, store_id: str) -> Optional[StoreDunningState]:
        return self._states.get(store_id)

    def set_dunning_state(self, store_id: str, state: StoreDunningState) -> None:
        self._states[store_id] = state


class StoreSubscriptionStateStoreProtocol(Protocol):
    def get_subscription_state(self, store_id: str) -> Optional[StoreSubscriptionState]: ...

    def set_subscription_state(self, store_id: str, state: StoreSubscriptionState) -> None: ...


class InMemoryStoreSubscriptionStateStore:
    """`StoreSubscriptionStateStoreProtocol`のインメモリ実装(デモ・テスト用)。"""

    def __init__(self) -> None:
        self._states: dict[str, StoreSubscriptionState] = {}

    def get_subscription_state(self, store_id: str) -> Optional[StoreSubscriptionState]:
        return self._states.get(store_id)

    def set_subscription_state(self, store_id: str, state: StoreSubscriptionState) -> None:
        self._states[store_id] = state


@dataclass
class StripeWebhookReceiverResult:
    """`receive_stripe_webhook()`の結果(design 5節)。"""

    status_code: int
    route: Optional[StripeEventRoute] = None
    outcome: Optional[str] = None
    error: Optional[str] = None
    duplicate: bool = False


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    resolve_store_id_by_customer: Callable[[str], Optional[str]],
    dunning_store: Optional[StoreDunningStateStoreProtocol] = None,
    subscription_store: Optional[StoreSubscriptionStateStoreProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版、design 2節)。

    署名検証 → JSONパース → `route_stripe_event()`によるイベント種別・store_id解決 →
    対応するハンドラ呼び出し・状態書き戻し、という流れを行う。各段階の安全側フォール
    バックはdesign 2節の番号付き手順の通り(course-set-pasha/aircon-pashaの
    `receive_stripe_webhook()`と同じ「未接続・未解決時はハンドラを呼ばず200」方針)。
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

    route = route_stripe_event(
        parsed,
        resolve_store_id_by_customer=resolve_store_id_by_customer,
        event_id_store=event_id_store,
    )

    if route.duplicate:
        return StripeWebhookReceiverResult(status_code=200, route=route, duplicate=True)

    if route.ignored or route.store_id is None:
        return StripeWebhookReceiverResult(status_code=200, route=route)

    store_id = route.store_id

    if route.event_type == EVENT_CHECKOUT_SESSION_COMPLETED:
        if subscription_store is None or push_client is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        state = subscription_store.get_subscription_state(store_id)
        if state is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        result = handle_subscription_activated(state, push_client)
        if result.outcome == SUBSCRIPTION_OUTCOME_SEND_FAILED:
            return StripeWebhookReceiverResult(
                status_code=200, route=route, outcome=result.outcome
            )
        subscription_store.set_subscription_state(store_id, state)
        return StripeWebhookReceiverResult(status_code=200, route=route, outcome=result.outcome)

    if route.event_type == EVENT_INVOICE_PAYMENT_SUCCEEDED:
        if dunning_store is None or push_client is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        state = dunning_store.get_dunning_state(store_id)
        if state is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        result = handle_payment_succeeded(state, push_client)
        if result.outcome == PAYMENT_OUTCOME_SEND_FAILED:
            return StripeWebhookReceiverResult(
                status_code=200, route=route, outcome=result.outcome
            )
        dunning_store.set_dunning_state(store_id, state)
        return StripeWebhookReceiverResult(status_code=200, route=route, outcome=result.outcome)

    if route.event_type == EVENT_INVOICE_PAYMENT_FAILED:
        # design 3節: handle_payment_failed()はpush_clientを取らない(検知のみを行い、
        # 実際の通知はcloud_function_send_dunning_notifications.py側の担当)。
        if dunning_store is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        state = dunning_store.get_dunning_state(store_id)
        if state is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        state_changed = handle_payment_failed(state, resolved_now)
        if state_changed:
            dunning_store.set_dunning_state(store_id, state)
        return StripeWebhookReceiverResult(
            status_code=200, route=route, outcome=str(state_changed)
        )

    return StripeWebhookReceiverResult(status_code=200, route=route)
