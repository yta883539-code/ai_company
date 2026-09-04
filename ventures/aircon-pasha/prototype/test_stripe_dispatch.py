#!/usr/bin/env python3
"""stripe_dispatch.pyの単体テスト。
stripe-webhook-event-dispatch-design.md(フェーズ126)4節のテスト観点に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

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
