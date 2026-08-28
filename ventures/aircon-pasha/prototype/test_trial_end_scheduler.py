#!/usr/bin/env python3
"""trial_end_scheduler.pyの単体テスト。
trial-end-scheduler-design.md(フェーズ133)の抽出条件・メッセージ整形・送信配線に
沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import START_CHECKOUT_POSTBACK_DATA  # noqa: E402
from trial_end_scheduler import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
    TrialUserState,
    build_trial_end_notification_flex_message,
    select_due_trial_end_notifications,
    send_trial_end_notifications,
)

_NOW = datetime(2026, 8, 28, 4, 0, 0)


class SelectDueTrialEndNotificationsTest(unittest.TestCase):
    def test_selects_user_at_exactly_14_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=14))]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])

    def test_selects_user_past_14_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=30))]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])

    def test_excludes_user_before_14_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=13))]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_user_without_trial_start_at(self):
        users = [TrialUserState(user_id="u1", trial_start_at=None)]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_already_notified_user(self):
        users = [
            TrialUserState(
                user_id="u1",
                trial_start_at=_NOW - timedelta(days=20),
                trial_end_notified_at=_NOW - timedelta(days=1),
            )
        ]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_already_upgraded_user(self):
        users = [
            TrialUserState(
                user_id="u1",
                trial_start_at=_NOW - timedelta(days=20),
                upgraded_at=_NOW - timedelta(days=2),
            )
        ]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_preserves_input_order_among_multiple_due_users(self):
        users = [
            TrialUserState(user_id="u2", trial_start_at=_NOW - timedelta(days=15)),
            TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=14)),
        ]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u2", "u1"])

    def test_custom_trial_period_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=7))]

        due = select_due_trial_end_notifications(users, _NOW, trial_period_days=7)

        self.assertEqual([u.user_id for u in due], ["u1"])


class BuildTrialEndNotificationFlexMessageTest(unittest.TestCase):
    def test_includes_generation_count_in_body_text(self):
        contents = build_trial_end_notification_flex_message(generation_count=8)

        body_texts = [
            block["text"]
            for block in contents["body"]["contents"]
            if block["type"] == "text"
        ]
        self.assertTrue(any("8回" in text for text in body_texts))

    def test_footer_button_uses_start_checkout_postback_data(self):
        contents = build_trial_end_notification_flex_message(generation_count=0)

        button = contents["footer"]["contents"][0]
        self.assertEqual(button["action"]["type"], "postback")
        self.assertEqual(button["action"]["data"], START_CHECKOUT_POSTBACK_DATA)


class SendTrialEndNotificationsTest(unittest.TestCase):
    class _InMemoryProfileStoreStub:
        def __init__(self) -> None:
            self.notified_at: dict[str, datetime] = {}

        def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
            self.notified_at[user_id] = notified_at

    def test_sends_to_due_users_and_writes_notified_at(self):
        users = [
            TrialUserState(
                user_id="u1", trial_start_at=_NOW - timedelta(days=14),
                trial_generation_count=3,
            ),
            TrialUserState(user_id="u2", trial_start_at=_NOW - timedelta(days=1)),
        ]
        profile_store = self._InMemoryProfileStoreStub()
        push = InMemoryLinePushClient()

        result = send_trial_end_notifications(users, _NOW, profile_store, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(profile_store.notified_at, {"u1": _NOW})
        self.assertEqual(len(push.sent), 1)
        sent_user_id, alt_text, contents = push.sent[0]
        self.assertEqual(sent_user_id, "u1")
        self.assertIn("トライアル", alt_text)

    def test_delivery_failure_does_not_write_notified_at_and_is_reported_as_failed(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=14))]
        profile_store = self._InMemoryProfileStoreStub()

        class _FailingPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise LinePushDeliveryError("boom")

        result = send_trial_end_notifications(users, _NOW, profile_store, _FailingPushClient())

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertEqual(profile_store.notified_at, {})

    def test_no_due_users_sends_nothing(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=1))]
        profile_store = self._InMemoryProfileStoreStub()
        push = InMemoryLinePushClient()

        result = send_trial_end_notifications(users, _NOW, profile_store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(push.sent, [])


if __name__ == "__main__":
    unittest.main()
