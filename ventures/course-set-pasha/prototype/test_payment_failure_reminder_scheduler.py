#!/usr/bin/env python3
"""payment_failure_reminder_scheduler.pyのテスト。
payment-failure-reminder-scheduler-design.md 4節の抽出条件を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from payment_failure_reminder_scheduler import (  # noqa: E402
    DEFAULT_GRACE_PERIOD_DAYS,
    DEFAULT_REMINDER_DAYS_BEFORE_END,
    PaymentFailureUserState,
    format_payment_failure_reminder_message,
    select_due_payment_failure_reminders,
    send_payment_failure_reminders,
)
from trial_end_scheduler import (  # noqa: E402
    LIFF_URL_PLACEHOLDER,
    InMemoryLinePushClient,
    LinePushDeliveryError,
)


class _FakeUsageCounter:
    """set_payment_failure_reminder_sent_at()呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.reminder_sent_at: dict[str, datetime] = {}

    def set_payment_failure_reminder_sent_at(self, user_id: str, sent_at: datetime) -> None:
        self.reminder_sent_at[user_id] = sent_at


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class SelectDuePaymentFailureRemindersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 28, 4, 0, 0)

    def test_exactly_4_days_elapsed_is_due(self) -> None:
        # grace_period_days(7) - reminder_days_before_end(3) = 4日ちょうど。
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=4)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [user])

    def test_5_days_elapsed_is_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=5)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [user])

    def test_3_days_elapsed_is_not_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=3)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_exactly_7_days_elapsed_is_not_due(self) -> None:
        # 猶予期間ちょうど経過(制限モード相当): 上限側の条件で除外される。
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=7)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_more_than_7_days_elapsed_is_not_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=20)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_already_reminded_is_not_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1",
            payment_failure_detected_at=self.now - timedelta(days=6),
            payment_failure_reminder_sent_at=self.now - timedelta(days=1),
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_no_detected_at_is_not_due(self) -> None:
        user = PaymentFailureUserState(user_id="u1", payment_failure_detected_at=None)
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_custom_thresholds(self) -> None:
        # grace_period_days=14, reminder_days_before_end=5 → 下限9日・上限14日。
        user_due = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=10)
        )
        user_too_early = PaymentFailureUserState(
            user_id="u2", payment_failure_detected_at=self.now - timedelta(days=8)
        )
        due = select_due_payment_failure_reminders(
            [user_due, user_too_early], self.now, grace_period_days=14, reminder_days_before_end=5
        )
        self.assertEqual(due, [user_due])

    def test_preserves_input_order_for_multiple_due_users(self) -> None:
        user1 = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=4)
        )
        user2 = PaymentFailureUserState(
            user_id="u2", payment_failure_detected_at=self.now - timedelta(days=6)
        )
        self.assertEqual(
            select_due_payment_failure_reminders([user1, user2], self.now), [user1, user2]
        )


class FormatPaymentFailureReminderMessageTest(unittest.TestCase):
    def test_default_placeholder_is_used(self) -> None:
        text = format_payment_failure_reminder_message()
        self.assertIn(LIFF_URL_PLACEHOLDER, text)
        self.assertIn("3日後に投稿文の生成を一時停止", text)

    def test_custom_liff_url_is_substituted(self) -> None:
        text = format_payment_failure_reminder_message(liff_url="https://liff.line.me/xyz")
        self.assertIn("https://liff.line.me/xyz", text)
        self.assertNotIn(LIFF_URL_PLACEHOLDER, text)


class SendPaymentFailureRemindersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 28, 4, 0, 0)

    def test_sends_to_due_users_and_records_sent_at(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=5)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        result = send_payment_failure_reminders([user], self.now, usage_counter, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(usage_counter.reminder_sent_at["u1"], self.now)
        self.assertEqual(push.sent, [("u1", format_payment_failure_reminder_message())])

    def test_skips_not_due_users(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=1)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        result = send_payment_failure_reminders([user], self.now, usage_counter, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(push.sent, [])
        self.assertNotIn("u1", usage_counter.reminder_sent_at)

    def test_failed_send_does_not_record_sent_at(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=5)
        )
        usage_counter = _FakeUsageCounter()
        result = send_payment_failure_reminders(
            [user], self.now, usage_counter, _FailingLinePushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertNotIn("u1", usage_counter.reminder_sent_at)

    def test_default_grace_period_matches_dunning_design(self) -> None:
        # デフォルト値がpayment-failure-dunning-design.mdの猶予7日・3日前リマインドと
        # 一致していることを固定する回帰テスト。
        self.assertEqual(DEFAULT_GRACE_PERIOD_DAYS, 7)
        self.assertEqual(DEFAULT_REMINDER_DAYS_BEFORE_END, 3)


if __name__ == "__main__":
    unittest.main()
