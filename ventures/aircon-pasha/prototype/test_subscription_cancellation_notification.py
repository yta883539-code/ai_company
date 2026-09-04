#!/usr/bin/env python3
"""subscription_cancellation_notification.pyの単体テスト。
subscription-cancellation-notification-design.md(フェーズ184)のテスト観点に沿った挙動を
確認する。"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_webhook import InMemoryPortalLinkProvider  # noqa: E402
from subscription_cancellation_notification import (  # noqa: E402
    OUTCOME_CANCELLATION_RESCHEDULED,
    OUTCOME_CANCELLATION_SCHEDULED,
    OUTCOME_NO_CHANGE,
    InMemoryLinePushClient,
    LinePushDeliveryError,
    classify_cancel_at_period_end_change,
    handle_subscription_cancellation_update,
    handle_subscription_cancelled,
    render_subscription_cancellation_scheduled_message,
    render_subscription_cancellation_rescheduled_message,
    render_subscription_cancelled_message,
)


class _FailingPushClient:
    def send_flex_message(self, user_id, alt_text, contents):
        raise LinePushDeliveryError("boom")


class ClassifyCancelAtPeriodEndChangeTest(unittest.TestCase):
    def test_false_to_true_is_scheduled(self):
        self.assertEqual(
            classify_cancel_at_period_end_change(False, True), OUTCOME_CANCELLATION_SCHEDULED
        )

    def test_true_to_false_is_rescheduled(self):
        self.assertEqual(
            classify_cancel_at_period_end_change(True, False), OUTCOME_CANCELLATION_RESCHEDULED
        )

    def test_no_change_when_both_false(self):
        self.assertEqual(classify_cancel_at_period_end_change(False, False), OUTCOME_NO_CHANGE)

    def test_no_change_when_both_true(self):
        self.assertEqual(classify_cancel_at_period_end_change(True, True), OUTCOME_NO_CHANGE)


class HandleSubscriptionCancelledTest(unittest.TestCase):
    def test_sends_completion_message(self):
        push = InMemoryLinePushClient()
        result = handle_subscription_cancelled("u1", push)
        self.assertTrue(result.notified)
        self.assertEqual(len(push.sent), 1)
        user_id, alt_text, contents = push.sent[0]
        self.assertEqual(user_id, "u1")
        self.assertIn("契約が終了しました", contents["body"]["contents"][0]["text"])

    def test_send_failure_returns_not_notified(self):
        result = handle_subscription_cancelled("u1", _FailingPushClient())
        self.assertFalse(result.notified)


class RenderScheduledMessageTest(unittest.TestCase):
    def test_includes_period_end_date_and_portal_url(self):
        text = render_subscription_cancellation_scheduled_message(
            "2026-10-01", InMemoryPortalLinkProvider("https://example.test/portal"), "u1"
        )
        self.assertIn("2026-10-01", text)
        self.assertIn("https://example.test/portal", text)
        self.assertNotIn("{Stripeカスタマーポータル URL}", text)

    def test_falls_back_to_generic_phrase_when_date_none(self):
        text = render_subscription_cancellation_scheduled_message(
            None, InMemoryPortalLinkProvider("https://example.test/portal"), "u1"
        )
        self.assertIn("今回の請求期間の終了日まで", text)

    def test_falls_back_to_unavailable_message_when_provider_none(self):
        text = render_subscription_cancellation_scheduled_message("2026-10-01", None, "u1")
        self.assertEqual(text, render_subscription_cancellation_scheduled_message("2026-10-01", None, "u1"))
        self.assertIn("お手続きページの発行に失敗", text)

    def test_falls_back_when_url_unavailable(self):
        text = render_subscription_cancellation_scheduled_message(
            "2026-10-01", InMemoryPortalLinkProvider(None), "u1"
        )
        self.assertIn("お手続きページの発行に失敗", text)


class RenderRescheduledMessageTest(unittest.TestCase):
    def test_fixed_message(self):
        text = render_subscription_cancellation_rescheduled_message()
        self.assertIn("解約のお取り消しを承りました", text)


class HandleSubscriptionCancellationUpdateTest(unittest.TestCase):
    def test_no_change_sends_nothing(self):
        push = InMemoryLinePushClient()
        result = handle_subscription_cancellation_update("u1", False, False, None, push)
        self.assertEqual(result.outcome, OUTCOME_NO_CHANGE)
        self.assertFalse(result.notified)
        self.assertEqual(len(push.sent), 0)

    def test_scheduled_sends_scheduled_message(self):
        push = InMemoryLinePushClient()
        period_end = int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp())
        result = handle_subscription_cancellation_update(
            "u1", False, True, period_end, push, InMemoryPortalLinkProvider()
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        self.assertEqual(len(push.sent), 1)

    def test_rescheduled_sends_rescheduled_message(self):
        push = InMemoryLinePushClient()
        result = handle_subscription_cancellation_update("u1", True, False, None, push)
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_RESCHEDULED)
        self.assertTrue(result.notified)

    def test_send_failure_leaves_notified_false(self):
        result = handle_subscription_cancellation_update(
            "u1", False, True, None, _FailingPushClient()
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertFalse(result.notified)


class RenderCancelledMessageTest(unittest.TestCase):
    def test_fixed_message(self):
        text = render_subscription_cancelled_message()
        self.assertIn("ご契約が終了しました", text)
        self.assertIn("作業完了報告・お手入れ案内の生成", text)


if __name__ == "__main__":
    unittest.main()
