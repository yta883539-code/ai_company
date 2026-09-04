#!/usr/bin/env python3
"""subscription_cancellation_notification.pyのテスト(subscription-cancelled-
notification-design.md フェーズ155、subscription-cancellation-scheduled-notification-
design.md フェーズ156)。"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from cloud_function_webhook import (
    PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    InMemoryPortalLinkProvider,
    InMemoryUsageCounter,
)
from subscription_cancellation_notification import (
    OUTCOME_CANCELLATION_RESCHEDULED,
    OUTCOME_CANCELLATION_SCHEDULED,
    OUTCOME_NO_CHANGE,
    SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE,
    SUBSCRIPTION_CANCELLED_MESSAGE,
    _is_payment_suspended_now,
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

    def test_default_is_currently_suspended_false_keeps_no_restriction_wording(self):
        # フェーズ157以前の呼び出し経路(引数省略)への後方互換確認。
        text = render_subscription_cancellation_scheduled_message(
            "2026-10-04", InMemoryPortalLinkProvider("https://example.com/portal"), "user_1"
        )
        self.assertIn("投稿文の生成に制限はありません", text)

    def test_is_currently_suspended_true_replaces_no_restriction_wording(self):
        # フェーズ157: 制限モード中は「制限はありません」という矛盾した案内を出さない。
        text = render_subscription_cancellation_scheduled_message(
            "2026-10-04",
            InMemoryPortalLinkProvider("https://example.com/portal"),
            "user_1",
            True,
        )
        self.assertNotIn("投稿文の生成に制限はありません", text)
        self.assertIn("投稿文の生成は既に一時停止しています", text)
        # 終了日までの契約継続自体は制限モード中でも変わらない事実のため、引き続き案内する。
        self.assertIn("2026-10-04", text)
        self.assertIn("契約自体は", text)


class IsPaymentSuspendedNowTest(unittest.TestCase):
    """フェーズ157: subscription-cancellation-scheduled-message-suspension-
    consistency-design.md 3節。"""

    def test_true_when_grace_period_exceeded(self):
        usage_counter = InMemoryUsageCounter()
        detected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        usage_counter.set_payment_failure_detected_at("user_1", detected_at)
        now = detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS)
        self.assertTrue(_is_payment_suspended_now(usage_counter, "user_1", now))

    def test_false_when_grace_period_not_yet_exceeded(self):
        usage_counter = InMemoryUsageCounter()
        detected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        usage_counter.set_payment_failure_detected_at("user_1", detected_at)
        now = detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS - 1)
        self.assertFalse(_is_payment_suspended_now(usage_counter, "user_1", now))

    def test_false_when_no_detected_at_recorded(self):
        usage_counter = InMemoryUsageCounter()
        self.assertFalse(
            _is_payment_suspended_now(usage_counter, "user_1", datetime.now(timezone.utc))
        )

    def test_false_when_usage_counter_none(self):
        self.assertFalse(_is_payment_suspended_now(None, "user_1", datetime.now(timezone.utc)))

    def test_false_when_now_none(self):
        usage_counter = InMemoryUsageCounter()
        usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        self.assertFalse(_is_payment_suspended_now(usage_counter, "user_1", None))

    def test_false_when_usage_counter_lacks_get_payment_failure_detected_at(self):
        class _NoLookupUsageCounter:
            pass

        self.assertFalse(
            _is_payment_suspended_now(
                _NoLookupUsageCounter(), "user_1", datetime.now(timezone.utc)
            )
        )


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

    def test_scheduled_while_suspended_sends_suspension_aware_message(self):
        # フェーズ157: usage_counterが制限モード中(猶予期間超過)を記録している場合、
        # 送信される文面が「制限はありません」から切り替わることを確認する。
        push_client = InMemoryLinePushClient()
        portal_link_provider = InMemoryPortalLinkProvider("https://example.com/portal")
        usage_counter = InMemoryUsageCounter()
        detected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        usage_counter.set_payment_failure_detected_at("user_1", detected_at)
        now = detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS)

        result = handle_subscription_cancellation_update(
            "user_1",
            False,
            True,
            1_700_000_000,
            push_client,
            portal_link_provider,
            usage_counter,
            now,
        )

        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        _, sent_text = push_client.sent[0]
        self.assertNotIn("投稿文の生成に制限はありません", sent_text)
        self.assertIn("投稿文の生成は既に一時停止しています", sent_text)

    def test_scheduled_while_not_yet_suspended_keeps_default_message(self):
        # 猶予期間内(まだ制限モードに移行していない)場合は従来通りの文言のまま。
        push_client = InMemoryLinePushClient()
        portal_link_provider = InMemoryPortalLinkProvider("https://example.com/portal")
        usage_counter = InMemoryUsageCounter()
        detected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        usage_counter.set_payment_failure_detected_at("user_1", detected_at)
        now = detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS - 1)

        result = handle_subscription_cancellation_update(
            "user_1",
            False,
            True,
            1_700_000_000,
            push_client,
            portal_link_provider,
            usage_counter,
            now,
        )

        _, sent_text = push_client.sent[0]
        self.assertIn("投稿文の生成に制限はありません", sent_text)

    def test_rescheduled_message_unaffected_by_suspension_state(self):
        # OUTCOME_CANCELLATION_RESCHEDULED側は制限モードの有無に関わらず文言が変わらない
        # (design 2節)ため、usage_counter/nowを渡しても固定文言のまま送信される。
        push_client = InMemoryLinePushClient()
        usage_counter = InMemoryUsageCounter()
        detected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        usage_counter.set_payment_failure_detected_at("user_1", detected_at)
        now = detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS)

        result = handle_subscription_cancellation_update(
            "user_1",
            True,
            False,
            1_700_000_000,
            push_client,
            usage_counter=usage_counter,
            now=now,
        )

        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_RESCHEDULED)
        _, sent_text = push_client.sent[0]
        self.assertEqual(sent_text, SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE)


if __name__ == "__main__":
    unittest.main()
