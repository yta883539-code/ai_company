#!/usr/bin/env python3
"""deletion_candidate_final_confirmation.pyのテスト(README.mdフェーズ292)。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from application_form_submission_flow import InMemoryUserProfileStore  # noqa: E402
from deletion_candidate import InMemoryProfileDeletionCandidateStore  # noqa: E402
from deletion_candidate_final_confirmation import (  # noqa: E402
    DeletionCandidateConfirmationRoute,
    DeletionCandidateConfirmationUserState,
    build_deletion_candidate_confirmation_states,
    list_unreachable_deletion_candidates,
    render_deletion_candidate_final_confirmation_message,
    render_unreachable_deletion_candidates_report,
    route_deletion_candidate_confirmation,
    run_due_deletion_candidate_final_confirmations,
    select_due_deletion_candidate_final_confirmations,
    send_deletion_candidate_final_confirmations,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError

NOW = datetime(2026, 10, 12, 18, 0, 0)


class RouteDeletionCandidateConfirmationTest(unittest.TestCase):
    def test_following_routes_to_line_push(self):
        self.assertEqual(
            route_deletion_candidate_confirmation(True),
            DeletionCandidateConfirmationRoute.LINE_PUSH,
        )

    def test_blocked_routes_to_mark_unreachable(self):
        self.assertEqual(
            route_deletion_candidate_confirmation(False),
            DeletionCandidateConfirmationRoute.MARK_UNREACHABLE,
        )


class SelectDueDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    def test_excludes_already_sent_and_keeps_input_order(self):
        users = [
            DeletionCandidateConfirmationUserState(user_id="u1", is_following=True),
            DeletionCandidateConfirmationUserState(
                user_id="u2", is_following=True, deletion_confirmation_sent_at=NOW
            ),
            DeletionCandidateConfirmationUserState(user_id="u3", is_following=False),
        ]

        due = select_due_deletion_candidate_final_confirmations(users)

        self.assertEqual([u.user_id for u in due], ["u1", "u3"])


class BuildDeletionCandidateConfirmationStatesTest(unittest.TestCase):
    def test_reads_is_following_and_sent_at_from_respective_stores(self):
        deletion_store = InMemoryProfileDeletionCandidateStore()
        deletion_store.set_deletion_confirmation_sent_at("u2", NOW)
        profile_store = InMemoryUserProfileStore()
        profile_store.set_is_following("u1", True)
        profile_store.set_is_following("u2", False)
        # u3はis_following未記録: デフォルトのTrue(安全側)を期待する。

        states = build_deletion_candidate_confirmation_states(
            ["u1", "u2", "u3"], deletion_store, profile_store
        )

        self.assertEqual(
            states,
            [
                DeletionCandidateConfirmationUserState(
                    user_id="u1", is_following=True, deletion_confirmation_sent_at=None
                ),
                DeletionCandidateConfirmationUserState(
                    user_id="u2", is_following=False, deletion_confirmation_sent_at=NOW
                ),
                DeletionCandidateConfirmationUserState(
                    user_id="u3", is_following=True, deletion_confirmation_sent_at=None
                ),
            ],
        )


class SendDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    def test_following_user_receives_push_and_sent_at_is_recorded(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryLinePushClient()
        users = [DeletionCandidateConfirmationUserState(user_id="u1", is_following=True)]

        result = send_deletion_candidate_final_confirmations(users, NOW, store, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(store.get_deletion_confirmation_sent_at("u1"), NOW)
        self.assertEqual(
            push.sent, [("u1", render_deletion_candidate_final_confirmation_message())]
        )

    def test_blocked_user_is_marked_unreachable_without_sending(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryLinePushClient()
        users = [DeletionCandidateConfirmationUserState(user_id="u2", is_following=False)]

        result = send_deletion_candidate_final_confirmations(users, NOW, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, ["u2"])
        self.assertEqual(store.get_deletion_confirmation_unreachable_at("u2"), NOW)
        self.assertEqual(push.sent, [])

    def test_push_delivery_error_is_recorded_as_failed_without_writing_sent_at(self):
        store = InMemoryProfileDeletionCandidateStore()

        class _FailingPushClient:
            def send_message(self, user_id, text):
                raise LinePushDeliveryError("boom")

        users = [DeletionCandidateConfirmationUserState(user_id="u1", is_following=True)]

        result = send_deletion_candidate_final_confirmations(
            users, NOW, store, _FailingPushClient()
        )

        self.assertEqual(result.failed, ["u1"])
        self.assertEqual(result.sent, [])
        self.assertIsNone(store.get_deletion_confirmation_sent_at("u1"))

    def test_already_sent_user_is_skipped_entirely(self):
        store = InMemoryProfileDeletionCandidateStore()
        push = InMemoryLinePushClient()
        users = [
            DeletionCandidateConfirmationUserState(
                user_id="u3", is_following=True, deletion_confirmation_sent_at=NOW
            )
        ]

        result = send_deletion_candidate_final_confirmations(users, NOW, store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(push.sent, [])


class RunDueDeletionCandidateFinalConfirmationsTest(unittest.TestCase):
    def test_wires_candidate_listing_through_to_sending(self):
        deletion_store = InMemoryProfileDeletionCandidateStore()
        deletion_store.set_deletion_candidate_at("u1", NOW)
        deletion_store.set_deletion_candidate_at("u2", NOW)
        profile_store = InMemoryUserProfileStore()
        profile_store.set_is_following("u1", True)
        profile_store.set_is_following("u2", False)
        push = InMemoryLinePushClient()

        result = run_due_deletion_candidate_final_confirmations(
            deletion_store, profile_store, NOW, push
        )

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.marked_unreachable, ["u2"])
        self.assertEqual(deletion_store.get_deletion_confirmation_sent_at("u1"), NOW)
        self.assertEqual(deletion_store.get_deletion_confirmation_unreachable_at("u2"), NOW)

    def test_candidates_not_yet_due_are_excluded(self):
        deletion_store = InMemoryProfileDeletionCandidateStore()
        future = datetime(2027, 1, 1, 0, 0, 0)
        deletion_store.set_deletion_candidate_at("u1", future)
        profile_store = InMemoryUserProfileStore()
        push = InMemoryLinePushClient()

        result = run_due_deletion_candidate_final_confirmations(
            deletion_store, profile_store, NOW, push
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(push.sent, [])


class ListUnreachableDeletionCandidatesTest(unittest.TestCase):
    """deletion-candidate-unreachable-owner-review-design.md 4節の選定ロジックのテスト
    (aircon-pashaフェーズ311の横展開)。本venture固有の`deletion_store`
    (`InMemoryProfileDeletionCandidateStore`)は、`all_user_ids()`が
    `deletion_candidate_at`が設定済みのuser_idのみを返す構成のため、各テストで
    `set_deletion_candidate_at()`も呼んでuser_idを登録する。"""

    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 6, 0, 0)
        self.store = InMemoryProfileDeletionCandidateStore()

    def _register(self, user_id: str, **overrides) -> None:
        self.store.set_deletion_candidate_at(user_id, self.now)
        if "unreachable_at" in overrides:
            self.store.set_deletion_confirmation_unreachable_at(
                user_id, overrides["unreachable_at"]
            )

    def test_returns_empty_list_when_no_candidate_is_unreachable(self) -> None:
        self._register("u1")
        self.assertEqual(list_unreachable_deletion_candidates(self.store, self.now), [])

    def test_user_marked_unreachable_is_included_with_days_since(self) -> None:
        unreachable_at = self.now - timedelta(days=10)
        self._register("u1", unreachable_at=unreachable_at)

        candidates = list_unreachable_deletion_candidates(self.store, self.now)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].user_id, "u1")
        self.assertEqual(
            candidates[0].deletion_confirmation_unreachable_at, unreachable_at
        )
        self.assertEqual(candidates[0].days_since_unreachable, 10)

    def test_results_are_sorted_by_user_id(self) -> None:
        self._register("u2", unreachable_at=self.now - timedelta(days=1))
        self._register("u1", unreachable_at=self.now - timedelta(days=2))

        candidates = list_unreachable_deletion_candidates(self.store, self.now)

        self.assertEqual([c.user_id for c in candidates], ["u1", "u2"])

    def test_user_without_unreachable_flag_is_excluded_even_if_other_unreachable_exists(
        self,
    ) -> None:
        self._register("u1", unreachable_at=self.now - timedelta(days=1))
        self._register("u2")

        candidates = list_unreachable_deletion_candidates(self.store, self.now)

        self.assertEqual([c.user_id for c in candidates], ["u1"])


class RenderUnreachableDeletionCandidatesReportTest(unittest.TestCase):
    """render_unreachable_deletion_candidates_report()のテスト
    (aircon-pashaフェーズ311の横展開)。"""

    def setUp(self) -> None:
        self.now = datetime(2026, 10, 13, 6, 0, 0)

    def test_empty_candidates_returns_no_candidate_message(self) -> None:
        self.assertEqual(
            render_unreachable_deletion_candidates_report([]),
            "連絡不能の削除候補ユーザーはいません。",
        )

    def test_report_includes_count_user_id_and_disclaimer(self) -> None:
        store = InMemoryProfileDeletionCandidateStore()
        store.set_deletion_candidate_at("u1", self.now)
        store.set_deletion_confirmation_unreachable_at(
            "u1", self.now - timedelta(days=5)
        )
        candidates = list_unreachable_deletion_candidates(store, self.now)

        report = render_unreachable_deletion_candidates_report(candidates)

        self.assertIn("1件", report)
        self.assertIn("u1", report)
        self.assertIn("5日経過", report)
        self.assertIn("自動削除の対象ではありません", report)


if __name__ == "__main__":
    unittest.main()
