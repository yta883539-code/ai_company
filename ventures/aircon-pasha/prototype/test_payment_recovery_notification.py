#!/usr/bin/env python3
"""payment_recovery_notification.pyの単体テスト。
payment-failure-dunning-design.md 4節末尾の「決済成功による復旧通知の3分岐」の判定・
メッセージ整形・送信配線に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from payment_failure_reminder_scheduler import (  # noqa: E402
    PaymentFailureReminderUserState,
)
from payment_recovery_notification import (  # noqa: E402
    OUTCOME_CONFIRMED_IN_GRACE,
    OUTCOME_NO_DUNNING,
    OUTCOME_RECOVERED_FROM_SUSPENSION,
    OUTCOME_SEND_FAILED,
    OUTCOME_SILENT_RESET,
    InMemoryLinePushClient,
    LinePushDeliveryError,
    PAYMENT_CONFIRMED_IN_GRACE_MESSAGE,
    PAYMENT_RECOVERED_MESSAGE,
    build_payment_confirmed_in_grace_flex_message,
    build_payment_recovered_flex_message,
    classify_payment_recovery,
    handle_payment_succeeded,
)
from user_id_linking import InMemoryUserProfileStore, UserProfile  # noqa: E402

_EVENT_TIME = datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc)


def _store_with_user(user_id: str = "U1", **overrides) -> InMemoryUserProfileStore:
    store = InMemoryUserProfileStore()
    store.save(
        user_id,
        UserProfile(
            business_name="テスト洗浄社",
            business_type="独立系",
            email="test@example.com",
            linked_at=_EVENT_TIME,
            **overrides,
        ),
    )
    return store


class ClassifyPaymentRecoveryTest(unittest.TestCase):
    def test_suspended_is_recovered_from_suspension(self):
        state = PaymentFailureReminderUserState(
            user_id="u1",
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=10),
            payment_suspended_at=_EVENT_TIME - timedelta(days=1),
        )
        self.assertEqual(
            classify_payment_recovery(state), OUTCOME_RECOVERED_FROM_SUSPENSION
        )

    def test_suspended_takes_priority_even_if_reminder_also_sent(self):
        state = PaymentFailureReminderUserState(
            user_id="u1",
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=10),
            payment_suspended_at=_EVENT_TIME - timedelta(days=1),
            payment_failure_reminder_sent_at=_EVENT_TIME - timedelta(days=3),
        )
        self.assertEqual(
            classify_payment_recovery(state), OUTCOME_RECOVERED_FROM_SUSPENSION
        )

    def test_no_detection_is_no_dunning(self):
        state = PaymentFailureReminderUserState(
            user_id="u1", payment_failure_detected_at=None
        )
        self.assertEqual(classify_payment_recovery(state), OUTCOME_NO_DUNNING)

    def test_detected_with_reminder_sent_is_confirmed_in_grace(self):
        state = PaymentFailureReminderUserState(
            user_id="u1",
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=5),
            payment_failure_reminder_sent_at=_EVENT_TIME - timedelta(days=1),
        )
        self.assertEqual(
            classify_payment_recovery(state), OUTCOME_CONFIRMED_IN_GRACE
        )

    def test_detected_without_reminder_is_silent_reset(self):
        state = PaymentFailureReminderUserState(
            user_id="u1", payment_failure_detected_at=_EVENT_TIME - timedelta(days=1)
        )
        self.assertEqual(classify_payment_recovery(state), OUTCOME_SILENT_RESET)


class MessageBuilderTest(unittest.TestCase):
    def test_recovered_message_has_no_footer_button(self):
        contents = build_payment_recovered_flex_message()
        self.assertNotIn("footer", contents)
        self.assertEqual(
            contents["body"]["contents"][0]["text"], PAYMENT_RECOVERED_MESSAGE
        )

    def test_confirmed_in_grace_message_differs_from_recovered(self):
        contents = build_payment_confirmed_in_grace_flex_message()
        self.assertNotIn("footer", contents)
        self.assertEqual(
            contents["body"]["contents"][0]["text"],
            PAYMENT_CONFIRMED_IN_GRACE_MESSAGE,
        )
        self.assertNotEqual(
            PAYMENT_CONFIRMED_IN_GRACE_MESSAGE, PAYMENT_RECOVERED_MESSAGE
        )
        # 猶予期間中は生成が止まっていないため「再開」という表現を使わない。
        self.assertNotIn("再開", PAYMENT_CONFIRMED_IN_GRACE_MESSAGE)


class HandlePaymentSucceededTest(unittest.TestCase):
    def test_no_dunning_sends_nothing_and_does_not_touch_store(self):
        store = _store_with_user()
        push = InMemoryLinePushClient()
        state = PaymentFailureReminderUserState(
            user_id="U1", payment_failure_detected_at=None
        )

        result = handle_payment_succeeded(state, store, push)

        self.assertEqual(result.outcome, OUTCOME_NO_DUNNING)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(push.sent, [])

    def test_silent_reset_clears_state_without_sending(self):
        store = _store_with_user(payment_failure_detected_at=_EVENT_TIME)
        push = InMemoryLinePushClient()
        state = PaymentFailureReminderUserState(
            user_id="U1", payment_failure_detected_at=_EVENT_TIME
        )

        result = handle_payment_succeeded(state, store, push)

        self.assertEqual(result.outcome, OUTCOME_SILENT_RESET)
        self.assertFalse(result.notified)
        self.assertTrue(result.state_reset)
        self.assertEqual(push.sent, [])
        profile = store.get("U1")
        self.assertIsNone(profile.payment_failure_detected_at)

    def test_confirmed_in_grace_sends_and_clears_state(self):
        store = _store_with_user(
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=5),
            payment_failure_reminder_sent_at=_EVENT_TIME - timedelta(days=1),
        )
        push = InMemoryLinePushClient()
        state = PaymentFailureReminderUserState(
            user_id="U1",
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=5),
            payment_failure_reminder_sent_at=_EVENT_TIME - timedelta(days=1),
        )

        result = handle_payment_succeeded(state, store, push)

        self.assertEqual(result.outcome, OUTCOME_CONFIRMED_IN_GRACE)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_reset)
        self.assertEqual(len(push.sent), 1)
        user_id, _alt_text, contents = push.sent[0]
        self.assertEqual(user_id, "U1")
        self.assertEqual(
            contents["body"]["contents"][0]["text"], PAYMENT_CONFIRMED_IN_GRACE_MESSAGE
        )
        profile = store.get("U1")
        self.assertIsNone(profile.payment_failure_detected_at)
        self.assertIsNone(profile.payment_failure_reminder_sent_at)

    def test_recovered_from_suspension_sends_and_clears_state(self):
        store = _store_with_user(
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=10),
            payment_suspended_at=_EVENT_TIME - timedelta(days=1),
        )
        push = InMemoryLinePushClient()
        state = PaymentFailureReminderUserState(
            user_id="U1",
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=10),
            payment_suspended_at=_EVENT_TIME - timedelta(days=1),
        )

        result = handle_payment_succeeded(state, store, push)

        self.assertEqual(result.outcome, OUTCOME_RECOVERED_FROM_SUSPENSION)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_reset)
        user_id, _alt_text, contents = push.sent[0]
        self.assertEqual(
            contents["body"]["contents"][0]["text"], PAYMENT_RECOVERED_MESSAGE
        )
        profile = store.get("U1")
        self.assertIsNone(profile.payment_suspended_at)
        self.assertIsNone(profile.payment_failure_detected_at)

    def test_send_failure_leaves_state_untouched(self):
        store = _store_with_user(
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=10),
            payment_suspended_at=_EVENT_TIME - timedelta(days=1),
        )
        state = PaymentFailureReminderUserState(
            user_id="U1",
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=10),
            payment_suspended_at=_EVENT_TIME - timedelta(days=1),
        )

        class _FailingPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise LinePushDeliveryError("boom")

        result = handle_payment_succeeded(state, store, _FailingPushClient())

        self.assertEqual(result.outcome, OUTCOME_SEND_FAILED)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        profile = store.get("U1")
        self.assertIsNotNone(profile.payment_suspended_at)
        self.assertIsNotNone(profile.payment_failure_detected_at)

    def test_webhook_retry_after_success_is_idempotent(self):
        """1回成功した後、Webhookが再送されても状態リセット済みのためno_dunningに落ち、
        通知が二重に届かない(冪等性)。"""
        store = _store_with_user(
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=5),
            payment_failure_reminder_sent_at=_EVENT_TIME - timedelta(days=1),
        )
        push = InMemoryLinePushClient()
        state = PaymentFailureReminderUserState(
            user_id="U1",
            payment_failure_detected_at=_EVENT_TIME - timedelta(days=5),
            payment_failure_reminder_sent_at=_EVENT_TIME - timedelta(days=1),
        )
        handle_payment_succeeded(state, store, push)
        self.assertEqual(len(push.sent), 1)

        # 再送時はstoreの最新状態を読み直した前提の状態を渡す(全フィールドクリア済み)。
        retried_state = PaymentFailureReminderUserState(
            user_id="U1", payment_failure_detected_at=None
        )
        result = handle_payment_succeeded(retried_state, store, push)

        self.assertEqual(result.outcome, OUTCOME_NO_DUNNING)
        self.assertEqual(len(push.sent), 1)  # 増えていない


if __name__ == "__main__":
    unittest.main()
