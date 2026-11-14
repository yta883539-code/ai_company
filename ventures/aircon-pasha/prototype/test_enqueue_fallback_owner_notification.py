#!/usr/bin/env python3
"""enqueue_fallback_owner_notification.pyのテスト(aircon-pasha版)。
enqueue-fallback-owner-notification-design.md(aircon-pasha版)2〜4節の挙動を検証する。
course-set-pasha/prototype/test_enqueue_fallback_owner_notification.pyの横展開版。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from enqueue_fallback_owner_notification import (  # noqa: E402
    ENQUEUE_FALLBACK_OWNER_NOTIFICATION_ALT_TEXT,
    build_enqueue_fallback_owner_notification_flex_message,
    send_enqueue_fallback_owner_notification,
)
from blocked_but_billing_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER  # noqa: E402
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402


class _FailingLinePushClient:
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        raise LinePushDeliveryError("simulated outage")


class BuildEnqueueFallbackOwnerNotificationFlexMessageTest(unittest.TestCase):
    def test_message_contains_count_and_ids(self) -> None:
        contents = build_enqueue_fallback_owner_notification_flex_message(["ev1", "ev2"])
        body_text = contents["body"]["contents"][1]["text"]
        self.assertIn("件数: 2件", body_text)
        self.assertIn("ev1", body_text)
        self.assertIn("ev2", body_text)

    def test_more_than_limit_is_summarized(self) -> None:
        ids = [f"ev{i}" for i in range(1, 8)]  # 7件
        contents = build_enqueue_fallback_owner_notification_flex_message(ids)
        body_text = contents["body"]["contents"][1]["text"]
        self.assertIn("件数: 7件", body_text)
        for i in range(1, 6):
            self.assertIn(f"ev{i}", body_text)
        self.assertIn("...他2件", body_text)
        self.assertNotIn("ev6", body_text)
        self.assertNotIn("ev7", body_text)

    def test_exactly_limit_is_not_summarized(self) -> None:
        ids = [f"ev{i}" for i in range(1, 6)]  # 5件(上限と同数)
        contents = build_enqueue_fallback_owner_notification_flex_message(ids)
        body_text = contents["body"]["contents"][1]["text"]
        self.assertNotIn("...他", body_text)


class SendEnqueueFallbackOwnerNotificationTest(unittest.TestCase):
    def test_sends_digest_to_fixed_owner_id(self) -> None:
        push = InMemoryLinePushClient()

        result = send_enqueue_fallback_owner_notification(["ev1", "ev2"], push)

        self.assertTrue(result.sent)
        self.assertEqual(len(push.sent), 1)
        recipient, alt_text, contents = push.sent[0]
        self.assertEqual(recipient, OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertEqual(alt_text, ENQUEUE_FALLBACK_OWNER_NOTIFICATION_ALT_TEXT)
        self.assertIn("ev1", contents["body"]["contents"][1]["text"])
        self.assertIn("ev2", contents["body"]["contents"][1]["text"])

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
