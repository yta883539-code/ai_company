#!/usr/bin/env python3
"""blocked_but_billing_candidates.pyの単体テスト。
blocked-but-billing-detection-design.md(フェーズ167)の候補洗い出しロジックの仕様に
沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from blocked_but_billing_candidates import (  # noqa: E402
    list_blocked_but_billing_candidates,
)
from user_id_linking import InMemoryUserProfileStore, UserProfile  # noqa: E402

_LINKED_AT = datetime(2026, 8, 24, 12, 0, 0)


def _save_profile(store, user_id, *, is_following=True, current_plan_id=None):
    store.save(
        user_id,
        UserProfile(
            business_name="テスト業者",
            business_type="エアコンクリーニング",
            email="owner@example.com",
            linked_at=_LINKED_AT,
            current_plan_id=current_plan_id,
            is_following=is_following,
        ),
    )


class ListBlockedButBillingCandidatesTest(unittest.TestCase):
    def test_returns_user_unfollowed_while_still_on_a_plan(self):
        store = InMemoryUserProfileStore()
        _save_profile(store, "U1", is_following=False, current_plan_id="スタンダード")
        self.assertEqual(list_blocked_but_billing_candidates(store), ["U1"])

    def test_excludes_a_user_who_is_still_following(self):
        store = InMemoryUserProfileStore()
        _save_profile(store, "U1", is_following=True, current_plan_id="スタンダード")
        self.assertEqual(list_blocked_but_billing_candidates(store), [])

    def test_excludes_an_unfollowed_user_whose_subscription_was_cancelled(self):
        # current_plan_idはsubscription.deleted受信時にNoneへ戻る(フェーズ161配線)ため、
        # 解約済みでunfollowしている業者は「もう課金されていない」ので候補から除外する。
        store = InMemoryUserProfileStore()
        _save_profile(store, "U1", is_following=False, current_plan_id=None)
        self.assertEqual(list_blocked_but_billing_candidates(store), [])

    def test_excludes_an_unfollowed_user_who_is_still_only_trialing(self):
        # design 2節: current_plan_idはトライアル中でも設定されうる想定のため、
        # トライアル中にブロックした業者も候補に含める(まだ無料期間内でも、放置すれば
        # 自動的に有料転換し課金が発生しうるため早期に検知する意図)。
        store = InMemoryUserProfileStore()
        _save_profile(store, "U1", is_following=False, current_plan_id="スモール")
        self.assertEqual(list_blocked_but_billing_candidates(store), ["U1"])

    def test_returns_multiple_candidates_sorted_by_user_id(self):
        store = InMemoryUserProfileStore()
        _save_profile(store, "U2", is_following=False, current_plan_id="繁忙期対応")
        _save_profile(store, "U1", is_following=False, current_plan_id="スタンダード")
        self.assertEqual(list_blocked_but_billing_candidates(store), ["U1", "U2"])

    def test_ignores_users_with_no_profile_at_all(self):
        store = InMemoryUserProfileStore()
        self.assertEqual(list_blocked_but_billing_candidates(store), [])


if __name__ == "__main__":
    unittest.main()
