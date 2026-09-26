#!/usr/bin/env python3
"""stripe-webhook-http-entry-point-design.md(フェーズ続き183)で設計した、
`route_stripe_event()`(ルート解決のみ)と各Stripeイベントハンドラ
(`handle_subscription_activated()`・`handle_payment_succeeded()`・
`handle_payment_failed()`・`handle_subscription_deleted()`・
`handle_subscription_updated()`、最後者はフェーズ続き185で追加)を結ぶ統合エントリポイント
`receive_stripe_webhook()`。

位置づけ:
- 実Stripeアカウント接続・Webhookエンドポイント公開・Firestore書き込みは引き続き
  オーナー承認待ち(pending-approval.md参照)。本モジュールは実クラウド接続なしで
  検証可能な「判断・配線ロジック自体」のみを実装する。
- course-set-pasha/aircon-pashaの`stripe_webhook.py`の`receive_stripe_webhook()`と
  同じ位置づけだが、本ventureは状態モデルが`StoreDunningState`(dunning・復旧)・
  `StoreSubscriptionState`(トライアル後の初回プラン選択)・`StoreCancellationState`
  (契約終了、フェーズ続き184で追加)の3つに分かれているため、それぞれ専用の
  ストアProtocolを介して読み書きする(design 0節参照、3つ目の追加理由は
  subscription-deleted-event-routing-design.md 3節参照)。
"""

from __future__ import annotations

import json
import os
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
from cloud_function_subscription_cancelled_webhook import (
    OUTCOME_SEND_FAILED as CANCELLATION_OUTCOME_SEND_FAILED,
    StoreSubscriptionState as StoreCancellationState,
    handle_subscription_deleted,
    handle_subscription_updated,
)
from portal_session import PortalLinkProvider
from store_profile_store import (
    InMemoryStoreProfileStore,
    handle_checkout_session_completed,
    make_resolve_store_id_by_customer,
)
from subscription_plan_sync import PlanStoreProtocol, sync_plan_on_subscription_event
from stripe_webhook import (
    EVENT_CHECKOUT_SESSION_COMPLETED,
    EVENT_CUSTOMER_SUBSCRIPTION_DELETED,
    EVENT_CUSTOMER_SUBSCRIPTION_UPDATED,
    EVENT_INVOICE_PAYMENT_FAILED,
    EVENT_INVOICE_PAYMENT_SUCCEEDED,
    InMemoryStripeEventIdStore,
    StripeEventIdStoreProtocol,
    StripeEventRoute,
    route_stripe_event,
    verify_stripe_signature,
)


def clear_dunning_state_on_subscription_deleted(state: StoreDunningState) -> bool:
    """`customer.subscription.deleted`受信時、当該店舗のdunning進行状態
    (`payment_failure_detected_at`・`sent_event_keys`)を初期化し`suspension_reason`を
    `"cancelled"`にする(dunning-state-clear-on-subscription-deleted-design.md)。

    aircon-pasha/course-set-pasha/kura-pashaで見つかった同種バグ(解約確定後も決済失敗系の
    stateが残ったままになり、日次バッチが既に解約済みの店舗を誤って選出してしまう)が本venture
    自身の`EVENT_CUSTOMER_SUBSCRIPTION_DELETED`経路にも存在していたため対応する。猶予期間中
    (`payment_suspended`等の別状態にまだ至っていない)に契約が終了した場合、`dunning_store`の
    stateをクリアしないまま残すと、後日`cloud_function_send_dunning_notifications.py`の
    日次バッチが解約済みの店舗をリマインド・制限モード移行の対象として再選出してしまう。

    戻り値は実際に何か変更があったか(観測用、`payment_failure_detected_at`が設定済みまたは
    `sent_event_keys`が空でなかった場合`True`)。
    """
    changed = state.payment_failure_detected_at is not None or bool(state.sent_event_keys)
    state.payment_failure_detected_at = None
    state.sent_event_keys = set()
    if state.suspension_reason != "cancelled":
        changed = True
    state.suspension_reason = "cancelled"
    return changed


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


class StoreCancellationStateStoreProtocol(Protocol):
    def get_cancellation_state(self, store_id: str) -> Optional[StoreCancellationState]: ...

    def set_cancellation_state(self, store_id: str, state: StoreCancellationState) -> None: ...


