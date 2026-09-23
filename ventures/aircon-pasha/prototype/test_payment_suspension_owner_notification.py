#!/usr/bin/env python3
"""payment_suspension_owner_notification.pyのテスト。
payment-suspension-owner-notification-design.md 3〜6節の抽出条件・送信配線を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from payment_suspension_owner_notification import (  # noqa: E402
    PAYMENT_SUSPENSION_OWNER_NOTIFICATION_ALT_TEXT,
    PaymentSuspensionOwnerNotificationUserState,
    build_payment_suspension_owner_notification_flex_message,
    select_due_payment_suspension_owner_notifications,
    send_payment_suspension_owner_notifications,
)
from blocked_but_billing_owner_notification import (  # noqa: E402
    OWNER_LINE_USER_ID_PLACEHOLDER,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402


class _FakeNotifiedAtStore:
    """set_payment_suspension_owner_notified_at()呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.notified_at: Dict[str, Optional[datetime]] = {}

    def set_payment_suspension_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        self.notified_at[user_id] = notified_at


class _FailingLinePushClient:
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        raise LinePushDeliveryError("simulated outage")


class SelectDuePaymentSuspensionOwnerNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 23, 4, 0, 0)

    def test_suspended_and_unnotified_user_is_selected(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1",
                payment_suspended_at=self.now,
                payment_failure_detected_at=self.now - timedelta(days=7),
            )
        ]
        self.assertEqual(
            [u.user_id for u in select_due_payment_suspension_owner_notifications(users)],
            ["u1"],
        )

    def test_not_yet_suspended_user_is_excluded(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1",
                payment_suspended_at=None,
                payment_failure_detected_at=self.now - timedelta(days=3),
            )
        ]
        self.assertEqual(select_due_payment_suspension_owner_notifications(users), [])

    def test_already_notified_user_is_excluded(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1",
                payment_suspended_at=self.now,
                payment_failure_detected_at=self.now - timedelta(days=7),
                payment_suspension_owner_notified_at=self.now - timedelta(days=1),
            )
        ]
        self.assertEqual(select_due_payment_suspension_owner_notifications(users), [])

    def test_empty_users_returns_empty(self) -> None:
        self.assertEqual(select_due_payment_suspension_owner_notifications([]), [])

    def test_input_order_is_preserved(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u3", payment_suspended_at=self.now
            ),
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1", payment_suspended_at=self.now
            ),
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u2", payment_suspended_at=self.now
            ),
        ]
        self.assertEqual(
            [u.user_id for u in select_due_payment_suspension_owner_notifications(users)],
            ["u3", "u1", "u2"],
        )

    def test_multiple_due_users_are_all_selected(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1", payment_suspended_at=self.now
            ),
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u2", payment_suspended_at=None
            ),
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u3", payment_suspended_at=self.now
            ),
        ]
        self.assertEqual(
            [u.user_id for u in select_due_payment_suspension_owner_notifications(users)],
            ["u1", "u3"],
        )


class BuildPaymentSuspensionOwnerNotificationFlexMessageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 23, 4, 0, 0)

    def test_message_contains_user_id_and_elapsed_days(self) -> None:
        user = PaymentSuspensionOwnerNotificationUserState(
            user_id="u1",
            payment_suspended_at=self.now,
            payment_failure_detected_at=self.now - timedelta(days=7),
        )
        contents = build_payment_suspension_owner_notification_flex_message(user, self.now)
        serialized = str(contents)
        self.assertIn("u1", serialized)
        self.assertIn("経過日数: 7日", serialized)
        self.assertIn("制限モード移行のお知らせ", serialized)

    def test_message_has_no_footer_button(self) -> None:
        user = PaymentSuspensionOwnerNotificationUserState(
            user_id="u1", payment_suspended_at=self.now
        )
        contents = build_payment_suspension_owner_notification_flex_message(user, self.now)
        self.assertNotIn("footer", contents)

    def test_missing_detected_at_falls_back_to_unknown(self) -> None:
        user = PaymentSuspensionOwnerNotificationUserState(
            user_id="u1", payment_suspended_at=self.now, payment_failure_detected_at=None
        )
        contents = build_payment_suspension_owner_notification_flex_message(user, self.now)
        self.assertIn("経過日数: 不明", str(contents))


class SendPaymentSuspensionOwnerNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 23, 4, 0, 0)

    def test_sends_only_to_due_users_and_marks_notified(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1",
                payment_suspended_at=self.now,
                payment_failure_detected_at=self.now - timedelta(days=7),
            ),
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u2",
                payment_suspended_at=self.now,
                payment_failure_detected_at=self.now - timedelta(days=7),
                payment_suspension_owner_notified_at=self.now - timedelta(days=1),
            ),
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u3", payment_suspended_at=None
            ),
        ]
        store = _FakeNotifiedAtStore()
        push = InMemoryLinePushClient()
        result = send_payment_suspension_owner_notifications(users, self.now, store, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.notified_at, {"u1": self.now})
        self.assertEqual(len(push.sent), 1)
        sent_id, sent_alt_text, _ = push.sent[0]
        self.assertEqual(sent_id, OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertEqual(sent_alt_text, PAYMENT_SUSPENSION_OWNER_NOTIFICATION_ALT_TEXT)

    def test_send_failure_does_not_write_notified_at_and_is_retried_next_time(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1", payment_suspended_at=self.now
            )
        ]
        store = _FakeNotifiedAtStore()
        result = send_payment_suspension_owner_notifications(
            users, self.now, store, _FailingLinePushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertNotIn("u1", store.notified_at)

    def test_no_due_users_sends_nothing(self) -> None:
        users = [
            PaymentSuspensionOwnerNotificationUserState(
                user_id="u1", payment_suspended_at=None
            )
        ]
        store = _FakeNotifiedAtStore()
        push = InMemoryLinePushClient()
        result = send_payment_suspension_owner_notifications(users, self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(len(push.sent), 0)


if __name__ == "__main__":
    unittest.main()
