#!/usr/bin/env python3
"""payment_failure_reminder_scheduler.pyの単体テスト。
payment-failure-reminder-scheduler-design.md(フェーズ143)の抽出条件・メッセージ整形・
送信配線に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_webhook import (  # noqa: E402
    UPDATE_PAYMENT_METHOD_POSTBACK_DATA,
)
from payment_failure_reminder_scheduler import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
    PaymentFailureReminderUserState,
    build_payment_failure_reminder_flex_message,
    select_due_payment_failure_reminders,
    send_payment_failure_reminders,
)

_NOW = datetime(2026, 8, 28, 4, 0, 0)


class SelectDuePaymentFailureRemindersTest(unittest.TestCase):
    def test_selects_user_at_exactly_4_days(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=4)
            )
        ]

        due = select_due_payment_failure_reminders(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])

    def test_selects_user_past_4_days(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=6)
            )
        ]

        due = select_due_payment_failure_reminders(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])

    def test_excludes_user_before_4_days(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=3)
            )
        ]

        due = select_due_payment_failure_reminders(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_user_without_payment_failure_detected_at(self):
        users = [
            PaymentFailureReminderUserState(user_id="u1", payment_failure_detected_at=None)
        ]

        due = select_due_payment_failure_reminders(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_already_reminded_user(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1",
                payment_failure_detected_at=_NOW - timedelta(days=6),
                payment_failure_reminder_sent_at=_NOW - timedelta(days=1),
            )
        ]

        due = select_due_payment_failure_reminders(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_already_suspended_user(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1",
                payment_failure_detected_at=_NOW - timedelta(days=10),
                payment_suspended_at=_NOW - timedelta(days=3),
            )
        ]

        due = select_due_payment_failure_reminders(users, _NOW)

        self.assertEqual(due, [])

    def test_preserves_input_order_among_multiple_due_users(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u2", payment_failure_detected_at=_NOW - timedelta(days=5)
            ),
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=4)
            ),
        ]

        due = select_due_payment_failure_reminders(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u2", "u1"])

    def test_custom_grace_period_and_reminder_days(self):
        # 猶予期間3日・2日前リマインドなら、検知から1日経過時点が対象。
        users = [
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=1)
            )
        ]

        due = select_due_payment_failure_reminders(
            users, _NOW, grace_period_days=3, reminder_days_before_end=2
        )

        self.assertEqual([u.user_id for u in due], ["u1"])


class BuildPaymentFailureReminderFlexMessageTest(unittest.TestCase):
    def test_footer_button_uses_update_payment_method_postback_data(self):
        contents = build_payment_failure_reminder_flex_message()

        button = contents["footer"]["contents"][0]
        self.assertEqual(button["action"]["type"], "postback")
        self.assertEqual(button["action"]["data"], UPDATE_PAYMENT_METHOD_POSTBACK_DATA)

    def test_body_mentions_grace_period_end(self):
        contents = build_payment_failure_reminder_flex_message()

        body_texts = [
            block["text"]
            for block in contents["body"]["contents"]
            if block["type"] == "text"
        ]
        self.assertTrue(any("3日後" in text for text in body_texts))


class SendPaymentFailureRemindersTest(unittest.TestCase):
    class _InMemoryProfileStoreStub:
        def __init__(self) -> None:
            self.reminder_sent_at: dict = {}

        def set_payment_failure_reminder_sent_at(self, user_id, value):
            self.reminder_sent_at[user_id] = value

    def test_sends_to_due_users_and_writes_reminder_sent_at(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=4)
            ),
            PaymentFailureReminderUserState(
                user_id="u2", payment_failure_detected_at=_NOW - timedelta(days=1)
            ),
        ]
        profile_store = self._InMemoryProfileStoreStub()
        push = InMemoryLinePushClient()

        result = send_payment_failure_reminders(users, _NOW, profile_store, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(profile_store.reminder_sent_at, {"u1": _NOW})
        self.assertEqual(len(push.sent), 1)
        sent_user_id, alt_text, contents = push.sent[0]
        self.assertEqual(sent_user_id, "u1")
        self.assertIn("お支払い", alt_text)

    def test_delivery_failure_does_not_write_reminder_sent_at_and_is_reported_as_failed(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=4)
            )
        ]
        profile_store = self._InMemoryProfileStoreStub()

        class _FailingPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise LinePushDeliveryError("boom")

        result = send_payment_failure_reminders(
            users, _NOW, profile_store, _FailingPushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertEqual(profile_store.reminder_sent_at, {})

    def test_no_due_users_sends_nothing(self):
        users = [
            PaymentFailureReminderUserState(
                user_id="u1", payment_failure_detected_at=_NOW - timedelta(days=1)
            )
        ]
        profile_store = self._InMemoryProfileStoreStub()
        push = InMemoryLinePushClient()

        result = send_payment_failure_reminders(users, _NOW, profile_store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(push.sent, [])


if __name__ == "__main__":
    unittest.main()
