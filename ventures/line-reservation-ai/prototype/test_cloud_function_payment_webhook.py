#!/usr/bin/env python3
"""cloud_function_payment_webhook.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_cloud_function_payment_webhook -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError
from cloud_function_payment_webhook import (
    OUTCOME_CONFIRMED_IN_GRACE,
    OUTCOME_NO_DUNNING,
    OUTCOME_RECOVERED_FROM_SUSPENSION,
    OUTCOME_SEND_FAILED,
    OUTCOME_SILENT_RESET,
    classify_payment_succeeded,
    handle_payment_succeeded,
)
from cloud_function_send_dunning_notifications import StoreDunningState
from dunning_notification_scheduler import DUNNING_CONFIG_A_7DAYS

DETECTED_AT = datetime(2026, 8, 17, 10, 0)


class AlwaysFailingLinePushClient:
    """送信が常に失敗する検証用クライアント。"""

    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated failure")


def _store(**overrides) -> StoreDunningState:
    defaults = dict(
        store_id="store-1",
        owner_line_user_id="owner-1",
        payment_failure_detected_at=DETECTED_AT,
        config=DUNNING_CONFIG_A_7DAYS,
        payment_page_url="https://example.com/billing",
    )
    defaults.update(overrides)
    return StoreDunningState(**defaults)


class ClassifyPaymentSucceededTests(unittest.TestCase):
    def test_suspended_by_payment_failure_is_recovery(self):
        state = _store(suspension_reason="payment_failed", sent_event_keys={"detected", "suspended"})
        self.assertEqual(classify_payment_succeeded(state), OUTCOME_RECOVERED_FROM_SUSPENSION)

    def test_in_grace_with_sent_notification_is_confirmed_in_grace(self):
        state = _store(sent_event_keys={"detected"})
        self.assertEqual(classify_payment_succeeded(state), OUTCOME_CONFIRMED_IN_GRACE)

    def test_in_grace_without_sent_notification_is_silent_reset(self):
        state = _store(sent_event_keys=set())
        self.assertEqual(classify_payment_succeeded(state), OUTCOME_SILENT_RESET)

    def test_not_in_dunning_is_no_dunning(self):
        state = _store(payment_failure_detected_at=None)
        self.assertEqual(classify_payment_succeeded(state), OUTCOME_NO_DUNNING)

    def test_dormant_by_trial_unselected_is_not_treated_as_recovery(self):
        """休止モードが決済失敗以外の要因の場合は復旧通知の対象にしない。"""
        state = _store(payment_failure_detected_at=None, suspension_reason="trial_unselected")
        self.assertEqual(classify_payment_succeeded(state), OUTCOME_NO_DUNNING)


class HandlePaymentSucceededTests(unittest.TestCase):
    def test_recovery_sends_message_and_clears_state(self):
        push = InMemoryLinePushClient()
        state = _store(suspension_reason="payment_failed", sent_event_keys={"detected", "suspended"})

        result = handle_payment_succeeded(state, push)

        self.assertEqual(result.outcome, OUTCOME_RECOVERED_FROM_SUSPENSION)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_reset)
        self.assertEqual(len(push.sent), 1)
        self.assertIn("再開", push.sent[0][1])
        self.assertIsNone(state.payment_failure_detected_at)
        self.assertIsNone(state.suspension_reason)
        self.assertEqual(state.sent_event_keys, set())

    def test_in_grace_message_does_not_claim_service_was_resumed(self):
        """猶予期間中は受付が止まっていないため「再開」と書かない文言を送る。"""
        push = InMemoryLinePushClient()
        state = _store(sent_event_keys={"detected"})

        result = handle_payment_succeeded(state, push)

        self.assertEqual(result.outcome, OUTCOME_CONFIRMED_IN_GRACE)
        self.assertTrue(result.notified)
        self.assertNotIn("再開", push.sent[0][1])
        self.assertIn("お支払いを確認しました", push.sent[0][1])
        self.assertIsNone(state.payment_failure_detected_at)

    def test_silent_reset_does_not_notify_but_clears_state(self):
        push = InMemoryLinePushClient()
        state = _store(sent_event_keys=set())

        result = handle_payment_succeeded(state, push)

        self.assertEqual(result.outcome, OUTCOME_SILENT_RESET)
        self.assertFalse(result.notified)
        self.assertTrue(result.state_reset)
        self.assertEqual(push.sent, [])
        self.assertIsNone(state.payment_failure_detected_at)

    def test_normal_monthly_payment_is_not_notified(self):
        push = InMemoryLinePushClient()
        state = _store(payment_failure_detected_at=None)

        result = handle_payment_succeeded(state, push)

        self.assertEqual(result.outcome, OUTCOME_NO_DUNNING)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(push.sent, [])

    def test_webhook_redelivery_does_not_send_twice(self):
        push = InMemoryLinePushClient()
        state = _store(suspension_reason="payment_failed", sent_event_keys={"detected", "suspended"})

        handle_payment_succeeded(state, push)
        second = handle_payment_succeeded(state, push)

        self.assertEqual(second.outcome, OUTCOME_NO_DUNNING)
        self.assertEqual(len(push.sent), 1)

    def test_send_failure_leaves_state_untouched_for_retry(self):
        state = _store(suspension_reason="payment_failed", sent_event_keys={"detected", "suspended"})

        result = handle_payment_succeeded(state, AlwaysFailingLinePushClient())

        self.assertEqual(result.outcome, OUTCOME_SEND_FAILED)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(state.payment_failure_detected_at, DETECTED_AT)
        self.assertEqual(state.suspension_reason, "payment_failed")
        self.assertEqual(state.sent_event_keys, {"detected", "suspended"})

    def test_retry_after_send_failure_sends_once_state_is_intact(self):
        state = _store(suspension_reason="payment_failed", sent_event_keys={"detected", "suspended"})
        handle_payment_succeeded(state, AlwaysFailingLinePushClient())

        push = InMemoryLinePushClient()
        result = handle_payment_succeeded(state, push)

        self.assertEqual(result.outcome, OUTCOME_RECOVERED_FROM_SUSPENSION)
        self.assertEqual(len(push.sent), 1)

    def test_dormant_suspension_reason_is_preserved(self):
        """決済失敗以外の要因の休止モードは、決済成功で勝手に解除しない。"""
        push = InMemoryLinePushClient()
        state = _store(suspension_reason="trial_unselected", sent_event_keys={"detected"})

        handle_payment_succeeded(state, push)

        self.assertEqual(state.suspension_reason, "trial_unselected")
        self.assertIsNone(state.payment_failure_detected_at)

    def test_message_tone_is_applied(self):
        push = InMemoryLinePushClient()
        state = _store(
            suspension_reason="payment_failed",
            sent_event_keys={"detected", "suspended"},
            message_tone="formal",
        )

        handle_payment_succeeded(state, push)

        self.assertIn("いたしました", push.sent[0][1])


if __name__ == "__main__":
    unittest.main()
