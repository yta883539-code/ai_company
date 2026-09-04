#!/usr/bin/env python3
"""subscription_cancellation_notification.pyのテスト(subscription-cancelled-
notification-design.md フェーズ155、subscription-cancellation-scheduled-notification-
design.md フェーズ156)。"""

from __future__ import annotations

import unittest

from cloud_function_webhook import PORTAL_LINK_UNAVAILABLE_FALLBACK, InMemoryPortalLinkProvider
from subscription_cancellation_notification import (
    OUTCOME_CANCELLATION_RESCHEDULED,
    OUTCOME_CANCELLATION_SCHEDULED,
    OUTCOME_NO_CHANGE,
    SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE,
    SUBSCRIPTION_CANCELLED_MESSAGE,
    classify_cancel_at_period_end_change,
    handle_subscription_cancellation_update,
    handle_subscription_cancelled,
    render_subscription_cancellation_rescheduled_message,
    render_subscription_cancellation_scheduled_message,
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


class ClassifyCancelAtPeriodEndChangeTest(unittest.TestCase):
    def test_false_to_true_is_scheduled(self):
        self.assertEqual(
            classify_cancel_at_period_end_change(False, True), OUTCOME_CANCELLATION_SCHEDULED
        )

    def test_true_to_false_is_rescheduled(self):
        self.assertEqual(
            classify_cancel_at_period_end_change(True, False), OUTCOME_CANCELLATION_RESCHEDULED
        )

    def test_no_change_false_false(self):
        self.assertEqual(classify_cancel_at_period_end_change(False, False), OUTCOME_NO_CHANGE)

    def test_no_change_true_true(self):
        self.assertEqual(classify_cancel_at_period_end_change(True, True), OUTCOME_NO_CHANGE)


class RenderSubscriptionCancellationScheduledMessageTest(unittest.TestCase):
    def test_includes_period_end_date_and_portal_url(self):
        text = render_subscription_cancellation_scheduled_message(
            "2026-10-04", InMemoryPortalLinkProvider("https://example.com/portal"), "user_1"
        )
        self.assertIn("2026-10-04", text)
        self.assertIn("https://example.com/portal", text)
        self.assertIn("解約のお手続きを承りました", text)
        self.assertIn("投稿文の生成がご利用いただけなくなります", text)

    def test_none_period_end_date_falls_back_to_dateless_phrase(self):
        text = render_subscription_cancellation_scheduled_message(
            None, InMemoryPortalLinkProvider("https://example.com/portal"), "user_1"
        )
        self.assertIn("今回の請求期間の終了日まで", text)
        self.assertNotIn("()", text)

    def test_unavailable_portal_link_provider_falls_back(self):
        text = render_subscription_cancellation_scheduled_message(
            "2026-10-04", InMemoryPortalLinkProvider(None), "user_1"
        )
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_none_portal_link_provider_falls_back(self):
        text = render_subscription_cancellation_scheduled_message("2026-10-04", None, "user_1")
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_none_user_id_falls_back(self):
        text = render_subscription_cancellation_scheduled_message(
            "2026-10-04", InMemoryPortalLinkProvider("https://example.com/portal"), None
        )
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)


class RenderSubscriptionCancellationRescheduledMessageTest(unittest.TestCase):
    def test_render_returns_the_message_constant(self):
        self.assertEqual(
            render_subscription_cancellation_rescheduled_message(),
            SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE,
        )

    def test_message_contains_required_points(self):
        text = render_subscription_cancellation_rescheduled_message()
        self.assertIn("解約のお取り消しを承りました", text)
        self.assertIn("引き続きご利用いただけます", text)


class HandleSubscriptionCancellationUpdateTest(unittest.TestCase):
    def test_no_change_does_not_send(self):
        push_client = InMemoryLinePushClient()
        result = handle_subscription_cancellation_update(
            "user_1", False, False, 1_700_000_000, push_client
        )
        self.assertEqual(result.outcome, OUTCOME_NO_CHANGE)
        self.assertFalse(result.notified)
        self.assertEqual(len(push_client.sent), 0)

    def test_scheduled_sends_scheduled_message(self):
        push_client = InMemoryLinePushClient()
        portal_link_provider = InMemoryPortalLinkProvider("https://example.com/portal")
        result = handle_subscription_cancellation_update(
            "user_1", False, True, 1_700_000_000, push_client, portal_link_provider
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        self.assertEqual(len(push_client.sent), 1)
        sent_user_id, sent_text = push_client.sent[0]
        self.assertEqual(sent_user_id, "user_1")
        self.assertIn("解約のお手続きを承りました", sent_text)

    def test_rescheduled_sends_rescheduled_message(self):
        push_client = InMemoryLinePushClient()
        result = handle_subscription_cancellation_update(
            "user_1", True, False, 1_700_000_000, push_client
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_RESCHEDULED)
        self.assertTrue(result.notified)
        sent_user_id, sent_text = push_client.sent[0]
        self.assertEqual(sent_text, SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE)

    def test_send_failure_returns_notified_false_without_raising(self):
        class _FailingPushClient:
            def send_message(self, user_id, text):
                raise LinePushDeliveryError("simulated failure")

        result = handle_subscription_cancellation_update(
            "user_1", False, True, 1_700_000_000, _FailingPushClient()
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertFalse(result.notified)


if __name__ == "__main__":
    unittest.main()
