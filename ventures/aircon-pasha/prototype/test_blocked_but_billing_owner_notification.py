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
    BLOCKED_BUT_BILLING_OWNER_NOTIFICATION_ALT_TEXT,
    OWNER_LINE_USER_ID_PLACEHOLDER,
    build_blocked_but_billing_owner_notification_flex_message,
    clear_blocked_but_billing_owner_notified_at,
    select_new_blocked_but_billing_candidates_for_notification,
    send_blocked_but_billing_owner_notifications,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402


class _FakeNotifiedAtStore:
    """get/set_blocked_but_billing_owner_notified_at()呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self, initial: Optional[Dict[str, datetime]] = None) -> None:
        self.notified_at: Dict[str, datetime] = dict(initial or {})

    def get_blocked_but_billing_owner_notified_at(self, user_id: str) -> Optional[datetime]:
        return self.notified_at.get(user_id)

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        self.notified_at[user_id] = notified_at


class _FailingLinePushClient:
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        raise LinePushDeliveryError("simulated outage")


class SelectNewBlockedButBillingCandidatesForNotificationTest(unittest.TestCase):
    def test_unnotified_candidates_are_selected(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification(["u1", "u2"], store),
            ["u1", "u2"],
        )

    def test_already_notified_candidate_is_excluded(self) -> None:
        store = _FakeNotifiedAtStore({"u2": datetime(2026, 9, 1, 18, 0, 0)})
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification(["u1", "u2"], store),
            ["u1"],
        )

    def test_empty_candidates_returns_empty(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification([], store), []
        )

    def test_input_order_is_preserved(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertEqual(
            select_new_blocked_but_billing_candidates_for_notification(["u3", "u1", "u2"], store),
            ["u3", "u1", "u2"],
        )


class ClearBlockedButBillingOwnerNotifiedAtTest(unittest.TestCase):
    """design 6節「クリア配線」(フェーズ175)、
    clear_blocked_but_billing_owner_notified_at()自体の挙動を検証する。実際の呼び出し配線
    (フォロー再開・解約確定)側のテストはtest_cloud_function_webhook.py・
    test_stripe_dispatch.pyにそれぞれ追加する。"""

    def test_clears_when_notified_at_is_set(self) -> None:
        store = _FakeNotifiedAtStore({"u1": datetime(2026, 9, 1, 18, 0, 0)})
        self.assertTrue(clear_blocked_but_billing_owner_notified_at(store, "u1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("u1"))

    def test_returns_false_and_no_op_when_already_unset(self) -> None:
        store = _FakeNotifiedAtStore()
        self.assertFalse(clear_blocked_but_billing_owner_notified_at(store, "u1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("u1"))

    def test_only_clears_the_specified_user(self) -> None:
        store = _FakeNotifiedAtStore(
            {
                "u1": datetime(2026, 9, 1, 18, 0, 0),
                "u2": datetime(2026, 9, 1, 18, 0, 0),
            }
        )
        self.assertTrue(clear_blocked_but_billing_owner_notified_at(store, "u1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("u1"))
        self.assertIsNotNone(store.get_blocked_but_billing_owner_notified_at("u2"))


class BuildBlockedButBillingOwnerNotificationFlexMessageTest(unittest.TestCase):
    def test_message_contains_user_id(self) -> None:
        contents = build_blocked_but_billing_owner_notification_flex_message("u1")
        serialized = str(contents)
        self.assertIn("u1", serialized)
        self.assertIn("ブロック中かつ契約継続中", str(contents["body"]))

    def test_message_has_no_footer_button(self) -> None:
        contents = build_blocked_but_billing_owner_notification_flex_message("u1")
        self.assertNotIn("footer", contents)


class SendBlockedButBillingOwnerNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 2, 18, 0, 0)

    def test_sends_only_to_new_candidates_and_marks_notified(self) -> None:
        store = _FakeNotifiedAtStore({"u2": datetime(2026, 9, 1, 18, 0, 0)})
        push = InMemoryLinePushClient()

        result = send_blocked_but_billing_owner_notifications(
            ["u1", "u2", "u3"], self.now, store, push
        )

        self.assertEqual(result.sent, ["u1", "u3"])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.get_blocked_but_billing_owner_notified_at("u1"), self.now)
        self.assertEqual(store.get_blocked_but_billing_owner_notified_at("u3"), self.now)
        # u2は既存の通知日時から更新されない(再送しないため)。
        self.assertEqual(
            store.get_blocked_but_billing_owner_notified_at("u2"), datetime(2026, 9, 1, 18, 0, 0)
        )

    def test_all_messages_sent_to_fixed_owner_id(self) -> None:
        store = _FakeNotifiedAtStore()
        push = InMemoryLinePushClient()

        send_blocked_but_billing_owner_notifications(["u1", "u2"], self.now, store, push)

        self.assertEqual(len(push.sent), 2)
        for recipient, alt_text, _contents in push.sent:
            self.assertEqual(recipient, OWNER_LINE_USER_ID_PLACEHOLDER)
            self.assertEqual(alt_text, BLOCKED_BUT_BILLING_OWNER_NOTIFICATION_ALT_TEXT)

    def test_no_candidates_sends_nothing(self) -> None:
        store = _FakeNotifiedAtStore()
        push = InMemoryLinePushClient()

        result = send_blocked_but_billing_owner_notifications([], self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(push.sent, [])

    def test_delivery_failure_is_not_marked_notified(self) -> None:
        store = _FakeNotifiedAtStore()
        push = _FailingLinePushClient()

        result = send_blocked_but_billing_owner_notifications(["u1"], self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("u1"))

    def test_partial_failure_only_marks_successful_ones(self) -> None:
        store = _FakeNotifiedAtStore()

        class _PartiallyFailingClient:
            def __init__(self) -> None:
                self.sent: list[tuple[str, str, dict]] = []

            def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
                if "u2" in str(contents):
                    raise LinePushDeliveryError("simulated outage for u2")
                self.sent.append((user_id, alt_text, contents))

        push = _PartiallyFailingClient()
        result = send_blocked_but_billing_owner_notifications(
            ["u1", "u2", "u3"], self.now, store, push
        )

        self.assertEqual(result.sent, ["u1", "u3"])
        self.assertEqual(result.failed, ["u2"])
        self.assertIsNotNone(store.get_blocked_but_billing_owner_notified_at("u1"))
        self.assertIsNone(store.get_blocked_but_billing_owner_notified_at("u2"))
        self.assertIsNotNone(store.get_blocked_but_billing_owner_notified_at("u3"))


if __name__ == "__main__":
    unittest.main()
