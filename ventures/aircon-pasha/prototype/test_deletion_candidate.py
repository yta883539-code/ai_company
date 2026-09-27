#!/usr/bin/env python3
"""deletion_candidate.pyの単体テスト。
stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ123)の削除候補洗い出し
ロジックの仕様に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from deletion_candidate import (  # noqa: E402
    InMemoryProfileDeletionCandidateStore,
    clear_deletion_candidate_on_subscription_reactivated,
    list_deletion_candidates,
    mark_deletion_candidate_on_subscription_deleted,
)

_EVENT_TIME = datetime(2026, 8, 24, 12, 0, 0)


class MarkDeletionCandidateOnSubscriptionDeletedTest(unittest.TestCase):
    def test_sets_deletion_candidate_at_to_event_time_plus_365_days(self):
        store = InMemoryProfileDeletionCandidateStore()
        result = mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        expected = _EVENT_TIME + timedelta(days=365)
        self.assertEqual(result, expected)
        self.assertEqual(store.get_deletion_candidate_at("U1"), expected)

    def test_overwrites_an_existing_value_with_the_latest_cancellation(self):
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        later_event_time = _EVENT_TIME + timedelta(days=10)
        result = mark_deletion_candidate_on_subscription_deleted(store, "U1", later_event_time)
        self.assertEqual(result, later_event_time + timedelta(days=365))
        self.assertEqual(store.get_deletion_candidate_at("U1"), result)

    def test_does_not_affect_other_users(self):
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        self.assertIsNone(store.get_deletion_candidate_at("U2"))


class ClearDeletionCandidateOnSubscriptionReactivatedTest(unittest.TestCase):
    def test_clears_an_existing_deletion_candidate_and_returns_true(self):
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        cleared = clear_deletion_candidate_on_subscription_reactivated(store, "U1")
        self.assertTrue(cleared)
        self.assertIsNone(store.get_deletion_candidate_at("U1"))

    def test_is_idempotent_when_nothing_is_set(self):
        store = InMemoryProfileDeletionCandidateStore()
        cleared = clear_deletion_candidate_on_subscription_reactivated(store, "U1")
        self.assertFalse(cleared)
        self.assertIsNone(store.get_deletion_candidate_at("U1"))

    def test_first_time_subscription_created_is_a_harmless_no_op(self):
        # design 5節: 「初回契約」でも`customer.subscription.created`は発火しうるが、
        # deletion_candidate_atが最初から未設定なら実害はない。
        store = InMemoryProfileDeletionCandidateStore()
        cleared = clear_deletion_candidate_on_subscription_reactivated(store, "new-user")
        self.assertFalse(cleared)


class ListDeletionCandidatesTest(unittest.TestCase):
    def test_returns_user_ids_whose_deletion_candidate_at_has_passed(self):
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        now = _EVENT_TIME + timedelta(days=366)
        self.assertEqual(list_deletion_candidates(store, now), ["U1"])

    def test_excludes_user_ids_whose_deletion_candidate_at_is_still_in_the_future(self):
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        now = _EVENT_TIME + timedelta(days=1)
        self.assertEqual(list_deletion_candidates(store, now), [])

    def test_includes_a_candidate_at_exactly_now(self):
        store = InMemoryProfileDeletionCandidateStore()
        deletion_candidate_at = mark_deletion_candidate_on_subscription_deleted(
            store, "U1", _EVENT_TIME
        )
        self.assertEqual(list_deletion_candidates(store, deletion_candidate_at), ["U1"])

    def test_excludes_users_without_any_deletion_candidate_at(self):
        store = InMemoryProfileDeletionCandidateStore()
        store.set_deletion_candidate_at("U1", None)
        self.assertEqual(list_deletion_candidates(store, _EVENT_TIME), [])

    def test_returns_multiple_candidates_sorted_by_user_id(self):
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U2", _EVENT_TIME)
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        now = _EVENT_TIME + timedelta(days=366)
        self.assertEqual(list_deletion_candidates(store, now), ["U1", "U2"])

    def test_does_not_call_reactivation_a_deletion(self):
        # markしてからclearした場合はlist_deletion_candidatesに含まれないこと
        # (list側が誤って過去のmark結果をキャッシュしていないことの確認)。
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        clear_deletion_candidate_on_subscription_reactivated(store, "U1")
        now = _EVENT_TIME + timedelta(days=366)
        self.assertEqual(list_deletion_candidates(store, now), [])


class StaleEventGuardTest(unittest.TestCase):
    """subscription-event-out-of-order-guard-design.md(本フェーズ、course-set-pasha
    フェーズ262の横展開): Stripe Webhookの配信順序入れ替わり(解約→即再契約でdeletedが
    createdより後に届く、初回createdのリトライが後続deletedより後に届く)に対する
    ガードの確認。"""

    def test_case_a_stale_deleted_after_newer_created_does_not_mark(self):
        # 解約(T1)→即再契約(T2>T1)で、createdが先に反映済みの状態に、遅れてT1のdeletedが届く。
        store = InMemoryProfileDeletionCandidateStore()
        newer_created_time = _EVENT_TIME + timedelta(days=1)
        clear_deletion_candidate_on_subscription_reactivated(store, "U1", newer_created_time)
        result = mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        self.assertIsNone(result)
        self.assertIsNone(store.get_deletion_candidate_at("U1"))

    def test_case_b_stale_created_after_newer_deleted_does_not_clear(self):
        # 初回contract(T1)のリトライが、後続の解約(T2>T1)より後に届く。
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        newer_deleted_time = _EVENT_TIME + timedelta(days=1)
        mark_deletion_candidate_on_subscription_deleted(store, "U1", newer_deleted_time)
        stale_created_time = _EVENT_TIME  # newer_deleted_timeより古い
        cleared = clear_deletion_candidate_on_subscription_reactivated(
            store, "U1", stale_created_time
        )
        self.assertFalse(cleared)
        self.assertEqual(
            store.get_deletion_candidate_at("U1"),
            newer_deleted_time + timedelta(days=365),
        )

    def test_normal_order_deleted_then_created_still_applies(self):
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        later = _EVENT_TIME + timedelta(days=1)
        cleared = clear_deletion_candidate_on_subscription_reactivated(store, "U1", later)
        self.assertTrue(cleared)
        self.assertIsNone(store.get_deletion_candidate_at("U1"))

    def test_event_time_omitted_on_clear_skips_guard_for_backward_compatibility(self):
        # event_timeを渡さない従来通りの呼び出しは、より新しい反映済みイベントがあっても
        # 無条件にクリアする(既存呼び出し経路・テストとの後方互換)。
        store = InMemoryProfileDeletionCandidateStore()
        mark_deletion_candidate_on_subscription_deleted(store, "U1", _EVENT_TIME)
        newer_deleted_time = _EVENT_TIME + timedelta(days=1)
        mark_deletion_candidate_on_subscription_deleted(store, "U1", newer_deleted_time)
        cleared = clear_deletion_candidate_on_subscription_reactivated(store, "U1")
        self.assertTrue(cleared)
        self.assertIsNone(store.get_deletion_candidate_at("U1"))


if __name__ == "__main__":
    unittest.main()
