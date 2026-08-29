#!/usr/bin/env python3
"""payment_recovery_notification.pyのテスト。
payment-failure-dunning-design.md 4節「決済成功による復旧時(3分岐)」を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_webhook import (  # noqa: E402
    PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    InMemoryUsageCounter,
)
from payment_recovery_notification import (  # noqa: E402
    OUTCOME_CONFIRMED_IN_GRACE,
    OUTCOME_NO_DUNNING,
    OUTCOME_RECOVERED_FROM_SUSPENSION,
    OUTCOME_SEND_FAILED,
    OUTCOME_SILENT_RESET,
    PAYMENT_CONFIRMED_IN_GRACE_MESSAGE,
    PAYMENT_RECOVERED_MESSAGE,
    build_payment_recovery_message,
    classify_payment_recovery,
    handle_payment_succeeded,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402

_NOW = datetime(2026, 8, 29, 1, 0, 0)


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated failure")


class ClassifyPaymentRecoveryTests(unittest.TestCase):
    def test_no_detected_at_is_no_dunning(self) -> None:
        self.assertEqual(
            classify_payment_recovery(None, None, _NOW), OUTCOME_NO_DUNNING
        )

    def test_grace_period_exactly_elapsed_is_recovered_from_suspension(self) -> None:
        detected_at = _NOW - timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS)
        self.assertEqual(
            classify_payment_recovery(detected_at, None, _NOW),
            OUTCOME_RECOVERED_FROM_SUSPENSION,
        )

    def test_past_grace_period_is_recovered_from_suspension_even_with_reminder(self) -> None:
        detected_at = _NOW - timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS + 3)
        reminder_sent_at = _NOW - timedelta(days=1)
        self.assertEqual(
            classify_payment_recovery(detected_at, reminder_sent_at, _NOW),
            OUTCOME_RECOVERED_FROM_SUSPENSION,
        )

    def test_within_grace_period_with_reminder_is_confirmed_in_grace(self) -> None:
        detected_at = _NOW - timedelta(days=5)
        reminder_sent_at = _NOW - timedelta(days=1)
        self.assertEqual(
            classify_payment_recovery(detected_at, reminder_sent_at, _NOW),
            OUTCOME_CONFIRMED_IN_GRACE,
        )

    def test_within_grace_period_without_reminder_is_silent_reset(self) -> None:
        detected_at = _NOW - timedelta(days=2)
        self.assertEqual(
            classify_payment_recovery(detected_at, None, _NOW), OUTCOME_SILENT_RESET
        )

    def test_custom_grace_period_days(self) -> None:
        detected_at = _NOW - timedelta(days=3)
        self.assertEqual(
            classify_payment_recovery(detected_at, None, _NOW, grace_period_days=3),
            OUTCOME_RECOVERED_FROM_SUSPENSION,
        )


class BuildPaymentRecoveryMessageTests(unittest.TestCase):
    def test_recovered_from_suspension_message(self) -> None:
        self.assertEqual(
            build_payment_recovery_message(OUTCOME_RECOVERED_FROM_SUSPENSION),
            PAYMENT_RECOVERED_MESSAGE,
        )
        self.assertIn("再開しました", PAYMENT_RECOVERED_MESSAGE)

    def test_confirmed_in_grace_message(self) -> None:
        self.assertEqual(
            build_payment_recovery_message(OUTCOME_CONFIRMED_IN_GRACE),
            PAYMENT_CONFIRMED_IN_GRACE_MESSAGE,
        )
        self.assertIn("解消されました", PAYMENT_CONFIRMED_IN_GRACE_MESSAGE)
        self.assertNotIn("再開", PAYMENT_CONFIRMED_IN_GRACE_MESSAGE)

    def test_unexpected_outcome_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_payment_recovery_message(OUTCOME_NO_DUNNING)
        with self.assertRaises(ValueError):
            build_payment_recovery_message(OUTCOME_SILENT_RESET)


class HandlePaymentSucceededTests(unittest.TestCase):
    def test_no_dunning_does_nothing(self) -> None:
        counter = InMemoryUsageCounter()
        push = InMemoryLinePushClient()
        result = handle_payment_succeeded("u1", counter, push, _NOW)
        self.assertEqual(result.outcome, OUTCOME_NO_DUNNING)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(push.sent, [])

    def test_recovered_from_suspension_notifies_and_resets(self) -> None:
        counter = InMemoryUsageCounter()
        counter.set_payment_failure_detected_at(
            "u1", _NOW - timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS + 1)
        )
        push = InMemoryLinePushClient()
        result = handle_payment_succeeded("u1", counter, push, _NOW)
        self.assertEqual(result.outcome, OUTCOME_RECOVERED_FROM_SUSPENSION)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_reset)
        self.assertEqual(len(push.sent), 1)
        self.assertIn("再開しました", push.sent[0][1])
        self.assertIsNone(counter.get_payment_failure_detected_at("u1"))

    def test_confirmed_in_grace_notifies_and_resets(self) -> None:
        counter = InMemoryUsageCounter()
        counter.set_payment_failure_detected_at("u2", _NOW - timedelta(days=5))
        counter.set_payment_failure_reminder_sent_at("u2", _NOW - timedelta(days=1))
        push = InMemoryLinePushClient()
        result = handle_payment_succeeded("u2", counter, push, _NOW)
        self.assertEqual(result.outcome, OUTCOME_CONFIRMED_IN_GRACE)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_reset)
        self.assertIn("解消されました", push.sent[0][1])
        self.assertIsNone(counter.get_payment_failure_detected_at("u2"))
        self.assertIsNone(counter.get_payment_failure_reminder_sent_at("u2"))

    def test_silent_reset_does_not_notify_but_clears_state(self) -> None:
        counter = InMemoryUsageCounter()
        counter.set_payment_failure_detected_at("u3", _NOW - timedelta(days=2))
        push = InMemoryLinePushClient()
        result = handle_payment_succeeded("u3", counter, push, _NOW)
        self.assertEqual(result.outcome, OUTCOME_SILENT_RESET)
        self.assertFalse(result.notified)
        self.assertTrue(result.state_reset)
        self.assertEqual(push.sent, [])
        self.assertIsNone(counter.get_payment_failure_detected_at("u3"))

    def test_send_failure_leaves_state_unchanged(self) -> None:
        counter = InMemoryUsageCounter()
        detected_at = _NOW - timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS + 1)
        counter.set_payment_failure_detected_at("u4", detected_at)
        push = _FailingLinePushClient()
        result = handle_payment_succeeded("u4", counter, push, _NOW)
        self.assertEqual(result.outcome, OUTCOME_SEND_FAILED)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(counter.get_payment_failure_detected_at("u4"), detected_at)

    def test_webhook_retry_after_success_is_idempotent(self) -> None:
        """状態クリア後の再送(Webhookリトライ)はOUTCOME_NO_DUNNINGに落ち、二重通知しない。"""
        counter = InMemoryUsageCounter()
        counter.set_payment_failure_detected_at(
            "u5", _NOW - timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS + 1)
        )
        push = InMemoryLinePushClient()
        first = handle_payment_succeeded("u5", counter, push, _NOW)
        self.assertTrue(first.notified)
        second = handle_payment_succeeded("u5", counter, push, _NOW)
        self.assertEqual(second.outcome, OUTCOME_NO_DUNNING)
        self.assertEqual(len(push.sent), 1)


if __name__ == "__main__":
    unittest.main()
