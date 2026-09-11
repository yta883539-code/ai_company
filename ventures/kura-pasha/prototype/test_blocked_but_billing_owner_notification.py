#!/usr/bin/env python3
"""blocked_but_billing_owner_notification.pyのテスト。
blocked-but-billing-owner-notification-design.md 3〜4節の抽出条件を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from blocked_but_billing_owner_notification import (  # noqa: E402
    OWNER_LINE_USER_ID_PLACEHOLDER,
    build_blocked_but_billing_owner_notification_message,
    clear_blocked_but_billing_owner_notified_at,
    select_new_blocked_but_billing_candidates_for_notification,
    send_blocked_but_billing_owner_notifications,
)
from subscription_cancellation_notification import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
)


class _FakeNotifiedAtStore:
    """get/set_blocked_but_billing_owner_notified_at()呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self, initial: Optional[Dict[str, datetime]] = None) -> None:
        self.notified_at: Dict[str, datetime] = dict(initial or {})

    def get_blocked_but_billing_owner_notified_at(self, workshop_id: str) -> Optional[datetime]:
        return self.notified_at.get(workshop_id)

    def set_blocked_but_billing_owner_notified_at(
        self, workshop_id: str, notified_at: Optional[datetime]
    ) -> None:
        if notified_at is None:
            self.notified_at.pop(workshop_id, None)
        else:
            self.notified_at[workshop_id] = notified_at


class _FakeContractorResolver:
    def __init__(self, contractor_by_workshop: Optional[Dict[str, str]] = None) -> None:
        self._contractor_by_workshop = dict(contractor_by_workshop or {})

    def get_contractor_user_id(self, workshop_id: str) -> str:
        return self._contractor_by_workshop.get(workshop_id, f"contractor-of-{workshop_id}")


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class SelectNewBlockedButBillingCandidatesForNotificationTest(unittest.TestCase):
    def test_unnotified_candidates_are_selected(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification(["w1", "w2"], store),
            ["w1", "w2"],
        )

    def test_already_notified_candidate_is_excluded(self) -> None:
        store = _FakeNotifiedAtStore({"w2": datetime(2026, 9, 10, 18, 0, 0)})
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification(["w1", "w2"], store),
            ["w1"],
        )

    def test_empty_candidates_returns_empty(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification([], store), []
        )

    def test_input_order_is_preserved(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification(["w3", "w1", "w2"], store),
            ["w3", "w1", "w2"],
        )


class ClearBlockedButBillingOwnerNotifiedAtTest(unittest.TestCase):
    """design 6節「クリア配線」、clear_blocked_but_billing_owner_notified_at()自体の挙動を
    検証する。実際の呼び出し配線(フォロー再開・解約確定)側のテストはtest_cloud_function_
    webhook.py・test_stripe_webhook.pyにそれぞれ追加する。"""

    def test_clears_when_notified_at_is_set(self) -> None:
        store = _FakeNotifiedAtStore({"w1": datetime(2026, 9, 10, 18, 0, 0)})
        self.assertTrue(clear_blocked_but_billing_owner_notified_at(store, "w1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("w1"))

    def test_returns_false_and_no_op_when_already_unset(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertFalse(clear_blocked_but_billing_owner_notified_at(store, "w1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("w1"))

    def test_only_clears_the_specified_workshop(self) -> None:
        store = _FakeNotifiedAtStore(
            {
                "w1": datetime(2026, 9, 10, 18, 0, 0),
                "w2": datetime(2026, 9, 10, 18, 0, 0),
            }
        )
        self.assertTrue(clear_blocked_but_billing_owner_notified_at(store, "w1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("w1"))
        self.assertIsNotNone(store.get_blocked_but_billing_owner_notified_at("w2"))


class BuildBlockedButBillingOwnerNotificationMessageTest(unittest.TestCase):
    def test_message_contains_contractor_user_id(self) -> None:
        text = build_blocked_but_billing_owner_notification_message("u1")
        self.assertIn("u1", text)
        self.assertIn("ブロック中かつ契約継続中", text)


class SendBlockedButBillingOwnerNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 11, 6, 0, 0)
        self.resolver = _FakeContractorResolver(
            {"w1": "u1", "w2": "u2", "w3": "u3"}
        )

    def test_sends_only_to_new_candidates_and_marks_notified(self) -> None:
        store = _FakeNotifiedAtStore({"w2": datetime(2026, 9, 10, 18, 0, 0)})
        push = InMemoryLinePushClient()

        result = send_blocked_but_billing_owner_notifications(
            ["w1", "w2", "w3"], self.now, store, push, self.resolver
        )

        self.assertEqual(result.sent, ["w1", "w3"])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.get_blocked_but_billing_owner_notified_at("w1"), self.now)
        self.assertEqual(store.get_blocked_but_billing_owner_notified_at("w3"), self.now)
        # w2は既存の通知日時から更新されない(再送しないため)。
        self.assertEqual(
            store.get_blocked_but_billing_owner_notified_at("w2"), datetime(2026, 9, 10, 18, 0, 0)
        )

    def test_all_messages_sent_to_fixed_owner_id(self) -> None:
        store = _FakeNotifiedAtStore()
        push = InMemoryLinePushClient()

        send_blocked_but_billing_owner_notifications(
            ["w1", "w2"], self.now, store, push, self.resolver
        )

        self.assertEqual(len(push.sent), 2)
        for recipient, text in push.sent:
            self.assertEqual(recipient, OWNER_LINE_USER_ID_PLACEHOLDER)
            self.assertIn("ブロック中かつ契約継続中", text)

    def test_message_uses_contractor_user_id_not_workshop_id(self) -> None:
        store = _FakeNotifiedAtStore()
        push = InMemoryLinePushClient()

        send_blocked_but_billing_owner_notifications(
            ["w1"], self.now, store, push, self.resolver
        )

        _recipient, text = push.sent[0]
        self.assertIn("u1", text)
        self.assertNotIn("w1", text)

    def test_no_candidates_sends_nothing(self) -> None:
        store = _FakeNotifiedAtStore()
        push = InMemoryLinePushClient()

        result = send_blocked_but_billing_owner_notifications(
            [], self.now, store, push, self.resolver
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(push.sent, [])

    def test_delivery_failure_is_not_marked_notified(self) -> None:
        store = _FakeNotifiedAtStore()
        push = _FailingLinePushClient()

        result = send_blocked_but_billing_owner_notifications(
            ["w1"], self.now, store, push, self.resolver
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["w1"])
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("w1"))

    def test_partial_failure_only_marks_successful_ones(self) -> None:
        store = _FakeNotifiedAtStore()

        class _PartiallyFailingClient:
            def __init__(self) -> None:
                self.sent: list[tuple[str, str]] = []

            def send_message(self, user_id: str, text: str) -> None:
                if "u2" in text:
                    raise LinePushDeliveryError("simulated outage for u2")
                self.sent.append((user_id, text))

        push = _PartiallyFailingClient()
        result = send_blocked_but_billing_owner_notifications(
            ["w1", "w2", "w3"], self.now, store, push, self.resolver
        )

        self.assertEqual(result.sent, ["w1", "w3"])
        self.assertEqual(result.failed, ["w2"])
        self.assertIsNotNone(store.get_blocked_but_billing_owner_notified_at("w1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("w2"))
        self.assertIsNotNone(store.get_blocked_but_billing_owner_notified_at("w3"))


if __name__ == "__main__":
    unittest.main()
