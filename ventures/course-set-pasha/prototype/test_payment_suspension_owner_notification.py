#!/usr/bin/env python3
"""payment_suspension_owner_notification.pyのテスト。
payment-suspension-owner-notification-design.md 3節の抽出条件を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
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


if __name__ == "__main__":
    unittest.main()
