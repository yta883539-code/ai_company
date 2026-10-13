#!/usr/bin/env python3
"""deletion_candidate_final_confirmation.pyのテスト。
data-retention-policy.md「削除候補化後の最終確認」節の経路判定・絞り込み・送信配線、
および「連絡不能」オーナーレビュー用レポートを検証する
(aircon-pasha版test_deletion_candidate_final_confirmation.pyと同じ構成だが、本venture
固有のworkshop_id単位・contractor_user_id解決の構造に合わせて調整している)。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).parent))

from deletion_candidate_final_confirmation import (  # noqa: E402
    DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE,
    DeletionCandidateConfirmationRoute,
    DeletionCandidateConfirmationWorkshopState,
    build_deletion_candidate_confirmation_states,
    list_unreachable_deletion_candidates,
    render_unreachable_deletion_candidates_report,
    route_deletion_candidate_confirmation,
    run_due_deletion_candidate_final_confirmations,
    select_due_deletion_candidate_final_confirmations,
    send_deletion_candidate_final_confirmations,
)
from subscription_cancellation_notification import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
)
from usage_counter_workshop import InMemoryUserProfileStore, InMemoryWorkshopStore  # noqa: E402


class _FakeWorkshopStore:
    """set_deletion_confirmation_sent_at()・set_deletion_confirmation_unreachable_at()
    呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.sent_at: Dict[str, Optional[datetime]] = {}
        self.unreachable_at: Dict[str, Optional[datetime]] = {}

    def set_deletion_confirmation_sent_at(
        self, workshop_id: str, sent_at: Optional[datetime]
    ) -> None:
        self.sent_at[workshop_id] = sent_at

    def set_deletion_confirmation_unreachable_at(
        self, workshop_id: str, unreachable_at: Optional[datetime]
    ) -> None:
        self.unreachable_at[workshop_id] = unreachable_at


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class RouteDeletionCandidateConfirmationTest(unittest.TestCase):
    def test_following_contractor_routes_to_line_push(self) -> None:
        self.assertEqual(
            route_deletion_candidate_confirmation(is_following=True),
            DeletionCandidateConfirmationRoute.LINE_PUSH,
        )

    def test_blocked_contractor_routes_to_mark_unreachable(self) -> None:
        self.assertEqual(
            route_deletion_candidate_confirmation(is_following=False),
            DeletionCandidateConfirmationRoute.MARK_UNREACHABLE,
        )


class SelectDueDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 9, 0, 0)

    def test_unsent_following_candidate_is_selected(self) -> None:
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w1", contractor_user_id="u1", is_following=True
            )
        ]
        self.assertEqual(
            [w.workshop_id for w in select_due_deletion_candidate_final_confirmations(workshops)],
            ["w1"],
        )

    def test_unsent_blocked_candidate_is_selected(self) -> None:
        """ブロック中(MARK_UNREACHABLE行き)でも、まだ確定送達していないため毎回の実行で
        対象に残り続ける(再フォロー後の切り替えを可能にするため)。"""
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w1", contractor_user_id="u1", is_following=False
            )
        ]
        self.assertEqual(
            [w.workshop_id for w in select_due_deletion_candidate_final_confirmations(workshops)],
            ["w1"],
        )

    def test_already_sent_candidate_is_excluded(self) -> None:
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w1",
                contractor_user_id="u1",
                is_following=True,
                deletion_confirmation_sent_at=self.now,
            )
        ]
        self.assertEqual(select_due_deletion_candidate_final_confirmations(workshops), [])


class SendDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 9, 0, 0)

    def test_following_candidate_gets_line_push_and_sent_at_recorded(self) -> None:
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w1", contractor_user_id="u1", is_following=True
            )
        ]
        store = _FakeWorkshopStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(workshops, self.now, store, push)

        self.assertEqual(result.sent, ["w1"])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.sent_at["w1"], self.now)
        self.assertNotIn("w1", store.unreachable_at)
        self.assertEqual(len(push.sent), 1)
        sent_user_id, sent_text = push.sent[0]
        self.assertEqual(sent_user_id, "u1")
        self.assertEqual(sent_text, DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE)

    def test_blocked_candidate_is_marked_unreachable_without_push_attempt(self) -> None:
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w2", contractor_user_id="u2", is_following=False
            )
        ]
        store = _FakeWorkshopStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(workshops, self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, ["w2"])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.unreachable_at["w2"], self.now)
        self.assertNotIn("w2", store.sent_at)
        self.assertEqual(len(push.sent), 0)

    def test_push_delivery_failure_is_recorded_as_failed_and_not_marked_sent(self) -> None:
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w3", contractor_user_id="u3", is_following=True
            )
        ]
        store = _FakeWorkshopStore()

        result = send_deletion_candidate_final_confirmations(
            workshops, self.now, store, _FailingLinePushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(result.failed, ["w3"])
        self.assertNotIn("w3", store.sent_at)

    def test_already_sent_candidate_is_skipped_entirely(self) -> None:
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w4",
                contractor_user_id="u4",
                is_following=True,
                deletion_confirmation_sent_at=self.now,
            )
        ]
        store = _FakeWorkshopStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(workshops, self.now, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(len(push.sent), 0)

    def test_reachable_and_blocked_candidates_are_handled_independently_in_one_batch(
        self,
    ) -> None:
        workshops = [
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w1", contractor_user_id="u1", is_following=True
            ),
            DeletionCandidateConfirmationWorkshopState(
                workshop_id="w2", contractor_user_id="u2", is_following=False
            ),
        ]
        store = _FakeWorkshopStore()
        push = InMemoryLinePushClient()

        result = send_deletion_candidate_final_confirmations(workshops, self.now, store, push)

        self.assertEqual(result.sent, ["w1"])
        self.assertEqual(result.marked_unreachable, ["w2"])
        self.assertEqual(len(push.sent), 1)


class BuildDeletionCandidateConfirmationStatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 9, 0, 0)
        self.workshop_store = InMemoryWorkshopStore()
        self.user_profile_store = InMemoryUserProfileStore()

    def test_reads_contractor_is_following_and_sent_at_for_each_candidate_in_order(
        self,
    ) -> None:
        self.workshop_store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])
        self.workshop_store.set_members("w2", contractor_user_id="u2", member_user_ids=["u2"])
        self.user_profile_store.set_is_following("u1", True)
        self.user_profile_store.set_is_following("u2", False)
        self.workshop_store.set_deletion_confirmation_sent_at("w2", self.now)

        states = build_deletion_candidate_confirmation_states(
            ["w1", "w2"], self.workshop_store, self.user_profile_store
        )

        self.assertEqual([s.workshop_id for s in states], ["w1", "w2"])
        self.assertEqual(states[0].contractor_user_id, "u1")
        self.assertTrue(states[0].is_following)
        self.assertIsNone(states[0].deletion_confirmation_sent_at)
        self.assertEqual(states[1].contractor_user_id, "u2")
        self.assertFalse(states[1].is_following)
        self.assertEqual(states[1].deletion_confirmation_sent_at, self.now)


class RunDueDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    """run_due_deletion_candidate_final_confirmations()の結合テスト
    (InMemoryWorkshopStore/InMemoryUserProfileStoreを実store代わりに使う、他スケジューラの
    結合テストと同じ構成)。"""

    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 9, 0, 0)
        self.workshop_store = InMemoryWorkshopStore()
        self.user_profile_store = InMemoryUserProfileStore()

    def test_due_following_candidate_receives_push_and_is_marked_sent(self) -> None:
        self.workshop_store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])
        self.workshop_store.set_deletion_candidate_at("w1", self.now - timedelta(days=1))
        push = InMemoryLinePushClient()

        result = run_due_deletion_candidate_final_confirmations(
            self.workshop_store, self.user_profile_store, self.now, push
        )

        self.assertEqual(result.sent, ["w1"])
        self.assertEqual(self.workshop_store.get_deletion_confirmation_sent_at("w1"), self.now)
        self.assertEqual(len(push.sent), 1)

    def test_due_blocked_candidate_is_marked_unreachable_without_push(self) -> None:
        self.workshop_store.set_members("w2", contractor_user_id="u2", member_user_ids=["u2"])
        self.workshop_store.set_deletion_candidate_at("w2", self.now - timedelta(days=1))
        self.user_profile_store.set_is_following("u2", False)
        push = InMemoryLinePushClient()

        result = run_due_deletion_candidate_final_confirmations(
            self.workshop_store, self.user_profile_store, self.now, push
        )

        self.assertEqual(result.marked_unreachable, ["w2"])
        self.assertEqual(
            self.workshop_store.get_deletion_confirmation_unreachable_at("w2"), self.now
        )
        self.assertEqual(len(push.sent), 0)

    def test_candidate_not_yet_due_is_excluded(self) -> None:
        self.workshop_store.set_members("w3", contractor_user_id="u3", member_user_ids=["u3"])
        self.workshop_store.set_deletion_candidate_at("w3", self.now + timedelta(days=1))
        push = InMemoryLinePushClient()

        result = run_due_deletion_candidate_final_confirmations(
            self.workshop_store, self.user_profile_store, self.now, push
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertIsNone(self.workshop_store.get_deletion_confirmation_sent_at("w3"))

    def test_second_run_does_not_resend_to_already_confirmed_candidate(self) -> None:
        self.workshop_store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])
        self.workshop_store.set_deletion_candidate_at("w1", self.now - timedelta(days=1))
        push = InMemoryLinePushClient()
        run_due_deletion_candidate_final_confirmations(
            self.workshop_store, self.user_profile_store, self.now, push
        )

        second_result = run_due_deletion_candidate_final_confirmations(
            self.workshop_store, self.user_profile_store, self.now, push
        )

        self.assertEqual(second_result.sent, [])
        self.assertEqual(len(push.sent), 1)


class ListUnreachableDeletionCandidatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 9, 0, 0)
        self.store = InMemoryWorkshopStore()

    def _make_workshop(self, workshop_id: str) -> None:
        self.store.set_members(
            workshop_id, contractor_user_id=f"{workshop_id}-u", member_user_ids=[f"{workshop_id}-u"]
        )

    def test_returns_empty_list_when_no_candidate_is_unreachable(self) -> None:
        self._make_workshop("w1")
        self.assertEqual(list_unreachable_deletion_candidates(self.store, self.now), [])

    def test_workshop_marked_unreachable_is_included_with_days_since(self) -> None:
        self._make_workshop("w1")
        unreachable_at = self.now - timedelta(days=10)
        self.store.set_deletion_confirmation_unreachable_at("w1", unreachable_at)

        candidates = list_unreachable_deletion_candidates(self.store, self.now)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].workshop_id, "w1")
        self.assertEqual(candidates[0].deletion_confirmation_unreachable_at, unreachable_at)
        self.assertEqual(candidates[0].days_since_unreachable, 10)

    def test_results_are_sorted_by_workshop_id(self) -> None:
        self._make_workshop("w2")
        self._make_workshop("w1")
        self.store.set_deletion_confirmation_unreachable_at("w2", self.now - timedelta(days=1))
        self.store.set_deletion_confirmation_unreachable_at("w1", self.now - timedelta(days=2))

        candidates = list_unreachable_deletion_candidates(self.store, self.now)

        self.assertEqual([c.workshop_id for c in candidates], ["w1", "w2"])

    def test_workshop_without_unreachable_flag_is_excluded_even_if_other_unreachable_exists(
        self,
    ) -> None:
        self._make_workshop("w1")
        self._make_workshop("w2")
        self.store.set_deletion_confirmation_unreachable_at("w1", self.now - timedelta(days=1))

        candidates = list_unreachable_deletion_candidates(self.store, self.now)

        self.assertEqual([c.workshop_id for c in candidates], ["w1"])


class RenderUnreachableDeletionCandidatesReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 9, 0, 0)

    def test_empty_candidates_returns_no_candidate_message(self) -> None:
        self.assertEqual(
            render_unreachable_deletion_candidates_report([]),
            "連絡不能の削除候補工房はいません。",
        )

    def test_report_includes_count_workshop_id_and_disclaimer(self) -> None:
        store = InMemoryWorkshopStore()
        store.set_members("w1", contractor_user_id="w1-u", member_user_ids=["w1-u"])
        store.set_deletion_confirmation_unreachable_at("w1", self.now - timedelta(days=5))
        candidates = list_unreachable_deletion_candidates(store, self.now)

        report = render_unreachable_deletion_candidates_report(candidates)

        self.assertIn("1件", report)
        self.assertIn("w1", report)
        self.assertIn("5日経過", report)
        self.assertIn("自動削除の対象ではありません", report)


if __name__ == "__main__":
    unittest.main()
