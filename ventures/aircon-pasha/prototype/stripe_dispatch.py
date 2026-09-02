#!/usr/bin/env python3
"""
stripe-webhook-event-dispatch-design.md(フェーズ126)で設計した、Stripe Webhookの
イベント種別ディスパッチロジックを実行可能なコードに落とし込んだもの。

位置づけ:
- `stripe_customer_id → user_id`の解決はuser_id_linking.pyの`get_user_id_by_stripe_
  customer_id()`(インメモリ実装)として、実際のHTTPエントリポイント
  (`verify_stripe_signature()`との結線)はstripe_webhook.pyの`receive_stripe_webhook()`
  (フェーズ127)としてそれぞれ実装済み。実Firestore接続・実Stripeアカウント接続のみが
  引き続きオーナー承認待ちの課題として残る(2026-09-02 フェーズ173点検で本docstringの
  記載漏れ〈design 5節「未解決事項・次の課題」が既に解消済みだった点が未反映〉を訂正)。
  本モジュールはイベント種別に応じた振り分けロジックを、実Firestore接続なしで検証可能な
  形で実装する(`deletion_candidate.py`と同じ「Protocol/Callableの差し替えで実接続を
  後回しにする」パターンの踏襲)。

設計の参照元: stripe-webhook-event-dispatch-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, List, Optional

from deletion_candidate import (
    ProfileDeletionCandidateStoreProtocol,
    clear_deletion_candidate_on_subscription_reactivated,
    mark_deletion_candidate_on_subscription_deleted,
)
from payment_failure import (
    LinePushClient,
    PaymentFailureStoreProtocol,
    clear_payment_failure_on_success,
    handle_payment_failure_detected,
    mark_payment_failure_detected,
)
from payment_failure_reminder_scheduler import PaymentFailureReminderUserState
from payment_recovery_notification import (
    OUTCOME_SEND_FAILED,
    LinePushClient as RecoveryPushClient,
    handle_payment_succeeded,
)
from subscription_plan_sync import (
    CurrentPlanStoreProtocol,
    clear_current_plan_on_subscription_deleted,
    sync_current_plan_on_subscription_event,
)

# design 1節: ディスパッチ対象のStripeイベント種別
_SUBSCRIPTION_DELETED = "customer.subscription.deleted"
_SUBSCRIPTION_CREATED = "customer.subscription.created"
_SUBSCRIPTION_UPDATED = "customer.subscription.updated"
# payment-failure-dunning-design.md(フェーズ139)6節・フェーズ140で追加。
_INVOICE_PAYMENT_FAILED = "invoice.payment_failed"
_INVOICE_PAYMENT_SUCCEEDED = "invoice.payment_succeeded"
_HANDLED_TYPES = {
    _SUBSCRIPTION_DELETED,
    _SUBSCRIPTION_CREATED,
    _SUBSCRIPTION_UPDATED,
    _INVOICE_PAYMENT_FAILED,
    _INVOICE_PAYMENT_SUCCEEDED,
}

# design 5節: updated時に削除候補フラグを解除する対象status
_REACTIVATED_STATUSES = {"active", "trialing"}


@dataclass
class StripeDispatchResult:
    """design 2節: `dispatch_stripe_event()`の結果集約。"""

    marked_user_ids: List[str] = field(default_factory=list)
    cleared_user_ids: List[str] = field(default_factory=list)
    ignored_types: List[str] = field(default_factory=list)
    unresolved_customers: List[str] = field(default_factory=list)
    invalid_events: List[str] = field(default_factory=list)
    # payment-failure-dunning-design.md(フェーズ139)対応、フェーズ140で追加。
    payment_failure_detected_user_ids: List[str] = field(default_factory=list)
    payment_recovered_user_ids: List[str] = field(default_factory=list)
    # フェーズ147追加: push_client指定時、決済失敗検知通知の送信に失敗したuser_id
    # (状態は書き込まれておらず、Webhookリトライでの再試行に委ねる想定)。
    payment_failure_notification_failed_user_ids: List[str] = field(default_factory=list)
    # フェーズ148追加: recovery_push_client指定時、復旧通知(制限モードからの復旧/
    # 猶予期間中の完了通知)の送信に失敗したuser_id(状態は書き込まれておらず、
    # Webhookリトライでの再試行に委ねる想定)。
    payment_recovery_notification_failed_user_ids: List[str] = field(default_factory=list)
    # フェーズ161追加: plan_store指定時、customer.subscription.created/updatedの
    # `items.data[0].price.lookup_key`からプランIDを解決し`current_plan_id`へ書き込めた
    # user_id(解決できなかった場合はここに記録されず、既存の`current_plan_id`を維持する)。
    plan_synced_user_ids: List[str] = field(default_factory=list)
    # フェーズ161追加: plan_store指定時、customer.subscription.deleted受信により
    # `current_plan_id`をNone(未契約)へ戻したuser_id。
    plan_cleared_user_ids: List[str] = field(default_factory=list)


def dispatch_stripe_event(
    event: dict,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    payment_store: Optional[PaymentFailureStoreProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    recovery_push_client: Optional[RecoveryPushClient] = None,
    plan_store: Optional[CurrentPlanStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> StripeDispatchResult:
    """design 1節: Stripe Webhookイベント1件を受け取り、種別に応じて
    `deletion_candidate.py`の関数群へ振り分ける。`now`は`clear_...`系呼び出し自体には
    使わないが、将来のロギング拡張に備えて引数として残す(design記載の署名踏襲)。

    `payment_store`はpayment-failure-dunning-design.md(フェーズ139)対応(フェーズ140で
    追加)。`invoice.payment_failed`/`invoice.payment_succeeded`受信時のみ参照し、
    `store`(削除候補化用)とは別のFirestoreフィールド群を扱う想定のため独立した引数とした。
    未指定(`None`)の場合、これら2種別は`ignored_types`として扱う(呼び出し元が
    `user_profile_store`をまだ用意していない既存の呼び出し経路(customer.subscription.*
    専用)に影響を与えないための後方互換措置)。

    `push_client`はdesign 4・6節「決済失敗検知時(段階1)通知の実送信配線」対応
    (フェーズ147追加)。指定時、`invoice.payment_failed`受信時に
    `handle_payment_failure_detected()`(payment_failure.py)経由で実際に通知を送信して
    から状態を書き込む。未指定(`None`)の場合は従来通り`mark_payment_failure_detected()`を
    直接呼び、通知は送信しない(既存呼び出し経路への後方互換措置)。
    `recovery_push_client`はdesign 4節「猶予期間中に決済が成功した場合の復旧通知」対応
    (フェーズ148追加)。指定時、`invoice.payment_succeeded`受信時に`payment_store`から
    読み取った現在状態を`PaymentFailureReminderUserState`へ詰め替え、
    `handle_payment_succeeded()`(payment_recovery_notification.py・フェーズ146)経由で
    実際に復旧通知を送信してから状態をクリアする。未指定(`None`)の場合は従来通り
    `clear_payment_failure_on_success()`を直接呼ぶのみで、通知は送信しない(既存呼び出し
    経路への後方互換措置)。`push_client`とは別引数にした理由: `LinePushDeliveryError`が
    モジュールごとに別クラスとして定義されている既存の慣習(本ファイル冒頭のdocstring・
    payment_failure.pyのモジュールdocstring参照)を踏まえ、フェーズ147時点で挙がっていた
    「例外クラスの共通化」「専用の別引数を設ける」という2案のうち、他の各種スケジューラも
    同様に自分専用のpush_client・例外クラスを持つ既存パターンとの一貫性を優先し、後者
    (別引数)を採用した。

    `plan_store`はuser-account-linking-design.md 4節・subscription-cancellation-flow-
    design.md「当月生成回数上限の適用方法」対応(フェーズ161追加)。指定時、
    `customer.subscription.created`/`.updated`受信のたびに`data.object`から
    プランID(`items.data[0].price.lookup_key`経由)を解決できれば`current_plan_id`へ
    書き込み、`customer.subscription.deleted`受信時は`current_plan_id`を`None`
    (未契約)へ戻す(subscription_plan_sync.py参照)。未指定(`None`)の場合はこれまで
    通りプランIDの同期を一切行わない(既存呼び出し経路への後方互換措置)。`payment_store`
    と同じく専用のInMemoryストアは新設せず、`InMemoryUserProfileStore`が
    `CurrentPlanStoreProtocol`を構造的に(duck typing)満たす設計とした。
    """
    result = StripeDispatchResult()
    event_type = event.get("type")

    if event_type not in _HANDLED_TYPES:
        if event_type is not None:
            result.ignored_types.append(event_type)
        return result

    data_object = event.get("data", {}).get("object", {})
    customer = data_object.get("customer")
    user_id = resolve_user_id(customer) if customer is not None else None

    if user_id is None:
        result.unresolved_customers.append(customer)
        return result

    if event_type == _SUBSCRIPTION_DELETED:
        created = event.get("created")
        if not isinstance(created, (int, float)) or isinstance(created, bool):
            result.invalid_events.append(event_type)
            return result
        event_time = datetime.fromtimestamp(created, tz=timezone.utc)
        mark_deletion_candidate_on_subscription_deleted(store, user_id, event_time)
        result.marked_user_ids.append(user_id)
        if plan_store is not None:
            clear_current_plan_on_subscription_deleted(plan_store, user_id)
            result.plan_cleared_user_ids.append(user_id)
        return result

    if event_type == _SUBSCRIPTION_CREATED:
        clear_deletion_candidate_on_subscription_reactivated(store, user_id)
        result.cleared_user_ids.append(user_id)
        if plan_store is not None:
            if sync_current_plan_on_subscription_event(plan_store, user_id, data_object):
                result.plan_synced_user_ids.append(user_id)
        return result

    if event_type == _SUBSCRIPTION_UPDATED:
        status = data_object.get("status")
        if status in _REACTIVATED_STATUSES:
            clear_deletion_candidate_on_subscription_reactivated(store, user_id)
            result.cleared_user_ids.append(user_id)
        if plan_store is not None:
            if sync_current_plan_on_subscription_event(plan_store, user_id, data_object):
                result.plan_synced_user_ids.append(user_id)
        return result

    if payment_store is None:
        result.ignored_types.append(event_type)
        return result

    if event_type == _INVOICE_PAYMENT_FAILED:
        created = event.get("created")
        if not isinstance(created, (int, float)) or isinstance(created, bool):
            result.invalid_events.append(event_type)
            return result
        event_time = datetime.fromtimestamp(created, tz=timezone.utc)
        if push_client is None:
            mark_payment_failure_detected(payment_store, user_id, event_time)
            result.payment_failure_detected_user_ids.append(user_id)
            return result
        detection_result = handle_payment_failure_detected(
            payment_store, user_id, event_time, push_client
        )
        if detection_result.notified:
            result.payment_failure_detected_user_ids.append(user_id)
        else:
            result.payment_failure_notification_failed_user_ids.append(user_id)
        return result

    # _INVOICE_PAYMENT_SUCCEEDED
    if recovery_push_client is None:
        if clear_payment_failure_on_success(payment_store, user_id):
            result.payment_recovered_user_ids.append(user_id)
        return result

    state = PaymentFailureReminderUserState(
        user_id=user_id,
        payment_failure_detected_at=payment_store.get_payment_failure_detected_at(user_id),
        payment_suspended_at=payment_store.get_payment_suspended_at(user_id),
        payment_failure_reminder_sent_at=(
            payment_store.get_payment_failure_reminder_sent_at(user_id)
        ),
    )
    recovery_result = handle_payment_succeeded(state, payment_store, recovery_push_client)
    if recovery_result.outcome == OUTCOME_SEND_FAILED:
        result.payment_recovery_notification_failed_user_ids.append(user_id)
    elif recovery_result.state_reset:
        result.payment_recovered_user_ids.append(user_id)
    return result
