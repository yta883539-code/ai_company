#!/usr/bin/env python3
"""stripe_dispatch.pyの単体テスト。
stripe-webhook-event-dispatch-design.md(フェーズ126)4節のテスト観点に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_webhook import InMemoryPortalLinkProvider  # noqa: E402
from deletion_candidate import InMemoryProfileDeletionCandidateStore  # noqa: E402
from payment_failure import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402
from payment_recovery_notification import (  # noqa: E402
    InMemoryLinePushClient as InMemoryRecoveryPushClient,
    LinePushDeliveryError as RecoveryLinePushDeliveryError,
)
from stripe_dispatch import StripeDispatchResult, dispatch_stripe_event  # noqa: E402
from subscription_cancellation_notification import (  # noqa: E402
    InMemoryLinePushClient as InMemoryCancellationPushClient,
    LinePushDeliveryError as CancellationLinePushDeliveryError,
)
from user_id_linking import InMemoryUserProfileStore, UserProfile  # noqa: E402

_CUSTOMER = "cus_ABC123"
_USER_ID = "U1"


class _FailingCancellationPushClient:
    def send_flex_message(self, user_id, alt_text, contents):
        raise CancellationLinePushDeliveryError("boom")


def _resolve_known(customer):
    return _USER_ID if customer == _CUSTOMER else None


def _resolve_none(customer):
    return None


class DispatchSubscriptionDeletedTest(unittest.TestCase):
    def test_marks_deletion_candidate_when_customer_resolves(self):
        store = InMemoryProfileDeletionCandidateStore()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.marked_user_ids, [_USER_ID])
        self.assertIsNotNone(store.get_deletion_candidate_at(_USER_ID))

    def test_clears_current_plan_id_when_plan_store_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        plan_store = _profile_store_with_user()
        plan_store.set_current_plan_id(_USER_ID, "スタンダード")
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, plan_store=plan_store
        )
        self.assertEqual(result.plan_cleared_user_ids, [_USER_ID])
        self.assertIsNone(plan_store.get_current_plan_id(_USER_ID))

    def test_plan_id_untouched_when_plan_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.plan_cleared_user_ids, [])

    def test_clears_blocked_but_billing_owner_notified_at_when_store_provided(self):
        # blocked-but-billing-owner-notification-design.md 6節「クリア配線」(フェーズ175)。
        store = InMemoryProfileDeletionCandidateStore()
        blocked_but_billing_store = _profile_store_with_user()
        blocked_but_billing_store.set_blocked_but_billing_owner_notified_at(
            _USER_ID, datetime(2026, 8, 20, tzinfo=timezone.utc)
        )
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            blocked_but_billing_store=blocked_but_billing_store,
        )
        self.assertEqual(result.blocked_but_billing_owner_notified_cleared_user_ids, [_USER_ID])
        self.assertIsNone(
            blocked_but_billing_store.get_blocked_but_billing_owner_notified_at(_USER_ID)
        )

    def test_blocked_but_billing_owner_notified_at_untouched_when_already_unset(self):
        store = InMemoryProfileDeletionCandidateStore()
        blocked_but_billing_store = _profile_store_with_user()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            blocked_but_billing_store=blocked_but_billing_store,
        )
        self.assertEqual(result.blocked_but_billing_owner_notified_cleared_user_ids, [])

    def test_blocked_but_billing_owner_notified_at_untouched_when_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.blocked_but_billing_owner_notified_cleared_user_ids, [])

    def test_clears_payment_failure_state_when_payment_store_provided(self):
        # payment-failure-state-clear-on-subscription-deleted-design.md(フェーズ272、
        # line-reservation-aiフェーズ続き273の横断確認)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_failure_detected_at(
            _USER_ID, datetime(2026, 8, 18, tzinfo=timezone.utc)
        )
        payment_store.set_payment_suspended_at(
            _USER_ID, datetime(2026, 8, 25, tzinfo=timezone.utc)
        )
        payment_store.set_payment_failure_reminder_sent_at(
            _USER_ID, datetime(2026, 8, 22, tzinfo=timezone.utc)
        )
        payment_store.set_payment_suspension_owner_notified_at(
            _USER_ID, datetime(2026, 8, 25, tzinfo=timezone.utc)
        )
        created = int(datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertEqual(result.payment_failure_cleared_on_deletion_user_ids, [_USER_ID])
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))
        self.assertIsNone(payment_store.get_payment_suspended_at(_USER_ID))
        self.assertIsNone(payment_store.get_payment_failure_reminder_sent_at(_USER_ID))
        self.assertIsNone(payment_store.get_payment_suspension_owner_notified_at(_USER_ID))

    def test_payment_failure_state_untouched_when_already_unset(self):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertEqual(result.payment_failure_cleared_on_deletion_user_ids, [])

    def test_payment_failure_state_untouched_when_payment_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.payment_failure_cleared_on_deletion_user_ids, [])

    def test_writes_subscription_canceled_at_when_payment_store_provided(self):
        # subscription-canceled-immediate-block-design.md(フェーズ275、kura-pasha
        # フェーズ188・course-set-pashaフェーズ258の横展開)。決済失敗が一度も検知
        # されていない(既に有料転換済みの)ユーザーの解約確定でも書き込まれることを
        # 確認する。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        event_created_at = datetime(2026, 8, 26, 12, 0, 0, tzinfo=timezone.utc)
        created = int(event_created_at.timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertEqual(result.subscription_canceled_user_ids, [_USER_ID])
        self.assertEqual(
            payment_store.get_subscription_canceled_at(_USER_ID), event_created_at
        )

    def test_subscription_canceled_at_untouched_when_payment_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.subscription_canceled_user_ids, [])

    def test_stale_deleted_event_skipped_when_older_than_already_applied_created(self):
        # subscription-event-out-of-order-guard-design.md(本フェーズ、course-set-pasha
        # フェーズ261のケースAの横展開)。より新しいcreated(T2)が既に反映済みの状態で、
        # それより古いdeleted(T1)がWebhookの配信順序入れ替わりにより後から届いても、
        # 既に有効な新契約を誤ってブロックしてはならない。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        newer_created_event = {
            "type": "customer.subscription.created",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_created_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertIsNone(payment_store.get_subscription_canceled_at(_USER_ID))

        older_deleted_event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_deleted_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertEqual(result.stale_subscription_deleted_user_ids, [_USER_ID])
        self.assertEqual(result.subscription_canceled_user_ids, [])
        self.assertIsNone(payment_store.get_subscription_canceled_at(_USER_ID))

    def test_stale_deleted_event_does_not_clear_payment_failure_state(self):
        # payment-failure-event-order-guard-design.md 4節「スコープ外」の是正
        # (course-set-pashaフェーズ263の横展開)。決済失敗検知中に、既により新しい
        # customer.subscription.createdが反映済みの状態で古いdeletedが遅延到着しても、
        # payment_failure_cleared_on_deletion_user_idsによるフィールドクリアをスキップする
        # (stale全体スキップへの統一)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_failure_detected_at(
            _USER_ID, datetime(2026, 8, 1, tzinfo=timezone.utc)
        )
        newer_created_event = {
            "type": "customer.subscription.created",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_created_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )

        older_deleted_event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_deleted_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertEqual(result.stale_subscription_deleted_user_ids, [_USER_ID])
        self.assertEqual(result.payment_failure_cleared_on_deletion_user_ids, [])
        self.assertIsNotNone(payment_store.get_payment_failure_detected_at(_USER_ID))

    def test_stale_deleted_event_sends_no_cancellation_notice(self):
        # payment-failure-event-order-guard-design.md 4節「スコープ外」の是正
        # (course-set-pashaフェーズ263の横展開)。既に有効な新契約の利用者に「ご契約が
        # 終了しました」という事実と異なる通知を送ってしまわないことを確認する。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        push_client = InMemoryCancellationPushClient()
        newer_created_event = {
            "type": "customer.subscription.created",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_created_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )

        older_deleted_event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_deleted_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            cancellation_push_client=push_client,
        )
        self.assertEqual(result.stale_subscription_deleted_user_ids, [_USER_ID])
        self.assertEqual(result.cancellation_notified_user_ids, [])
        self.assertEqual(result.cancellation_notification_failed_user_ids, [])
        self.assertEqual(len(push_client.sent), 0)

    def test_stale_deleted_event_does_not_clear_current_plan_id(self):
        # フェーズ283: subscription-event-out-of-order-guard-design.md 6節の
        # 「stale全体スキップ」方針をplan_store側にも拡張。既により新しいcustomer.
        # subscription.createdで有効化済みの利用者に対し、遅延到着した古いdeletedで
        # current_plan_idを誤ってNone(未契約)へ戻してしまわないことを確認する。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_current_plan_id(_USER_ID, "スタンダード")
        newer_created_event = {
            "type": "customer.subscription.created",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_created_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )

        older_deleted_event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_deleted_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            plan_store=payment_store,
        )
        self.assertEqual(result.stale_subscription_deleted_user_ids, [_USER_ID])
        self.assertEqual(result.plan_cleared_user_ids, [])
        self.assertEqual(payment_store.get_current_plan_id(_USER_ID), "スタンダード")

    def test_stale_deleted_event_does_not_clear_blocked_but_billing_owner_notified_at(self):
        # フェーズ283: 同上、blocked_but_billing_store側にも拡張。staleなdeletedで
        # blocked_but_billing_owner_notified_atを誤って早期クリアしてしまわないことを
        # 確認する(クリアされると、実際にはまだブロック中かつ契約継続中の候補として
        # 再度通知すべき状況を見逃すおそれがある)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_blocked_but_billing_owner_notified_at(
            _USER_ID, datetime(2026, 8, 20, tzinfo=timezone.utc)
        )
        newer_created_event = {
            "type": "customer.subscription.created",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_created_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )

        older_deleted_event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_deleted_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            blocked_but_billing_store=payment_store,
        )
        self.assertEqual(result.stale_subscription_deleted_user_ids, [_USER_ID])
        self.assertEqual(result.blocked_but_billing_owner_notified_cleared_user_ids, [])
        self.assertIsNotNone(
            payment_store.get_blocked_but_billing_owner_notified_at(_USER_ID)
        )

    def test_invalid_event_when_created_missing(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.invalid_events, ["customer.subscription.deleted"])
        self.assertEqual(result.marked_user_ids, [])
        self.assertIsNone(store.get_deletion_candidate_at(_USER_ID))

    def test_invalid_event_when_created_not_numeric(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.deleted",
            "created": "not-a-timestamp",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.invalid_events, ["customer.subscription.deleted"])

    def test_invalid_event_when_created_is_bool(self):
        # bool は int のサブクラスのため明示的に除外する分岐を確認する
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.deleted",
            "created": True,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.invalid_events, ["customer.subscription.deleted"])


class DispatchSubscriptionCreatedTest(unittest.TestCase):
    def test_clears_deletion_candidate_unconditionally(self):
        store = InMemoryProfileDeletionCandidateStore()
        store.set_deletion_candidate_at(_USER_ID, datetime(2027, 8, 25, tzinfo=timezone.utc))
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])
        self.assertIsNone(store.get_deletion_candidate_at(_USER_ID))

    def test_clears_even_when_nothing_was_set_idempotent(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])

    def test_clears_subscription_canceled_at_when_payment_store_provided(self):
        # subscription-canceled-immediate-block-design.md(フェーズ275)。再契約後に
        # 生成が永久にブロックされたままにならないよう、customer.subscription.created
        # 受信でsubscription_canceled_atをクリアする。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_subscription_canceled_at(
            _USER_ID, datetime(2026, 8, 20, tzinfo=timezone.utc)
        )
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertIsNone(payment_store.get_subscription_canceled_at(_USER_ID))

    def test_subscription_canceled_at_untouched_when_payment_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        # payment_store未指定でも例外を送出せず正常終了することを確認する。
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])

    def test_stale_created_event_skipped_when_older_than_already_applied_deleted(self):
        # subscription-event-out-of-order-guard-design.md(本フェーズ、course-set-pasha
        # フェーズ261のケースBの横展開)。より新しいdeleted(T2)が既に反映済み(解約確定済み)
        # の状態で、それより古いcreated(T1、初回契約イベントのリトライ再送等)が後から
        # 届いても、既に解約済みの利用者のブロックを誤って解除してはならない。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        newer_deleted_event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_deleted_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertIsNotNone(payment_store.get_subscription_canceled_at(_USER_ID))

        older_created_event = {
            "type": "customer.subscription.created",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_created_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertEqual(result.stale_subscription_created_user_ids, [_USER_ID])
        self.assertIsNotNone(payment_store.get_subscription_canceled_at(_USER_ID))

    def test_created_without_created_field_still_applies_for_backward_compatibility(self):
        # event.createdが取得できない(既存呼び出し経路と同じ形式の)createdイベントは、
        # 順序判定不能として従来通り適用される(後方互換の回帰確認)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        deleted_event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            deleted_event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertIsNotNone(payment_store.get_subscription_canceled_at(_USER_ID))

        created_event_without_timestamp = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            created_event_without_timestamp,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertEqual(result.stale_subscription_created_user_ids, [])
        self.assertIsNone(payment_store.get_subscription_canceled_at(_USER_ID))

    def test_syncs_current_plan_id_when_plan_store_provided_and_lookup_key_known(self):
        store = InMemoryProfileDeletionCandidateStore()
        plan_store = _profile_store_with_user()
        event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "items": {"data": [{"price": {"lookup_key": "aircon_pasha_busy"}}]},
                }
            },
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, plan_store=plan_store
        )
        self.assertEqual(result.plan_synced_user_ids, [_USER_ID])
        self.assertEqual(plan_store.get_current_plan_id(_USER_ID), "繁忙期対応")

    def test_plan_id_untouched_when_lookup_key_unknown(self):
        store = InMemoryProfileDeletionCandidateStore()
        plan_store = _profile_store_with_user()
        event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "items": {"data": [{"price": {"lookup_key": "not_a_plan"}}]},
                }
            },
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, plan_store=plan_store
        )
        self.assertEqual(result.plan_synced_user_ids, [])
        self.assertIsNone(plan_store.get_current_plan_id(_USER_ID))

    def test_no_plan_sync_attempted_when_plan_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.created",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "items": {"data": [{"price": {"lookup_key": "aircon_pasha_small"}}]},
                }
            },
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.plan_synced_user_ids, [])


class DispatchSubscriptionUpdatedTest(unittest.TestCase):
    def test_clears_when_status_active(self):
        store = InMemoryProfileDeletionCandidateStore()
        store.set_deletion_candidate_at(_USER_ID, datetime(2027, 8, 25, tzinfo=timezone.utc))
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "active"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])
        self.assertIsNone(store.get_deletion_candidate_at(_USER_ID))

    def test_clears_when_status_trialing(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "trialing"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])

    def test_does_nothing_when_status_past_due(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "past_due"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [])
        self.assertEqual(result.marked_user_ids, [])

    def test_does_nothing_when_status_canceled(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "canceled"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [])

    def test_syncs_current_plan_id_on_upgrade_regardless_of_deletion_candidate_status(self):
        # design: current_plan_idは「customer.subscription.*受信のたびに」更新する対象で、
        # 削除候補化(status)の判定条件とは独立している(past_dueでもプラン変更自体は
        # 起こりうる)ことを確認する。
        store = InMemoryProfileDeletionCandidateStore()
        plan_store = _profile_store_with_user()
        plan_store.set_current_plan_id(_USER_ID, "スモール")
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "status": "past_due",
                    "items": {
                        "data": [{"price": {"lookup_key": "aircon_pasha_standard"}}]
                    },
                }
            },
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, plan_store=plan_store
        )
        self.assertEqual(result.cleared_user_ids, [])
        self.assertEqual(result.plan_synced_user_ids, [_USER_ID])
        self.assertEqual(plan_store.get_current_plan_id(_USER_ID), "スタンダード")


def _profile_store_with_user() -> InMemoryUserProfileStore:
    store = InMemoryUserProfileStore()
    store.save(
        _USER_ID,
        UserProfile(
            business_name="テスト洗浄社",
            business_type="独立系",
            email="test@example.com",
            linked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
    )
    return store


class DispatchInvoicePaymentFailedTest(unittest.TestCase):
    def test_marks_payment_failure_detected_when_customer_resolves(self):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        created = int(datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "invoice.payment_failed",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertEqual(result.payment_failure_detected_user_ids, [_USER_ID])
        self.assertEqual(
            payment_store.get_payment_failure_detected_at(_USER_ID),
            datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc),
        )

    def test_invalid_event_when_created_missing(self):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        event = {
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertEqual(result.invalid_events, ["invoice.payment_failed"])
        self.assertEqual(result.payment_failure_detected_user_ids, [])
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))

    def test_ignored_when_payment_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "invoice.payment_failed",
            "created": int(datetime(2026, 8, 28, tzinfo=timezone.utc).timestamp()),
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.ignored_types, ["invoice.payment_failed"])
        self.assertEqual(result.payment_failure_detected_user_ids, [])

    def test_sends_detection_notification_and_marks_when_push_client_provided(self):
        # フェーズ147: push_client指定時はhandle_payment_failure_detected()経由で
        # 実際に通知を送信してから状態を書き込む。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        push_client = InMemoryLinePushClient()
        created = int(datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "invoice.payment_failed",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            push_client=push_client,
        )
        self.assertEqual(result.payment_failure_detected_user_ids, [_USER_ID])
        self.assertEqual(result.payment_failure_notification_failed_user_ids, [])
        self.assertEqual(
            payment_store.get_payment_failure_detected_at(_USER_ID),
            datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(push_client.sent), 1)
        self.assertEqual(push_client.sent[0][0], _USER_ID)

    def test_notification_send_failure_leaves_state_untouched(self):
        # フェーズ147: 送信失敗時は状態を変更せず、Webhookリトライでの再試行に委ねる。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()

        class _FailingPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise LinePushDeliveryError("boom")

        created = int(datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "invoice.payment_failed",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            push_client=_FailingPushClient(),
        )
        self.assertEqual(result.payment_failure_detected_user_ids, [])
        self.assertEqual(result.payment_failure_notification_failed_user_ids, [_USER_ID])
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))

    def test_stale_payment_failed_event_skipped_when_older_than_already_applied_succeeded(
        self,
    ):
        # payment-failure-event-order-guard-design.md(フェーズ281、subscription-event-
        # out-of-order-guard-design.md〈フェーズ280〉のdunning側への横展開)。より新しい
        # invoice.payment_succeeded(T2)が既に反映済みの状態で、それより古いinvoice.
        # payment_failed(T1)がWebhookの配信順序入れ替わりにより後から届いても、既に
        # 決済済みの利用者を誤って督促対象へ書き換えてはならない。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        newer_succeeded_event = {
            "type": "invoice.payment_succeeded",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_succeeded_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        older_failed_event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_failed_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertEqual(result.stale_payment_failed_user_ids, [_USER_ID])
        self.assertEqual(result.payment_failure_detected_user_ids, [])
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))

    def test_notification_not_sent_when_payment_failed_event_is_stale(self):
        # 上記のstale判定は、push_client指定時(実送信配線)でも通知の送信自体を
        # 行わない(状態と矛盾する通知を送らないため)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        newer_succeeded_event = {
            "type": "invoice.payment_succeeded",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_succeeded_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        push_client = InMemoryLinePushClient()
        older_failed_event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_failed_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            push_client=push_client,
        )
        self.assertEqual(result.stale_payment_failed_user_ids, [_USER_ID])
        self.assertEqual(result.payment_failure_detected_user_ids, [])
        self.assertEqual(result.payment_failure_notification_failed_user_ids, [])
        self.assertEqual(len(push_client.sent), 0)


class DispatchInvoicePaymentSucceededTest(unittest.TestCase):
    def test_clears_failure_and_suspended_state(self):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_failure_detected_at(
            _USER_ID, datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        payment_store.set_payment_suspended_at(
            _USER_ID, datetime(2026, 9, 4, tzinfo=timezone.utc)
        )
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertEqual(result.payment_recovered_user_ids, [_USER_ID])
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))
        self.assertIsNone(payment_store.get_payment_suspended_at(_USER_ID))

    def test_idempotent_when_nothing_was_set(self):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, payment_store=payment_store,
        )
        self.assertEqual(result.payment_recovered_user_ids, [])

    def test_ignored_when_payment_store_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.ignored_types, ["invoice.payment_succeeded"])
        self.assertEqual(result.payment_recovered_user_ids, [])

    def test_sends_recovered_from_suspension_notification_when_recovery_push_client_provided(
        self,
    ):
        # フェーズ148: recovery_push_client指定時はhandle_payment_succeeded()経由で
        # 制限モードからの復旧通知を送信してから状態をクリアする。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_failure_detected_at(
            _USER_ID, datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        payment_store.set_payment_suspended_at(
            _USER_ID, datetime(2026, 9, 4, tzinfo=timezone.utc)
        )
        recovery_push_client = InMemoryRecoveryPushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            recovery_push_client=recovery_push_client,
        )
        self.assertEqual(result.payment_recovered_user_ids, [_USER_ID])
        self.assertEqual(result.payment_recovery_notification_failed_user_ids, [])
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))
        self.assertIsNone(payment_store.get_payment_suspended_at(_USER_ID))
        self.assertEqual(len(recovery_push_client.sent), 1)
        self.assertEqual(recovery_push_client.sent[0][0], _USER_ID)

    def test_silent_reset_sends_no_notification_when_recovery_push_client_provided(self):
        # フェーズ148: 検知はされているがリマインド未送信(まだ何も通知していない)場合は
        # 通知を送らず状態のみリセットする(OUTCOME_SILENT_RESET)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_failure_detected_at(
            _USER_ID, datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        recovery_push_client = InMemoryRecoveryPushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            recovery_push_client=recovery_push_client,
        )
        self.assertEqual(result.payment_recovered_user_ids, [_USER_ID])
        self.assertEqual(len(recovery_push_client.sent), 0)
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))

    def test_confirmed_in_grace_when_only_detection_notified_at_is_set(self):
        # フェーズ274: 検知時通知(段階1)のみ送信済み(3日前リマインドはまだ)の状態でも、
        # payment_store経由でdispatch_stripe_event()がhandle_payment_succeeded()へ
        # payment_failure_detection_notified_atを渡すことを確認する(通知が届く=
        # OUTCOME_SILENT_RESETではなくOUTCOME_CONFIRMED_IN_GRACEになる)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_failure_detected_at(
            _USER_ID, datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        payment_store.set_payment_failure_detection_notified_at(
            _USER_ID, datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        recovery_push_client = InMemoryRecoveryPushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            recovery_push_client=recovery_push_client,
        )
        self.assertEqual(result.payment_recovered_user_ids, [_USER_ID])
        self.assertEqual(len(recovery_push_client.sent), 1)
        self.assertIsNone(payment_store.get_payment_failure_detected_at(_USER_ID))
        self.assertIsNone(
            payment_store.get_payment_failure_detection_notified_at(_USER_ID)
        )

    def test_no_dunning_when_recovery_push_client_provided_and_nothing_was_set(self):
        # フェーズ148: 決済失敗を検知したことがない通常の課金成功では通知も状態変更もしない。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        recovery_push_client = InMemoryRecoveryPushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            recovery_push_client=recovery_push_client,
        )
        self.assertEqual(result.payment_recovered_user_ids, [])
        self.assertEqual(result.payment_recovery_notification_failed_user_ids, [])
        self.assertEqual(len(recovery_push_client.sent), 0)

    def test_recovery_notification_send_failure_leaves_state_untouched(self):
        # フェーズ148: 送信失敗時は状態を変更せず、Webhookリトライでの再試行に委ねる
        # (payment_failure.pyのhandle_payment_failure_detected()と対称の設計)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_failure_detected_at(
            _USER_ID, datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        payment_store.set_payment_suspended_at(
            _USER_ID, datetime(2026, 9, 4, tzinfo=timezone.utc)
        )

        class _FailingRecoveryPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise RecoveryLinePushDeliveryError("boom")

        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            recovery_push_client=_FailingRecoveryPushClient(),
        )
        self.assertEqual(result.payment_recovered_user_ids, [])
        self.assertEqual(result.payment_recovery_notification_failed_user_ids, [_USER_ID])
        self.assertIsNotNone(payment_store.get_payment_failure_detected_at(_USER_ID))
        self.assertIsNotNone(payment_store.get_payment_suspended_at(_USER_ID))

    def test_stale_payment_succeeded_event_skipped_when_older_than_already_applied_failed(
        self,
    ):
        # payment-failure-event-order-guard-design.md(フェーズ281)。より新しいinvoice.
        # payment_failed(T2)が既に反映済みの状態で、それより古いinvoice.payment_succeeded
        # (T1)がWebhookの配信順序入れ替わりにより後から届いても、既に決済失敗した利用者の
        # 督促を誤って解除してはならない。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        newer_failed_event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_failed_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        older_succeeded_event = {
            "type": "invoice.payment_succeeded",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_succeeded_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        self.assertEqual(result.stale_payment_succeeded_user_ids, [_USER_ID])
        self.assertEqual(result.payment_recovered_user_ids, [])
        self.assertIsNotNone(payment_store.get_payment_failure_detected_at(_USER_ID))

    def test_recovery_notification_not_sent_when_payment_succeeded_event_is_stale(self):
        # 上記のstale判定は、recovery_push_client指定時(実送信配線)でも復旧通知の送信自体を
        # 行わない(状態と矛盾する通知を送らないため)。
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _profile_store_with_user()
        newer_failed_event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_200,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        dispatch_stripe_event(
            newer_failed_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
        )
        recovery_push_client = InMemoryRecoveryPushClient()
        older_succeeded_event = {
            "type": "invoice.payment_succeeded",
            "created": 1_700_000_100,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            older_succeeded_event,
            store=store,
            resolve_user_id=_resolve_known,
            payment_store=payment_store,
            recovery_push_client=recovery_push_client,
        )
        self.assertEqual(result.stale_payment_succeeded_user_ids, [_USER_ID])
        self.assertEqual(result.payment_recovered_user_ids, [])
        self.assertEqual(len(recovery_push_client.sent), 0)


class DispatchSubscriptionCancellationNotificationTest(unittest.TestCase):
    """subscription-cancellation-notification-design.md(フェーズ184)対応。"""

    def test_sends_cancellation_completed_notification_on_deleted(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryCancellationPushClient()
        created = int(datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, cancellation_push_client=push
        )
        self.assertEqual(result.cancellation_notified_user_ids, [_USER_ID])
        self.assertEqual(result.cancellation_notification_failed_user_ids, [])
        self.assertEqual(len(push.sent), 1)

    def test_no_cancellation_notification_when_push_client_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        created = int(datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cancellation_notified_user_ids, [])

    def test_records_failure_when_deleted_notification_send_fails(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = _FailingCancellationPushClient()
        created = int(datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, cancellation_push_client=push
        )
        self.assertEqual(result.cancellation_notified_user_ids, [])
        self.assertEqual(result.cancellation_notification_failed_user_ids, [_USER_ID])

    def test_sends_scheduled_notification_when_cancel_at_period_end_becomes_true(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryCancellationPushClient()
        period_end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "status": "active",
                    "cancel_at_period_end": True,
                    "current_period_end": period_end,
                },
                "previous_attributes": {"cancel_at_period_end": False},
            },
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, cancellation_push_client=push
        )
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [_USER_ID])
        self.assertEqual(result.cancellation_rescheduled_notified_user_ids, [])
        self.assertEqual(len(push.sent), 1)

    def test_sends_rescheduled_notification_when_cancel_at_period_end_becomes_false(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryCancellationPushClient()
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {"customer": _CUSTOMER, "status": "active", "cancel_at_period_end": False},
                "previous_attributes": {"cancel_at_period_end": True},
            },
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, cancellation_push_client=push
        )
        self.assertEqual(result.cancellation_rescheduled_notified_user_ids, [_USER_ID])
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [])

    def test_no_update_notification_when_previous_attributes_missing_key(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryCancellationPushClient()
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {"customer": _CUSTOMER, "status": "active"},
                "previous_attributes": {"items": {}},
            },
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, cancellation_push_client=push
        )
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [])
        self.assertEqual(result.cancellation_rescheduled_notified_user_ids, [])
        self.assertEqual(len(push.sent), 0)

    def test_no_update_notification_when_push_client_not_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {"customer": _CUSTOMER, "status": "active", "cancel_at_period_end": True},
                "previous_attributes": {"cancel_at_period_end": False},
            },
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [])

    def test_records_failure_when_update_notification_send_fails(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = _FailingCancellationPushClient()
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {"customer": _CUSTOMER, "status": "active", "cancel_at_period_end": True},
                "previous_attributes": {"cancel_at_period_end": False},
            },
        }
        result = dispatch_stripe_event(
            event, store=store, resolve_user_id=_resolve_known, cancellation_push_client=push
        )
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [])
        self.assertEqual(result.cancellation_update_notification_failed_user_ids, [_USER_ID])

    def test_scheduled_message_reflects_suspension_when_payment_store_suspended(self):
        """subscription-cancellation-scheduled-message-suspension-consistency-design.md
        (フェーズ185)。既存の`payment_store`引数がcancel_at_period_end変化通知にも
        配線されていることを確認する。"""
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryCancellationPushClient()
        payment_store = _profile_store_with_user()
        payment_store.set_payment_suspended_at(
            _USER_ID, datetime(2026, 8, 20, tzinfo=timezone.utc)
        )
        period_end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "status": "active",
                    "cancel_at_period_end": True,
                    "current_period_end": period_end,
                },
                "previous_attributes": {"cancel_at_period_end": False},
            },
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            cancellation_push_client=push,
            payment_store=payment_store,
            portal_link_provider=InMemoryPortalLinkProvider("https://example.test/portal"),
        )
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [_USER_ID])
        _, _, contents = push.sent[0]
        text = contents["body"]["contents"][0]["text"]
        self.assertIn("作業完了報告・お手入れ案内の生成は既に一時停止しています", text)
        self.assertNotIn("作業完了報告・お手入れ案内の生成に制限はありません", text)

    def test_scheduled_message_default_when_payment_store_provided_but_not_suspended(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryCancellationPushClient()
        payment_store = _profile_store_with_user()
        period_end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "status": "active",
                    "cancel_at_period_end": True,
                    "current_period_end": period_end,
                },
                "previous_attributes": {"cancel_at_period_end": False},
            },
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            cancellation_push_client=push,
            payment_store=payment_store,
            portal_link_provider=InMemoryPortalLinkProvider("https://example.test/portal"),
        )
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [_USER_ID])
        _, _, contents = push.sent[0]
        text = contents["body"]["contents"][0]["text"]
        self.assertIn("作業完了報告・お手入れ案内の生成に制限はありません", text)

    def test_scheduled_message_default_when_payment_store_not_provided(self):
        """`payment_store`未指定時はフェーズ184時点と同じ挙動(制限モード判定なし)。"""
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryCancellationPushClient()
        period_end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": _CUSTOMER,
                    "status": "active",
                    "cancel_at_period_end": True,
                    "current_period_end": period_end,
                },
                "previous_attributes": {"cancel_at_period_end": False},
            },
        }
        result = dispatch_stripe_event(
            event,
            store=store,
            resolve_user_id=_resolve_known,
            cancellation_push_client=push,
            portal_link_provider=InMemoryPortalLinkProvider("https://example.test/portal"),
        )
        self.assertEqual(result.cancellation_scheduled_notified_user_ids, [_USER_ID])
        _, _, contents = push.sent[0]
        text = contents["body"]["contents"][0]["text"]
        self.assertIn("作業完了報告・お手入れ案内の生成に制限はありません", text)


class DispatchIgnoredAndUnresolvedTest(unittest.TestCase):
    def test_ignored_type_is_recorded_and_no_handler_called(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "invoice.paid",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.ignored_types, ["invoice.paid"])
        self.assertEqual(result.marked_user_ids, [])
        self.assertEqual(result.cleared_user_ids, [])

    def test_unresolved_customer_is_recorded(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": "cus_UNKNOWN"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_none)
        self.assertEqual(result.unresolved_customers, ["cus_UNKNOWN"])
        self.assertEqual(result.cleared_user_ids, [])

    def test_default_result_is_all_empty(self):
        self.assertEqual(StripeDispatchResult(), StripeDispatchResult())


if __name__ == "__main__":
    unittest.main()
