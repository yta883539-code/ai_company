#!/usr/bin/env python3
"""payment_suspension_owner_notification.pyのテスト。
payment-suspension-owner-notification-design.md 3〜5節の抽出条件・送信配線を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from payment_suspension_owner_notification import (  # noqa: E402
    OWNER_LINE_USER_ID_PLACEHOLDER,
    build_payment_suspension_owner_notification_message,
    select_due_payment_suspension_owner_notifications,
    send_payment_suspension_owner_notifications,
)
from subscription_cancellation_notification import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
)
from usage_counter_workshop import InMemoryWorkshopStore  # noqa: E402


def _make_store() -> InMemoryWorkshopStore:
    store = InMemoryWorkshopStore()
    store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])
    store.set_members("w2", contractor_user_id="u2", member_user_ids=["u2"])
    store.set_members("w3", contractor_user_id="u3", member_user_ids=["u3"])
    return store


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class SelectDuePaymentSuspensionOwnerNotificationsTest(unittest.TestCase):
    def test_selects_workshop_past_grace_period_and_unnotified(self) -> None:
        now = datetime(2026, 9, 14, 10, 0, 0)
        store = _make_store()
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 5, 10, 0, 0))  # 9日経過
        self.assertEqual(
            select_due_payment_suspension_owner_notifications(now, store), ["w1"]
        )

    def test_excludes_workshop_still_within_grace_period(self) -> None:
        now = datetime(2026, 9, 14, 10, 0, 0)
        store = _make_store()
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 10, 10, 0, 0))  # 4日経過
        self.assertEqual(select_due_payment_suspension_owner_notifications(now, store), [])

    def test_excludes_workshop_with_no_payment_failure(self) -> None:
        now = datetime(2026, 9, 14, 10, 0, 0)
        store = _make_store()
        self.assertEqual(select_due_payment_suspension_owner_notifications(now, store), [])

    def test_excludes_already_notified_workshop(self) -> None:
        now = datetime(2026, 9, 14, 10, 0, 0)
        store = _make_store()
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 5, 10, 0, 0))
        store.set_payment_suspension_owner_notified_at("w1", datetime(2026, 9, 13, 0, 0, 0))
        self.assertEqual(select_due_payment_suspension_owner_notifications(now, store), [])

    def test_results_are_sorted_by_workshop_id(self) -> None:
        now = datetime(2026, 9, 14, 10, 0, 0)
        store = _make_store()
        store.set_payment_failure_detected_at("w3", datetime(2026, 9, 5, 10, 0, 0))
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 4, 10, 0, 0))
        self.assertEqual(
            select_due_payment_suspension_owner_notifications(now, store), ["w1", "w3"]
        )


class BuildPaymentSuspensionOwnerNotificationMessageTest(unittest.TestCase):
    def test_message_contains_contractor_user_id_and_elapsed_days(self) -> None:
        text = build_payment_suspension_owner_notification_message("u1", 9)
        self.assertIn("u1", text)
        self.assertIn("9日", text)
        self.assertIn("制限モード移行", text)


class SendPaymentSuspensionOwnerNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 14, 10, 0, 0)

    def test_sends_only_to_due_candidates_and_marks_notified(self) -> None:
        store = _make_store()
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 5, 10, 0, 0))  # 9日経過
        store.set_payment_failure_detected_at("w2", datetime(2026, 9, 10, 10, 0, 0))  # 4日経過
        push = InMemoryLinePushClient()

        result = send_payment_suspension_owner_notifications(self.now, store, push)

        self.assertEqual(result.sent, ["w1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(
            store.get_payment_suspension_owner_notified_at("w1"), self.now
        )
        self.assertIsNone(store.get_payment_suspension_owner_notified_at("w2"))

    def test_all_messages_sent_to_fixed_owner_id(self) -> None:
        store = _make_store()
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 5, 10, 0, 0))
        push = InMemoryLinePushClient()

        send_payment_suspension_owner_notifications(self.now, store, push)

        self.assertEqual(len(push.sent), 1)
        recipient, text = push.sent[0]
        self.assertEqual(recipient, OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertIn("u1", text)

    def test_no_candidates_sends_nothing(self) -> None:
        store = _make_store()
        push = InMemoryLinePushClient()

        result = send_payment_suspension_owner_notifications(self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(push.sent, [])

    def test_delivery_failure_is_not_marked_notified(self) -> None:
        store = _make_store()
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 5, 10, 0, 0))
        push = _FailingLinePushClient()

        result = send_payment_suspension_owner_notifications(self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["w1"])
        self.assertIsNone(store.get_payment_suspension_owner_notified_at("w1"))

    def test_recovery_clears_notified_at_via_clear_payment_failure_detected_at(self) -> None:
        """design 6節: clear_payment_failure_detected_at()経由で本フィールドも
        まとめてクリアされ、再度の決済失敗時に再通知できることを確認する。"""
        store = _make_store()
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 5, 10, 0, 0))
        push = InMemoryLinePushClient()
        send_payment_suspension_owner_notifications(self.now, store, push)
        self.assertIsNotNone(store.get_payment_suspension_owner_notified_at("w1"))

        store.clear_payment_failure_detected_at("w1")
        self.assertIsNone(store.get_payment_suspension_owner_notified_at("w1"))

        # 再度決済に失敗し猶予期間を超えた場合、再通知対象になることを確認する。
        later = datetime(2026, 9, 25, 10, 0, 0)
        store.set_payment_failure_detected_at("w1", datetime(2026, 9, 16, 10, 0, 0))
        self.assertEqual(
            select_due_payment_suspension_owner_notifications(later, store), ["w1"]
        )


if __name__ == "__main__":
    unittest.main()