class InMemoryStoreCancellationStateStore:
    """`StoreCancellationStateStoreProtocol`のインメモリ実装(デモ・テスト用)。

    subscription-deleted-event-routing-design.md 3節の通り、`subscription_store`
    (`cloud_function_subscription_activated_webhook.StoreSubscriptionState`)とは
    フィールド構成が異なる別クラスを保持するため、意図的に別のストアとして分離している。
    """

    def __init__(self) -> None:
        self._states: dict[str, StoreCancellationState] = {}

    def get_cancellation_state(self, store_id: str) -> Optional[StoreCancellationState]:
        return self._states.get(store_id)

    def set_cancellation_state(self, store_id: str, state: StoreCancellationState) -> None:
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
    cancellation_store: Optional[StoreCancellationStateStoreProtocol] = None,
    store_profile_store: Optional[PlanStoreProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版、design 2節)。

    署名検証 → JSONパース → `route_stripe_event()`によるイベント種別・store_id解決 →
    対応するハンドラ呼び出し・状態書き戻し、という流れを行う。各段階の安全側フォール
    バックはdesign 2節の番号付き手順の通り(course-set-pasha/aircon-pashaの
    `receive_stripe_webhook()`と同じ「未接続・未解決時はハンドラを呼ばず200」方針)。

    `portal_link_provider`(portal-session-provider-design.md、フェーズ続き193)は
    省略時`None`。`EVENT_CHECKOUT_SESSION_COMPLETED`(決済完了案内)・
    `EVENT_CUSTOMER_SUBSCRIPTION_UPDATED`(解約予約受理案内)の直前にのみ
    `get_portal_url(store_id)`を呼び都度URLを解決する(design 4節3.、stateには
    保存しない)。`None`の場合は各render関数側の安全側フォールバック文言に委ねる。

    `store_profile_store`(subscription-plan-sync-design.md、フェーズ続き220)は
    `EVENT_CUSTOMER_SUBSCRIPTION_UPDATED`受信のたびに`items.data[0].price.lookup_key`
    からプランを解決できれば`stores/{storeId}.plan`へ同期する(`cancellation_store`/
    `push_client`の要否とは独立)。省略時`None`はプラン同期をスキップするだけの
    安全側フォールバック。
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
        # checkout-initiation-flow-design.md 7節: stripe_customer_id・plan の
        # store_profile_store への書き込み(handle_checkout_session_completed())は、
        # customer.subscription.updated分岐のsync_plan_on_subscription_event()と同じく
        # 通知送信(subscription_store/push_client)の要否とは独立して行う。この配線が
        # 抜けていたため、統合エントリポイント経由ではstripe_customer_idの紐付け・plan
        # 書き込みが一度も行われず、resolve_store_id_by_customer()による以後のイベント
        # (invoice.payment_failed等)のstore_id解決が常に失敗する配線漏れがあった。
        if store_profile_store is not None:
            handle_checkout_session_completed(parsed, store_profile_store)
        if subscription_store is None or push_client is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        state = subscription_store.get_subscription_state(store_id)
        if state is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        portal_url = (
            portal_link_provider.get_portal_url(store_id)
            if portal_link_provider is not None
            else None
        )
        result = handle_subscription_activated(state, push_client, portal_url=portal_url)
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

    if route.event_type == EVENT_CUSTOMER_SUBSCRIPTION_DELETED:
        # subscription-deleted-event-routing-design.md 3節: activated用の
        # `subscription_store`とはフィールド構成が異なるため専用の`cancellation_store`を使う。
        # blocked-but-billing-detection-design.md 3節: store_profile_store側の
        # suspension_reasonは実運用では`cancellation_store`側と同一Firestore
        # ドキュメントのフィールドに収束する想定だが、本プロトタイプは別インスタンスの
        # ままのため、checkout.session.completed分岐のhandle_checkout_session_completed()・
        # customer.subscription.updated分岐のsync_plan_on_subscription_event()と同じ
        # 「通知の成否とは独立して書き込む」方針で、list_blocked_but_billing_candidates()が
        # 参照するstore_profile_store.suspension_reasonにも"cancelled"を反映する。
        if store_profile_store is not None:
            store_profile_store.set_suspension_reason(store_id, "cancelled")
        # dunning-state-clear-on-subscription-deleted-design.md: cancellation_store/
        # push_clientの要否・通知成否とは独立して、dunning_store側のstateもクリアする
        # (store_profile_storeのsuspension_reason書き込みと同じ「通知とは独立」方針)。
        if dunning_store is not None:
            dunning_state = dunning_store.get_dunning_state(store_id)
            if dunning_state is not None:
                clear_dunning_state_on_subscription_deleted(dunning_state)
                dunning_store.set_dunning_state(store_id, dunning_state)
        if cancellation_store is None or push_client is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        state = cancellation_store.get_cancellation_state(store_id)
        if state is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        result = handle_subscription_deleted(state, push_client)
        if result.outcome == CANCELLATION_OUTCOME_SEND_FAILED:
            return StripeWebhookReceiverResult(
                status_code=200, route=route, outcome=result.outcome
            )
        cancellation_store.set_cancellation_state(store_id, state)
        return StripeWebhookReceiverResult(status_code=200, route=route, outcome=result.outcome)

    if route.event_type == EVENT_CUSTOMER_SUBSCRIPTION_UPDATED:
        # customer-subscription-updated-event-routing-design.md 3節:
        # handle_subscription_updated()はstateを一切書き換えないため、書き戻しは行わない。
        data_object = parsed.get("data", {}).get("object", {})
        previous_attributes = parsed.get("data", {}).get("previous_attributes", {})
        # subscription-plan-sync-design.md(フェーズ続き220): プラン変更を伴わない
        # イベント(支払い方法変更等)でも毎回届くため、解約通知(cancellation_store/
        # push_client)の要否・成否とは独立に同期する。store_profile_store未指定時は
        # 何もしない(安全側、他イベントの既存フォールバックと同じ方針)。
        if store_profile_store is not None:
            sync_plan_on_subscription_event(store_profile_store, store_id, data_object)
        if cancellation_store is None or push_client is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        state = cancellation_store.get_cancellation_state(store_id)
        if state is None:
            return StripeWebhookReceiverResult(status_code=200, route=route)
        cancel_at_period_end_after = bool(data_object.get("cancel_at_period_end", False))
        cancel_at_period_end_before = bool(
            previous_attributes.get("cancel_at_period_end", cancel_at_period_end_after)
        )
        portal_url = (
            portal_link_provider.get_portal_url(store_id)
            if portal_link_provider is not None
            else None
        )
        result = handle_subscription_updated(
            state,
            cancel_at_period_end_before,
            cancel_at_period_end_after,
            push_client,
            portal_url=portal_url,
        )
        if result.outcome == CANCELLATION_OUTCOME_SEND_FAILED:
            return StripeWebhookReceiverResult(
                status_code=200, route=route, outcome=result.outcome
            )
        return StripeWebhookReceiverResult(status_code=200, route=route, outcome=result.outcome)

    return StripeWebhookReceiverResult(status_code=200, route=route)


