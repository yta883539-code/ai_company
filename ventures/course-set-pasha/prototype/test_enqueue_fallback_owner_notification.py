#!/usr/bin/env python3
"""enqueue_fallback_owner_notification.pyのテスト。
enqueue-fallback-owner-notification-design.md 2〜4節の挙動を検証する。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from enqueue_fallback_owner_notification import (  # noqa: E402
    OWNER_LINE_USER_ID_PLACEHOLDER,
    format_enqueue_fallback_owner_notification_message,
    send_enqueue_fallback_owner_notification,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class FormatEnqueueFallbackOwnerNotificationMessageTest(unittest.TestCase):
    def test_message_contains_count_and_ids(self) -> None:
        text = format_enqueue_fallback_owner_notification_message(["ev1", "ev2"])
        self.assertIn("件数: 2件", text)
        self.assertIn("ev1", text)
        self.assertIn("ev2", text)
        self.assertIn("enqueue失敗", text)

    def test_more_than_limit_is_summarized(self) -> None:
        ids = [f"ev{i}" for i in range(1, 8)]  # 7件
        text = format_enqueue_fallback_owner_notification_message(ids)
        self.assertIn("件数: 7件", text)
        for i in range(1, 6):
            self.assertIn(f"ev{i}", text)
        self.assertIn("...他2件", text)
        self.assertNotIn("ev6", text)
        self.assertNotIn("ev7", text)

    def test_exactly_limit_is_not_summarized(self) -> None:
        ids = [f"ev{i}" for i in range(1, 6)]  # 5件(上限と同数)
        text = format_enqueue_fallback_owner_notification_message(ids)
        self.assertNotIn("...他", text)


class SendEnqueueFallbackOwnerNotificationTest(unittest.TestCase):
    def test_sends_digest_to_fixed_owner_id(self) -> None:
        push = InMemoryLinePushClient()

        result = send_enqueue_fallback_owner_notification(["ev1", "ev2"], push)

        self.assertTrue(result.sent)
        self.assertEqual(len(push.sent), 1)
        recipient, text = push.sent[0]
        self.assertEqual(recipient, OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertIn("ev1", text)
        self.assertIn("ev2", text)

    def test_empty_webhook_event_ids_sends_nothing(self) -> None:
        push = InMemoryLinePushClient()

        result = send_enqueue_fallback_owner_notification([], push)

        self.assertFalse(result.sent)
        self.assertEqual(push.sent, [])

    def test_delivery_failure_is_swallowed_without_raising(self) -> None:
        push = _FailingLinePushClient()

        result = send_enqueue_fallback_owner_notification(["ev1"], push)

        self.assertFalse(result.sent)


if __name__ == "__main__":
    unittest.main()
