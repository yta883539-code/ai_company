#!/usr/bin/env python3
"""blocked_but_billing_candidates.pyの単体テスト。
blocked-but-billing-detection-design.md(フェーズ142)の候補洗い出しロジックの仕様に
沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from blocked_but_billing_candidates import (  # noqa: E402
    list_blocked_but_billing_candidates,
)
from application_form_submission_flow import InMemoryUserProfileStore  # noqa: E402
from deletion_candidate import InMemoryProfileDeletionCandidateStore  # noqa: E402

_DELETION_MARKED_AT = datetime(2026, 9, 1, 0, 0, 0)


class ListBlockedButBillingCandidatesTest(unittest.TestCase):
    def _stores(self):
        return InMemoryUserProfileStore(), InMemoryProfileDeletionCandidateStore()

    def test_returns_user_unfollowed_while_stripe_customer_not_cancelled(self):
        profile_store, deletion_store = self._stores()
        profile_store.set_stripe_customer_id("U1", "cus_A")
        profile_store.set_is_following("U1", False)

        self.assertEqual(
            list_blocked_but_billing_candidates(profile_store, deletion_store), ["U1"]
        )

    def test_excludes_a_user_who_is_still_following(self):
        profile_store, deletion_store = self._stores()
        profile_store.set_stripe_customer_id("U1", "cus_A")
        # follow直後(is_following未設定)はデフォルトTrue扱いのため候補から除外される。

        self.assertEqual(
            list_blocked_but_billing_candidates(profile_store, deletion_store), []
        )

    def test_excludes_a_user_who_never_completed_checkout(self):
        # stripe_customer_id未設定(=Checkout未完了、トライアル中含む)は候補外(design 2節)。
        profile_store, deletion_store = self._stores()
        profile_store.set_is_following("U1", False)

        self.assertEqual(
            list_blocked_but_billing_candidates(profile_store, deletion_store), []
        )

    def test_excludes_an_unfollowed_user_whose_subscription_was_already_cancelled(self):
        # deletion_candidate_atはcustomer.subscription.deleted受信時に設定される
        # (=解約が確認済み)ため、これ以上「解約案内」を送る必要はない。
        profile_store, deletion_store = self._stores()
        profile_store.set_stripe_customer_id("U1", "cus_A")
        profile_store.set_is_following("U1", False)
        deletion_store.set_deletion_candidate_at("U1", _DELETION_MARKED_AT)

        self.assertEqual(
            list_blocked_but_billing_candidates(profile_store, deletion_store), []
        )

    def test_returns_multiple_candidates_sorted_by_user_id(self):
        profile_store, deletion_store = self._stores()
        for user_id in ("U2", "U1"):
            profile_store.set_stripe_customer_id(user_id, f"cus_{user_id}")
            profile_store.set_is_following(user_id, False)

        self.assertEqual(
            list_blocked_but_billing_candidates(profile_store, deletion_store),
            ["U1", "U2"],
        )

    def test_ignores_users_with_no_profile_at_all(self):
        profile_store, deletion_store = self._stores()
        self.assertEqual(
            list_blocked_but_billing_candidates(profile_store, deletion_store), []
        )


if __name__ == "__main__":
    unittest.main()
