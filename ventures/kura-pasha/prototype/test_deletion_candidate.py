#!/usr/bin/env python3
"""deletion_candidate.pyの単体テスト。
stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ232)の削除候補洗い出し
ロジックの仕様に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from deletion_candidate import (  # noqa: E402
    RETENTION_DAYS,
    clear_deletion_candidate_on_subscription_reactivated,
    list_deletion_candidates,
    mark_deletion_candidate_on_subscription_deleted,
)
from usage_counter_workshop import InMemoryWorkshopStore  # noqa: E402

_EVENT_TIME = datetime(2026, 10, 13, 12, 0, 0)


def _register_workshop(store: InMemoryWorkshopStore, workshop_id: str) -> None:
    store.set_members(workshop_id, f"{workshop_id}-contractor", [])


class MarkDeletionCandidateOnSubscriptionDeletedTest(unittest.TestCase):
    def test_sets_deletion_candidate_at_to_event_time_plus_retention_days(self):
        store = InMemoryWorkshopStore()
        result = mark_deletion_candidate_on_subscription_deleted(store, "W1", _EVENT_TIME)
        expected = _EVENT_TIME + timedelta(days=RETENTION_DAYS)
        self.assertEqual(result, expected)
        self.assertEqual(store.get_deletion_candidate_at("W1"), expected)

    def test_overwrites_an_existing_value_with_the_latest_cancellation(self):
        store = InMemoryWorkshopStore()
        mark_deletion_candidate_on_subscription_deleted(store, "W1", _EVENT_TIME)
        later_event_time = _EVENT_TIME + timedelta(days=10)
        result = mark_deletion_candidate_on_subscription_deleted(store, "W1", later_event_time)
        self.assertEqual(result, later_event_time + timedelta(days=RETENTION_DAYS))
        self.assertEqual(store.get_deletion_candidate_at("W1"), result)

    def test_does_not_affect_other_workshops(self):
        store = InMemoryWorkshopStore()
        mark_deletion_candidate_on_subscription_deleted(store, "W1", _EVENT_TIME)
        self.assertIsNone(store.get_deletion_candidate_at("W2"))


class ClearDeletionCandidateOnSubscriptionReactivatedTest(unittest.TestCase):
    def test_clears_an_existing_deletion_candidate_and_returns_true(self):
        store = InMemoryWorkshopStore()
        mark_deletion_candidate_on_subscription_deleted(store, "W1", _EVENT_TIME)
        cleared = clear_deletion_candidate_on_subscription_reactivated(store, "W1")
        self.assertTrue(cleared)
        self.assertIsNone(store.get_deletion_candidate_at("W1"))

    def test_is_idempotent_when_nothing_is_set(self):
        store = InMemoryWorkshopStore()
        cleared = clear_deletion_candidate_on_subscription_reactivated(store, "W1")
        self.assertFalse(cleared)
        self.assertIsNone(store.get_deletion_candidate_at("W1"))


class ListDeletionCandidatesTest(unittest.TestCase):
    def test_returns_workshops_whose_deletion_candidate_at_has_passed(self):
        store = InMemoryWorkshopStore()
        _register_workshop(store, "W1")
        _register_workshop(store, "W2")
        mark_deletion_candidate_on_subscription_deleted(store, "W1", _EVENT_TIME)
        now = _EVENT_TIME + timedelta(days=RETENTION_DAYS, seconds=1)
        self.assertEqual(list_deletion_candidates(store, now), ["W1"])

    def test_excludes_workshops_not_yet_due(self):
        store = InMemoryWorkshopStore()
        _register_workshop(store, "W1")
        mark_deletion_candidate_on_subscription_deleted(store, "W1", _EVENT_TIME)
        now = _EVENT_TIME + timedelta(days=RETENTION_DAYS - 1)
        self.assertEqual(list_deletion_candidates(store, now), [])

    def test_excludes_workshops_without_a_deletion_candidate_at(self):
        store = InMemoryWorkshopStore()
        _register_workshop(store, "W1")
        now = _EVENT_TIME + timedelta(days=RETENTION_DAYS + 1)
        self.assertEqual(list_deletion_candidates(store, now), [])


if __name__ == "__main__":
    unittest.main()
