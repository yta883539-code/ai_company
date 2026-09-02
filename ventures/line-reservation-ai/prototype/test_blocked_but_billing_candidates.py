#!/usr/bin/env python3
"""blocked_but_billing_candidates.pyの単体テスト。
blocked-but-billing-detection-design.md(フェーズ続き176)の候補洗い出しロジックの仕様に
沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from blocked_but_billing_candidates import (  # noqa: E402
    list_blocked_but_billing_candidates,
)
from store_profile_store import InMemoryStoreProfileStore  # noqa: E402


def _set_store(store, store_id, *, owner_is_following=True, suspension_reason=None):
    store.set_owner_is_following(store_id, owner_is_following)
    store.set_suspension_reason(store_id, suspension_reason)


class ListBlockedButBillingCandidatesTest(unittest.TestCase):
    def test_returns_store_whose_owner_unfollowed_while_billing_normally(self):
        store = InMemoryStoreProfileStore()
        _set_store(store, "store-1", owner_is_following=False, suspension_reason=None)
        self.assertEqual(list_blocked_but_billing_candidates(store), ["store-1"])

    def test_excludes_a_store_whose_owner_is_still_following(self):
        store = InMemoryStoreProfileStore()
        _set_store(store, "store-1", owner_is_following=True, suspension_reason=None)
        self.assertEqual(list_blocked_but_billing_candidates(store), [])

    def test_excludes_an_unfollowed_store_whose_subscription_was_cancelled(self):
        # suspension_reason="cancelled"は契約自体が終了済み=もう課金されていないため除外する。
        store = InMemoryStoreProfileStore()
        _set_store(store, "store-1", owner_is_following=False, suspension_reason="cancelled")
        self.assertEqual(list_blocked_but_billing_candidates(store), [])

    def test_excludes_an_unfollowed_store_in_dormant_trial_unselected_mode(self):
        # design 2節: trial_unselected(有料転換前に休止した)はそもそも課金が発生していない
        # ため、aircon-pashaの「トライアル中も候補に含める」とは異なり除外する。
        store = InMemoryStoreProfileStore()
        _set_store(
            store, "store-1", owner_is_following=False, suspension_reason="trial_unselected"
        )
        self.assertEqual(list_blocked_but_billing_candidates(store), [])

    def test_includes_an_unfollowed_store_in_payment_failed_grace_period(self):
        store = InMemoryStoreProfileStore()
        _set_store(
            store, "store-1", owner_is_following=False, suspension_reason="payment_failed"
        )
        self.assertEqual(list_blocked_but_billing_candidates(store), ["store-1"])

    def test_includes_an_unfollowed_store_in_payment_suspended_restricted_mode(self):
        store = InMemoryStoreProfileStore()
        _set_store(
            store, "store-1", owner_is_following=False, suspension_reason="payment_suspended"
        )
        self.assertEqual(list_blocked_but_billing_candidates(store), ["store-1"])

    def test_returns_multiple_candidates_sorted_by_store_id(self):
        store = InMemoryStoreProfileStore()
        _set_store(store, "store-2", owner_is_following=False, suspension_reason=None)
        _set_store(store, "store-1", owner_is_following=False, suspension_reason="payment_failed")
        self.assertEqual(
            list_blocked_but_billing_candidates(store), ["store-1", "store-2"]
        )

    def test_ignores_stores_with_no_record_at_all(self):
        store = InMemoryStoreProfileStore()
        self.assertEqual(list_blocked_but_billing_candidates(store), [])


if __name__ == "__main__":
    unittest.main()
