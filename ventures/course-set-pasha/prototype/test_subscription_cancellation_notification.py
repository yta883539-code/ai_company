#!/usr/bin/env python3
"""subscription_cancellation_notification.pyのテスト(subscription-cancelled-
notification-design.md フェーズ155)。"""

from __future__ import annotations

import unittest

from subscription_cancellation_notification import (
    SUBSCRIPTION_CANCELLED_MESSAGE,
    handle_subscription_cancelled,
    render_subscription_cancelled_message,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError


class RenderSubscriptionCancelledMessageTest(unittest.TestCase):
    def test_render_returns_the_message_constant(self):
        self.assertEqual(render_subscription_cancelled_message(), SUBSCRIPTION_CANCELLED_MESSAGE)

    def test_message_contains_required_points(self):
        # design 2節: 「契約終了」「本日以降、生成は利用不可」「再開時は新規契約と同じ手続き」
        text = render_subscription_cancelled_message()
        self.assertIn("ご契約が終了しました", text)
        self.assertIn("投稿文の生成はご利用いただけません", text)
        self.assertIn("新規契約と", text)

    def test_message_does_not_contain_date_placeholder(self):
        # design 1節: customer.subscription.deleted受信時点では既に契約終了後のため、
        # 「◯月◯日まで利用可能」のような未来日付の言及を含めない。
        text = render_subscription_cancelled_message()
        self.assertNotIn("◯月◯日", text)
        self.assertNotIn("それまでは引き続きご利用いただけます", text)


class HandleSubscriptionCancelledTest(unittest.TestCase):
    def test_successful_send_returns_notified_true(self):
        push_client = InMemoryLinePushClient()
        result = handle_subscription_cancelled("user_1", push_client)
        self.assertTrue(result.notified)
        self.assertEqual(len(push_client.sent), 1)
        sent_user_id, sent_text = push_client.sent[0]
        self.assertEqual(sent_user_id, "user_1")
        self.assertEqual(sent_text, SUBSCRIPTION_CANCELLED_MESSAGE)

    def test_send_failure_returns_notified_false_without_raising(self):
        class _FailingPushClient:
            def send_message(self, user_id, text):
                raise LinePushDeliveryError("simulated failure")

        result = handle_subscription_cancelled("user_1", _FailingPushClient())
        self.assertFalse(result.notified)


if __name__ == "__main__":
    unittest.main()
