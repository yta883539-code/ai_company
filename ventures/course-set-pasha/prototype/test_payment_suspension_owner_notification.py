#!/usr/bin/env python3
"""payment_suspension_owner_notification.pyのテスト。
payment-suspension-owner-notification-design.md 3節の抽出条件を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from payment_suspension_owner_notification import (  # noqa: E402
    DEFAULT_GRACE_PERIOD_DAYS,
    OWNER_LINE_USER_ID_PLACEHOLDER,
    PaymentSuspensionCustomerState,
    format_payment_suspension_owner_notification_message,
    select_due_payment_suspension_owner_notifications,
    send_payment_suspension_owner_notifications,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402


class _FakeUsageCounter:
    """set_payment_suspension_owner_notified_at()呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.owner_notified_at: dict[str, datetime] = {}

    def set_payment_suspension_owner_notified_at(self, user_id: str, notified_at: datetime) -> None:
        self.owner_notified_at[user_id] = notified_at


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class SelectDuePaymentSuspensionOwnerNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 29, 15, 0, 0)

    def test_exactly_7_days_elapsed_is_due(self) -> None:
        # 猶予期間ちょうど経過(制限モード移行の瞬間): 対象。
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=7)
        )
        self.assertEqual(
            select_due_payment_suspension_owner_notifications([customer], self.now), [customer]
        )

    def test_more_than_7_days_elapsed_is_due(self) -> None:
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=10)
        )
        self.assertEqual(
            select_due_payment_suspension_owner_notifications([customer], self.now), [customer]
        )

    def test_less_than_7_days_elapsed_is_not_due(self) -> None:
        # まだ猶予期間中(制限モード未移行): payment_failure_reminder_schedulerの
        # 担当範囲であり、本モジュールの対象外。
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=6)
        )
        self.assertEqual(select_due_payment_suspension_owner_notifications([customer], self.now), [])

    def test_already_notified_is_not_due(self) -> None:
        customer = PaymentSuspensionCustomerState(
            user_id="u1",
            payment_failure_detected_at=self.now - timedelta(days=10),
            payment_suspension_owner_notified_at=self.now - timedelta(days=1),
        )
        self.assertEqual(select_due_payment_suspension_owner_notifications([customer], self.now), [])

    def test_no_detected_at_is_not_due(self) -> None:
        customer = PaymentSuspensionCustomerState(user_id="u1", payment_failure_detected_at=None)
        self.assertEqual(select_due_payment_suspension_owner_notifications([customer], self.now), [])

    def test_custom_grace_period(self) -> None:
        customer_due = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=14)
        )
        customer_too_early = PaymentSuspensionCustomerState(
            user_id="u2", payment_failure_detected_at=self.now - timedelta(days=10)
        )
        due = select_due_payment_suspension_owner_notifications(
            [customer_due, customer_too_early], self.now, grace_period_days=14
        )
        self.assertEqual(due, [customer_due])

    def test_preserves_input_order_for_multiple_due_customers(self) -> None:
        customer1 = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=8)
        )
        customer2 = PaymentSuspensionCustomerState(
            user_id="u2", payment_failure_detected_at=self.now - timedelta(days=20)
        )
        self.assertEqual(
            select_due_payment_suspension_owner_notifications([customer1, customer2], self.now),
            [customer1, customer2],
        )


class FormatPaymentSuspensionOwnerNotificationMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 29, 15, 0, 0)

    def test_embeds_user_id_and_elapsed_days(self) -> None:
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=10)
        )
        text = format_payment_suspension_owner_notification_message(customer, self.now)
        self.assertIn("u1", text)
        self.assertIn("10日", text)
        self.assertIn("制限モードへ移行しました", text)

    def test_embeds_custom_grace_period_days(self) -> None:
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=14)
        )
        text = format_payment_suspension_owner_notification_message(
            customer, self.now, grace_period_days=14
        )
        self.assertIn("猶予期間(14日)", text)


class SendPaymentSuspensionOwnerNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 29, 15, 0, 0)

    def test_sends_to_owner_and_records_notified_at(self) -> None:
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=10)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        result = send_payment_suspension_owner_notifications([customer], self.now, usage_counter, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(usage_counter.owner_notified_at["u1"], self.now)
        # 送信先は顧客のuser_idではなく固定のオーナー宛であることを確認する。
        self.assertEqual(push.sent[0][0], OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertIn("u1", push.sent[0][1])

    def test_skips_not_due_customers(self) -> None:
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=2)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        result = send_payment_suspension_owner_notifications([customer], self.now, usage_counter, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(push.sent, [])
        self.assertNotIn("u1", usage_counter.owner_notified_at)

    def test_failed_send_does_not_record_notified_at(self) -> None:
        customer = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=10)
        )
        usage_counter = _FakeUsageCounter()
        result = send_payment_suspension_owner_notifications(
            [customer], self.now, usage_counter, _FailingLinePushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertNotIn("u1", usage_counter.owner_notified_at)

    def test_multiple_due_customers_each_get_own_message(self) -> None:
        customer1 = PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=8)
        )
        customer2 = PaymentSuspensionCustomerState(
            user_id="u2", payment_failure_detected_at=self.now - timedelta(days=20)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        result = send_payment_suspension_owner_notifications(
            [customer1, customer2], self.now, usage_counter, push
        )

        self.assertEqual(result.sent, ["u1", "u2"])
        self.assertIn("8日", push.sent[0][1])
        self.assertIn("20日", push.sent[1][1])

    def test_default_grace_period_matches_dunning_design(self) -> None:
        # デフォルト値がpayment-failure-dunning-design.mdの猶予7日と一致していることを
        # 固定する回帰テスト。
        self.assertEqual(DEFAULT_GRACE_PERIOD_DAYS, 7)


class StripeWebhookPaymentFailureDetectedToOwnerNotificationWiringTest(unittest.TestCase):
    """stripe_webhook.dispatch_stripe_event()が`invoice.payment_failed`受信時に書き込む
    payment_failure_detected_atと、select_due_payment_suspension_owner_notifications()が
    読むpayment_failure_detected_atが、build_payment_suspension_customer_states()を介して
    実際に同一のInMemoryUsageCounter経由でつながることを確認する
    (trial_end_scheduler.pyのStripeWebhookUpgradedAtToTrialEndSchedulerWiringTest
    〈フェーズ130〉と同種の配線漏れの観点)。"""

    def setUp(self) -> None:
        from cloud_function_webhook import InMemoryUsageCounter
        from deletion_candidate import InMemoryProfileDeletionCandidateStore

        self.usage_counter = InMemoryUsageCounter()
        self.store = InMemoryProfileDeletionCandidateStore()

    def test_payment_failure_event_becomes_due_after_grace_period(self) -> None:
        from stripe_webhook import dispatch_stripe_event

        from payment_suspension_owner_notification import (
            build_payment_suspension_customer_states,
        )

        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,  # 2023-11-14T22:13:20Z
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=lambda customer: {"cus_A": "u1"}.get(customer),
            usage_counter=self.usage_counter,
        )
        self.assertEqual(result.payment_failure_detected_user_ids, ["u1"])

        event_time = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)

        # 猶予期間(7日)未経過: build_payment_suspension_customer_states()経由でも
        # まだ対象外のまま。
        states = build_payment_suspension_customer_states(self.usage_counter, ["u1"])
        due = select_due_payment_suspension_owner_notifications(
            states, event_time + timedelta(days=5)
        )
        self.assertEqual(due, [])

        # 猶予期間(7日)経過後は対象となる。
        states = build_payment_suspension_customer_states(self.usage_counter, ["u1"])
        due = select_due_payment_suspension_owner_notifications(
            states, event_time + timedelta(days=8)
        )
        self.assertEqual([c.user_id for c in due], ["u1"])

    def test_owner_notification_excludes_customer_from_next_scan(self) -> None:
        from stripe_webhook import dispatch_stripe_event

        from payment_suspension_owner_notification import (
            build_payment_suspension_customer_states,
        )

        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=lambda customer: {"cus_A": "u1"}.get(customer),
            usage_counter=self.usage_counter,
        )
        event_time = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
        now = event_time + timedelta(days=8)

        # send_payment_suspension_owner_notifications()を、dispatch_stripe_event()と
        # 同一のusage_counterに対して実行すると、payment_suspension_owner_notified_atが
        # 書き込まれる。
        states = build_payment_suspension_customer_states(self.usage_counter, ["u1"])
        push = InMemoryLinePushClient()
        send_result = send_payment_suspension_owner_notifications(
            states, now, self.usage_counter, push
        )
        self.assertEqual(send_result.sent, ["u1"])

        # 同じusage_counterを再度build_payment_suspension_customer_states()経由で
        # 読み取ると、payment_suspension_owner_notified_at設定済みのため次回スキャンの
        # 対象から除外される(二重送信しない)。
        states_after = build_payment_suspension_customer_states(self.usage_counter, ["u1"])
        due_after = select_due_payment_suspension_owner_notifications(states_after, now)
        self.assertEqual(due_after, [])


if __name__ == "__main__":
    unittest.main()
