#!/usr/bin/env python3
"""blocked_but_billing_owner_email_notification.pyの単体テスト。
blocked-but-billing-owner-email-notification-design.md(フェーズ続き177)の
仕様に沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from blocked_but_billing_owner_email_notification import (  # noqa: E402
    build_blocked_but_billing_owner_email,
    select_new_blocked_but_billing_candidates_for_email_notification,
    send_blocked_but_billing_owner_email_notifications,
)
from store_profile_store import InMemoryStoreProfileStore  # noqa: E402


def _set_candidate_store(
    store,
    store_id,
    *,
    owner_is_following=False,
    suspension_reason=None,
    owner_email=None,
    notified_at=None,
):
    store.set_owner_is_following(store_id, owner_is_following)
    store.set_suspension_reason(store_id, suspension_reason)
    if owner_email is not None:
        store.set_owner_email(store_id, owner_email)
    store.set_blocked_but_billing_owner_notified_at(store_id, notified_at)


class BuildBlockedButBillingOwnerEmailTest(unittest.TestCase):
    def test_subject_includes_store_id(self):
        content = build_blocked_but_billing_owner_email("store-1")
        self.assertIn("store-1", content.subject)

    def test_body_mentions_blocking_and_missed_notifications(self):
        content = build_blocked_but_billing_owner_email("store-1")
        self.assertIn("ブロック", content.body)
        self.assertIn("予約確定", content.body)

    def test_raises_on_empty_store_id(self):
        with self.assertRaises(ValueError):
            build_blocked_but_billing_owner_email("")


class SelectNewCandidatesForEmailNotificationTest(unittest.TestCase):
    def test_includes_candidate_with_email_and_not_yet_notified(self):
        store = InMemoryStoreProfileStore()
        _set_candidate_store(store, "store-1", owner_email="owner@example.com")
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_email_notification(store),
            ["store-1"],
        )

    def test_excludes_candidate_without_owner_email(self):
        store = InMemoryStoreProfileStore()
        _set_candidate_store(store, "store-1", owner_email=None)
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_email_notification(store), []
        )

    def test_excludes_candidate_already_notified(self):
        store = InMemoryStoreProfileStore()
        _set_candidate_store(
            store,
            "store-1",
            owner_email="owner@example.com",
            notified_at="2026-09-03T00:00:00Z",
        )
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_email_notification(store), []
        )

    def test_excludes_store_that_is_not_a_candidate_at_all(self):
        store = InMemoryStoreProfileStore()
        _set_candidate_store(
            store,
            "store-1",
            owner_is_following=True,
            owner_email="owner@example.com",
        )
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_email_notification(store), []
        )


class _FakeEmailSender:
    def __init__(self, failing_emails: Tuple[str, ...] = ()):
        self._failing_emails = set(failing_emails)
        self.sent: List[Dict[str, str]] = []

    def send(self, to_email: str, subject: str, body: str) -> bool:
        if to_email in self._failing_emails:
            return False
        self.sent.append({"to_email": to_email, "subject": subject, "body": body})
        return True


class SendBlockedButBillingOwnerEmailNotificationsTest(unittest.TestCase):
    def test_sends_to_each_new_candidate_and_marks_notified(self):
        store = InMemoryStoreProfileStore()
        _set_candidate_store(store, "store-1", owner_email="owner1@example.com")
        _set_candidate_store(store, "store-2", owner_email="owner2@example.com")
        sender = _FakeEmailSender()

        sent_store_ids = send_blocked_but_billing_owner_email_notifications(
            store, sender, notified_at="2026-09-03T01:00:00Z"
        )

        self.assertEqual(sent_store_ids, ["store-1", "store-2"])
        self.assertEqual(len(sender.sent), 2)
        self.assertEqual(
            store.get_blocked_but_billing_owner_notified_at("store-1"),
            "2026-09-03T01:00:00Z",
        )
        self.assertEqual(
            store.get_blocked_but_billing_owner_notified_at("store-2"),
            "2026-09-03T01:00:00Z",
        )

    def test_does_not_mark_notified_on_send_failure(self):
        store = InMemoryStoreProfileStore()
        _set_candidate_store(store, "store-1", owner_email="owner1@example.com")
        sender = _FakeEmailSender(failing_emails=("owner1@example.com",))

        sent_store_ids = send_blocked_but_billing_owner_email_notifications(
            store, sender, notified_at="2026-09-03T01:00:00Z"
        )

        self.assertEqual(sent_store_ids, [])
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("store-1"))

    def test_does_not_resend_to_already_notified_candidate(self):
        store = InMemoryStoreProfileStore()
        _set_candidate_store(
            store,
            "store-1",
            owner_email="owner1@example.com",
            notified_at="2026-09-02T00:00:00Z",
        )
        sender = _FakeEmailSender()

        sent_store_ids = send_blocked_but_billing_owner_email_notifications(
            store, sender, notified_at="2026-09-03T01:00:00Z"
        )

        self.assertEqual(sent_store_ids, [])
        self.assertEqual(len(sender.sent), 0)

    def test_raises_on_empty_notified_at(self):
        store = InMemoryStoreProfileStore()
        sender = _FakeEmailSender()
        with self.assertRaises(ValueError):
            send_blocked_but_billing_owner_email_notifications(store, sender, notified_at="")


if __name__ == "__main__":
    unittest.main()
