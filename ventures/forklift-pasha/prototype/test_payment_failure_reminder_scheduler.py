#!/usr/bin/env python3
import unittest
from datetime import datetime, timedelta

from trial_end_email_scheduler import EmailDeliveryError, InMemoryEmailSenderClient
from trial_management import InMemoryFleetOperatorStore

from payment_failure_reminder_scheduler import (
    OWNER_NOTIFICATION_EMAIL_PLACEHOLDER,
    run_due_payment_failure_reminders,
    run_due_payment_suspension_owner_notifications,
    select_due_payment_failure_reminders,
    select_due_payment_suspension_owner_notifications,
    send_payment_failure_reminders,
    send_payment_suspension_owner_notifications,
)

NOW = datetime(2026, 10, 18, 4, 0, 0)


def _upgraded_with_failure(store: InMemoryFleetOperatorStore, internal_id: str, days_ago: int) -> None:
    store.set_email(internal_id, f"{internal_id}@example.com")
    store.set_upgraded_at(internal_id, NOW - timedelta(days=60))
    store.set_payment_failure_detected_at(internal_id, NOW - timedelta(days=days_ago))


class TestSelectDuePaymentFailureReminders(unittest.TestCase):
    def test_four_days_since_detection_is_due(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=4)
        self.assertEqual(select_due_payment_failure_reminders(["fo_1"], NOW, store), ["fo_1"])

    def test_three_days_since_detection_is_not_due(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=3)
        self.assertEqual(select_due_payment_failure_reminders(["fo_1"], NOW, store), [])

    def test_already_suspended_is_excluded(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=9)  # 猶予期間(7日)超過=制限モード
        self.assertEqual(select_due_payment_failure_reminders(["fo_1"], NOW, store), [])

    def test_already_reminded_is_excluded(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=5)
        store.set_payment_failure_reminder_sent_at("fo_1", NOW - timedelta(days=1))
        self.assertEqual(select_due_payment_failure_reminders(["fo_1"], NOW, store), [])

    def test_no_detected_failure_is_excluded(self):
        store = InMemoryFleetOperatorStore()
        store.set_email("fo_1", "fo_1@example.com")
        store.set_upgraded_at("fo_1", NOW - timedelta(days=60))
        self.assertEqual(select_due_payment_failure_reminders(["fo_1"], NOW, store), [])

    def test_trial_user_without_upgrade_is_excluded(self):
        store = InMemoryFleetOperatorStore()
        store.set_email("fo_1", "fo_1@example.com")
        store.set_payment_failure_detected_at("fo_1", NOW - timedelta(days=4))
        self.assertEqual(select_due_payment_failure_reminders(["fo_1"], NOW, store), [])


class TestSendPaymentFailureReminders(unittest.TestCase):
    def test_sends_and_marks_sent_at(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=4)
        client = InMemoryEmailSenderClient()

        result = send_payment_failure_reminders(["fo_1"], NOW, store, client)

        self.assertEqual(result.sent, ["fo_1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.get_payment_failure_reminder_sent_at("fo_1"), NOW)
        self.assertEqual(len(client.sent), 1)
        self.assertEqual(client.sent[0][0], "fo_1@example.com")

    def test_skips_missing_email(self):
        store = InMemoryFleetOperatorStore()
        store.set_upgraded_at("fo_1", NOW - timedelta(days=60))
        store.set_payment_failure_detected_at("fo_1", NOW - timedelta(days=4))
        client = InMemoryEmailSenderClient()

        result = send_payment_failure_reminders(["fo_1"], NOW, store, client)

        self.assertEqual(result.skipped_no_email, ["fo_1"])
        self.assertEqual(store.get_payment_failure_reminder_sent_at("fo_1"), None)

    def test_delivery_failure_does_not_mark_sent_at(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=4)

        class _FailingClient:
            def send_email(self, to_email, subject, body):
                raise EmailDeliveryError("boom")

        result = send_payment_failure_reminders(["fo_1"], NOW, store, _FailingClient())

        self.assertEqual(result.failed, ["fo_1"])
        self.assertEqual(store.get_payment_failure_reminder_sent_at("fo_1"), None)


class TestOwnerNotification(unittest.TestCase):
    def test_suspended_and_unnotified_is_due(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=9)
        self.assertEqual(
            select_due_payment_suspension_owner_notifications(["fo_1"], NOW, store), ["fo_1"]
        )

    def test_not_yet_suspended_is_excluded(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=4)
        self.assertEqual(
            select_due_payment_suspension_owner_notifications(["fo_1"], NOW, store), []
        )

    def test_already_notified_is_excluded(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=9)
        store.set_payment_suspension_owner_notified_at("fo_1", NOW - timedelta(days=1))
        self.assertEqual(
            select_due_payment_suspension_owner_notifications(["fo_1"], NOW, store), []
        )

    def test_send_marks_notified_at_and_uses_owner_placeholder(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=9)
        client = InMemoryEmailSenderClient()

        result = send_payment_suspension_owner_notifications(["fo_1"], NOW, store, client)

        self.assertEqual(result.sent, ["fo_1"])
        self.assertEqual(store.get_payment_suspension_owner_notified_at("fo_1"), NOW)
        self.assertEqual(client.sent[0][0], OWNER_NOTIFICATION_EMAIL_PLACEHOLDER)


class TestRunDueWrappers(unittest.TestCase):
    """フェーズ171: store.all_internal_ids()による全事業者列挙込みのwrapper
    (run_due_payment_failure_reminders()/run_due_payment_suspension_owner_notifications())が
    send_*()への受け渡し前に行う列挙そのものを担うことを確認する。"""

    def test_run_due_payment_failure_reminders_covers_all_internal_ids(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=4)
        _upgraded_with_failure(store, "fo_2", days_ago=1)  # 未到達
        client = InMemoryEmailSenderClient()

        result = run_due_payment_failure_reminders(store, NOW, client)

        self.assertEqual(result.sent, ["fo_1"])
        self.assertEqual(store.get_payment_failure_reminder_sent_at("fo_1"), NOW)
        self.assertIsNone(store.get_payment_failure_reminder_sent_at("fo_2"))

    def test_run_due_payment_suspension_owner_notifications_covers_all_internal_ids(self):
        store = InMemoryFleetOperatorStore()
        _upgraded_with_failure(store, "fo_1", days_ago=9)  # 制限モード移行済み
        _upgraded_with_failure(store, "fo_2", days_ago=4)  # 未移行
        client = InMemoryEmailSenderClient()

        result = run_due_payment_suspension_owner_notifications(store, NOW, client)

        self.assertEqual(result.sent, ["fo_1"])
        self.assertEqual(store.get_payment_suspension_owner_notified_at("fo_1"), NOW)
        self.assertIsNone(store.get_payment_suspension_owner_notified_at("fo_2"))


if __name__ == "__main__":
    unittest.main()