def get_stripe_webhook_runtime_dependencies() -> dict:
    """`main()`が使う依存の既定値を組み立てる(design 8節、course-set-pasha/stripe_webhook.
    get_stripe_runtime_dependencies()と対称の構成)。

    `dunning_store`/`subscription_store`/`cancellation_store`/`store_profile_store`/
    `event_id_store`はいずれも本プロセス内で1つずつ生成する`InMemory*`実装(`store_profile_
    store`は`resolve_store_id_by_customer`が使う`InMemoryStoreProfileStore`インスタンスと
    同一のものを返す、フェーズ続き220で`subscription_plan_sync`用に追加)。実運用ではLINE側
    Cloud Function (cloud_function_process_event.py・cloud_function_webhook.py)と同一
    Firestoreの各コレクションを共有する想定だが、本プロセスでは別プロセス・別インスタンス
    として初期化されるため、呼び出しをまたいで状態が保持されない(course-set-pasha/
    aircon-pashaの同名ファクトリと同じ既知の限界)。

    `push_client`・`portal_link_provider`は意図的に返り値へ含めない。実LINE Messaging
    API接続(Channel Access Token取得)・実Stripe Billing Portalセッション作成API接続は
    いずれもオーナー承認待ちのため、`receive_stripe_webhook()`には`None`のまま渡り、
    `push_client`は各分岐の「`None`の場合はハンドラを呼ばず200を返す」既存の安全側
    フォールバックが、`portal_link_provider`は各render関数側の「`None`の場合は
    案内文言を省略・トークルーム返信導線に差し替える」安全側フォールバック(portal-
    session-provider-design.md 4節)がそれぞれ効く(course-set-pasha/aircon-pashaの
    stripe_webhook.get_stripe_runtime_dependencies()と同じ判断)。
    """
    store = InMemoryStoreProfileStore()
    return {
        "resolve_store_id_by_customer": make_resolve_store_id_by_customer(store),
        "dunning_store": InMemoryStoreDunningStateStore(),
        "subscription_store": InMemoryStoreSubscriptionStateStore(),
        "cancellation_store": InMemoryStoreCancellationStateStore(),
        "store_profile_store": store,
        "event_id_store": InMemoryStripeEventIdStore(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、Stripe版、design 8節)。

    `request.get_data()`・`request.headers.get("Stripe-Signature")`からのbody・署名ヘッダ
    取り出し配線を行い、`receive_stripe_webhook()`に委譲する(course-set-pasha/stripe_webhook.
    main()・本venture自身のcheckout_session.main()と対称の構成)。`webhook_secret`は
    環境変数`STRIPE_WEBHOOK_SECRET`から取得する(未設定時は空文字列となり、
    `verify_stripe_signature()`が必ず401を返す安全側)。
    """
    body = request.get_data()
    signature_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    result = receive_stripe_webhook(
        body, signature_header, webhook_secret, **get_stripe_webhook_runtime_dependencies()
    )

    if result.status_code == 200:
        return "OK", 200
    return (result.error or "error"), result.status_code
