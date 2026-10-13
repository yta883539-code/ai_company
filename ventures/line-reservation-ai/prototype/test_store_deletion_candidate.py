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
    render_store_deletion_final_confirmation_message,
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


if __name__ == "__main__":
    unittest.main()
