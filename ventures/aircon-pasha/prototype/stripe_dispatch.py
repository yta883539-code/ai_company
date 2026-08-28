#!/usr/bin/env python3
"""
stripe-webhook-event-dispatch-design.md(フェーズ126)で設計した、Stripe Webhookの
イベント種別ディスパッチロジックを実行可能なコードに落とし込んだもの。

位置づけ:
- `stripe_customer_id → user_id`の解決(実Firestoreクエリ等)、および実際のHTTPエントリ
  ポイント(`verify_stripe_signature()`との結線)はいずれもdesign 5節「未解決事項・次の課題」
  のとおり本ventureにまだ存在せず、実Stripeアカウント接続後の課題として引き続き残る。本
  モジュールはイベント種別に応じた振り分けロジックのみを、実Firestore接続なしで検証可能な
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
    PaymentFailureStoreProtocol,
    clear_payment_failure_on_success,
    mark_payment_failure_detected,
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


def dispatch_stripe_event(
    event: dict,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    payment_store: Optional[PaymentFailureStoreProtocol] = None,
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
        return result

    if event_type == _SUBSCRIPTION_CREATED:
        clear_deletion_candidate_on_subscription_reactivated(store, user_id)
        result.cleared_user_ids.append(user_id)
        return result

    if event_type == _SUBSCRIPTION_UPDATED:
        status = data_object.get("status")
        if status in _REACTIVATED_STATUSES:
            clear_deletion_candidate_on_subscription_reactivated(store, user_id)
            result.cleared_user_ids.append(user_id)
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
        mark_payment_failure_detected(payment_store, user_id, event_time)
        result.payment_failure_detected_user_ids.append(user_id)
        return result

    # _INVOICE_PAYMENT_SUCCEEDED
    if clear_payment_failure_on_success(payment_store, user_id):
        result.payment_recovered_user_ids.append(user_id)
    return result
