#!/usr/bin/env python3
"""store_deletion_candidate.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_store_deletion_candidate -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from store_deletion_candidate import (
    DELETION_CANDIDATE_DELAY,
    StoreDeletionCandidateState,
    is_store_deletion_candidate,
    list_store_deletion_candidates,
    list_unreachable_store_deletion_candidates,
    render_store_deletion_final_confirmation_message,
    render_unreachable_store_deletion_candidates_report,
)

FINAL_SENT_AT = datetime(2026, 8, 20, 10, 0)
DUE_AT = FINAL_SENT_AT + DELETION_CANDIDATE_DELAY


def _state(**overrides) -> StoreDeletionCandidateState:
    defaults = dict(
        store_id="store-1",
        dormant_renotify_count=3,
        dormant_final_renotify_sent_at=FINAL_SENT_AT,
        suspension_reason="trial_unselected",
        stripe_customer_id=None,
        store_deletion_confirmation_sent_at=None,
    )
    defaults.update(overrides)
    return StoreDeletionCandidateState(**defaults)


class IsStoreDeletionCandidateTests(unittest.TestCase):
    def test_all_conditions_met_is_candidate(self):
        self.assertTrue(is_store_deletion_candidate(_state(), DUE_AT))

    def test_before_365_days_not_candidate(self):
        self.assertFalse(
            is_store_deletion_candidate(_state(), DUE_AT - timedelta(days=1))
        )

    def test_renotify_count_below_3_not_candidate(self):
        self.assertFalse(
            is_store_deletion_candidate(_state(dormant_renotify_count=2), DUE_AT)
        )

    def test_final_not_sent_not_candidate(self):
        self.assertFalse(
            is_store_deletion_candidate(
                _state(dormant_final_renotify_sent_at=None), DUE_AT
            )
        )

    def test_already_confirmed_not_candidate(self):
        self.assertFalse(
            is_store_deletion_candidate(
                _state(store_deletion_confirmation_sent_at=FINAL_SENT_AT), DUE_AT
            )
        )

    def test_reactivated_via_stripe_customer_id_not_candidate(self):
        self.assertFalse(
            is_store_deletion_candidate(
                _state(stripe_customer_id="cus_123"), DUE_AT
            )
        )

    def test_reactivated_via_suspension_reason_cleared_not_candidate(self):
        self.assertFalse(
            is_store_deletion_candidate(_state(suspension_reason=None), DUE_AT)
        )


class ListStoreDeletionCandidatesTests(unittest.TestCase):
    def test_returns_only_matching_store_ids_sorted(self):
        states = [
            _state(store_id="store-b"),
            _state(store_id="store-a"),
            _state(store_id="store-c", dormant_renotify_count=1),  # 対象外
        ]
        self.assertEqual(
            list_store_deletion_candidates(states, DUE_AT), ["store-a", "store-b"]
        )

    def test_empty_when_none_due(self):
        states = [_state(dormant_final_renotify_sent_at=None)]
        self.assertEqual(list_store_deletion_candidates(states, DUE_AT), [])


class RenderMessageTests(unittest.TestCase):
    def test_message_does_not_mention_specific_deletion_date(self):
        message = render_store_deletion_final_confirmation_message()
        self.assertIn("データ保有", message)
        self.assertNotIn("削除予定日", message)


class ListUnreachableStoreDeletionCandidatesTests(unittest.TestCase):
    def test_returns_only_unreachable_stores_sorted_with_days_elapsed(self):
        unreachable_at = DUE_AT - timedelta(days=10)
        states = [
            _state(store_id="store-b", store_deletion_confirmation_unreachable_at=unreachable_at),
            _state(store_id="store-a", store_deletion_confirmation_unreachable_at=unreachable_at),
            _state(store_id="store-c", store_deletion_confirmation_unreachable_at=None),
        ]
        result = list_unreachable_store_deletion_candidates(states, DUE_AT)
        self.assertEqual([c.store_id for c in result], ["store-a", "store-b"])
        self.assertEqual(result[0].days_since_unreachable, 10)

    def test_empty_when_none_unreachable(self):
        states = [_state(store_deletion_confirmation_unreachable_at=None)]
        self.assertEqual(list_unreachable_store_deletion_candidates(states, DUE_AT), [])


class RenderUnreachableStoreDeletionCandidatesReportTests(unittest.TestCase):
    def test_empty_report_when_no_candidates(self):
        self.assertEqual(
            render_unreachable_store_deletion_candidates_report([]),
            "連絡不能の削除候補店舗はありません。",
        )

    def test_report_lists_store_id_and_days_elapsed_and_warns_against_auto_deletion(self):
        candidates = list_unreachable_store_deletion_candidates(
            [_state(store_id="store-a", store_deletion_confirmation_unreachable_at=DUE_AT - timedelta(days=5))],
            DUE_AT,
        )
        report = render_unreachable_store_deletion_candidates_report(candidates)
        self.assertIn("store-a", report)
        self.assertIn("5日経過", report)
        self.assertIn("自動削除の対象ではありません", report)


if __name__ == "__main__":
    unittest.main()
