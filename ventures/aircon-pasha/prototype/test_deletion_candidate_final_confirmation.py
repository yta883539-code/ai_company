#!/usr/bin/env python3
"""deletion_candidate_final_confirmation.pyのテスト。
data-retention-policy.md「削除候補化後の最終確認」節の経路判定・絞り込み・送信配線を
検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from deletion_candidate_final_confirmation import (  # noqa: E402
    DELETION_CANDIDATE_FINAL_CONFIRMATION_ALT_TEXT,
    DeletionCandidateConfirmationRoute,
    DeletionCandidateConfirmationUserState,
    build_deletion_candidate_final_confirmation_flex_message,
    route_deletion_candidate_confirmation,
    select_due_deletion_candidate_final_confirmations,
    send_deletion_candidate_final_confirmations,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402


class _FakeStateStore:
    """set_deletion_confirmation_sent_at()・set_deletion_confirmation_unreachable_at()
    呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.sent_at: Dict[str, Optional[datetime]] = {}
        self.unreachable_at: Dict[str, Optional[datetime]] = {}

    def set_deletion_confirmation_sent_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self.sent_at[user_id] = value

    def set_deletion_confirmation_unreachable_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self.unreachable_at[user_id] = value


class _FailingLinePushClient:
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        raise LinePushDeliveryError("simulated outage")


class RouteDeletionCandidateConfirmationTest(unittest.TestCase):
    def test_following_user_routes_to_line_push(self) -> None:
        self.assertEqual(
            route_deletion_candidate_confirmation(is_following=True),
            DeletionCandidateConfirmationRoute.LINE_PUSH,
        )

    def test_blocked_user_routes_to_mark_unreachable(self) -> None:
        self.assertEqual(
            route_deletion_candidate_confirmation(is_following=False),
            DeletionCandidateConfirmationRoute.MARK_UNREACHABLE,
        )


class SelectDueDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 27, 4, 0, 0)

    def test_unsent_following_candidate_is_selected(self) -> None:
        users = [DeletionCandidateConfirmationUserState(user_id="u1", is_following=True)]
        self.assertEqual(
            [u.user_id for u in select_due_deletion_candidate_final_confirmations(users)],
            ["u1"],
        )

    def test_unsent_blocked_candidate_is_selected(self) -> None:
        """ブロック中(MARK_UNREACHABLE行き)でも、まだ確定送達していないため
        毎回の実行で対象に残り続ける(再フォロー後の切り替えを可能にするため)。"""
        users = [DeletionCandidateConfirmationUserState(user_id="u1", is_following=False)]
        self.assertEqual(
            [u.user_id for u in select_due_deletion_candidate_final_confirmations(users)],
            ["u1"],
        )

    def test_already_sent_candidate_is_excluded(self) -> None:
        users = [
            DeletionCandidateConfirmationUserState(
                user_id="u1",
                is_following=True,
                deletion_confirmation_sent_at=self.now,
            )
        ]
        self.assertEqual(select_due_deletion_candidate_final_confirmations(users), [])


class BuildDeletionCandidateFinalConfirmationFlexMessageTest(unittest.TestCase):
    def test_message_has_no_cta_button_and_contains_body_text(self) -> None:
        contents = build_deletion_candidate_final_confirmation_flex_message()
        self.assertEqual(contents["type"], "bubble")
        self.assertNotIn("footer", contents)
        body_texts = [c["text"] for c in contents["body"]["contents"]]
        self.assertTrue(any("保存期間ポリシー" in text for text in body_texts))


class SendDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 27, 4, 0, 0)

    def test_following_candidate_gets_line_push_and_sent_at_recorded(self) -> None:
        users = [DeletionCandidateConfirmationUserState(user_id="u1", is_following=True)]
        store = _FakeStateStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(users, self.now, store, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.sent_at["u1"], self.now)
        self.assertNotIn("u1", store.unreachable_at)
        self.assertEqual(len(push.sent), 1)
        sent_user_id, sent_alt_text, _sent_contents = push.sent[0]
        self.assertEqual(sent_user_id, "u1")
        self.assertEqual(sent_alt_text, DELETION_CANDIDATE_FINAL_CONFIRMATION_ALT_TEXT)

    def test_blocked_candidate_is_marked_unreachable_without_push_attempt(self) -> None:
        users = [DeletionCandidateConfirmationUserState(user_id="u2", is_following=False)]
        store = _FakeStateStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(users, self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, ["u2"])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.unreachable_at["u2"], self.now)
        self.assertNotIn("u2", store.sent_at)
        self.assertEqual(len(push.sent), 0)

    def test_push_delivery_failure_is_recorded_as_failed_and_not_marked_sent(self) -> None:
        users = [DeletionCandidateConfirmationUserState(user_id="u3", is_following=True)]
        store = _FakeStateStore()

        result = send_deletion_candidate_final_confirmations(
            users, self.now, store, _FailingLinePushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(result.failed, ["u3"])
        self.assertNotIn("u3", store.sent_at)

    def test_already_sent_candidate_is_skipped_entirely(self) -> None:
        users = [
            DeletionCandidateConfirmationUserState(
                user_id="u4", is_following=True, deletion_confirmation_sent_at=self.now
            )
        ]
        store = _FakeStateStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(users, self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(len(push.sent), 0)

    def test_reachable_and_blocked_candidates_are_handled_independently_in_one_batch(
        self,
    ) -> None:
        users = [
            DeletionCandidateConfirmationUserState(user_id="u1", is_following=True),
            DeletionCandidateConfirmationUserState(user_id="u2", is_following=False),
        ]
        store = _FakeStateStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(users, self.now, store, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.marked_unreachable, ["u2"])
        self.assertEqual(len(push.sent), 1)


if __name__ == "__main__":
    unittest.main()
