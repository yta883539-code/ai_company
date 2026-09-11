#!/usr/bin/env python3
"""blocked_but_billing_candidates.pyの単体テスト。
blocked-but-billing-detection-design.md(フェーズ80)の候補洗い出しロジックの仕様に
沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from blocked_but_billing_candidates import (  # noqa: E402
    list_blocked_but_billing_candidates,
)
from usage_counter_workshop import (  # noqa: E402
    InMemoryUserProfileStore,
    InMemoryWorkshopStore,
)


def _make_workshop(workshop_store, workshop_id, *, contractor_user_id, subscription_status):
    workshop_store.set_members(
        workshop_id, contractor_user_id=contractor_user_id, member_user_ids=[contractor_user_id]
    )
    workshop_store.set_plan(workshop_id, "light")
    workshop_store.set_subscription_status(workshop_id, subscription_status)


class ListBlockedButBillingCandidatesTest(unittest.TestCase):
    def test_returns_workshop_whose_contractor_unfollowed_while_still_billed(self):
        workshop_store = InMemoryWorkshopStore()
        profile_store = InMemoryUserProfileStore()
        _make_workshop(workshop_store, "W1", contractor_user_id="U1", subscription_status="active")
        profile_store.set_is_following("U1", False)

        self.assertEqual(
            list_blocked_but_billing_candidates(workshop_store, profile_store), ["W1"]
        )

    def test_excludes_workshop_whose_contractor_is_still_following(self):
        workshop_store = InMemoryWorkshopStore()
        profile_store = InMemoryUserProfileStore()
        _make_workshop(workshop_store, "W1", contractor_user_id="U1", subscription_status="active")
        # is_followingを明示的に設定しない = 既定値True(フォロー中)のまま。

        self.assertEqual(list_blocked_but_billing_candidates(workshop_store, profile_store), [])

    def test_excludes_an_unfollowed_contractor_whose_workshop_was_canceled(self):
        # subscription_statusはcustomer.subscription.deleted受信時に"canceled"へ更新される
        # (stripe_webhook.handle_customer_subscription_deleted())。plan_idは解約後も
        # workshop作成時の値のまま残るため判定に使えない一方、subscription_statusで
        # 「もう課金されていない」workshopを安全に除外できる。
        workshop_store = InMemoryWorkshopStore()
        profile_store = InMemoryUserProfileStore()
        _make_workshop(workshop_store, "W1", contractor_user_id="U1", subscription_status="canceled")
        profile_store.set_is_following("U1", False)

        self.assertEqual(list_blocked_but_billing_candidates(workshop_store, profile_store), [])

    def test_includes_an_unfollowed_contractor_still_trialing(self):
        # design 1節: トライアル中(有料転換前)にブロックした契約者も候補に含める
        # (放置すればトライアル終了通知が届かないまま自動的に有料転換しうるため)。
        workshop_store = InMemoryWorkshopStore()
        profile_store = InMemoryUserProfileStore()
        _make_workshop(workshop_store, "W1", contractor_user_id="U1", subscription_status="trialing")
        profile_store.set_is_following("U1", False)

        self.assertEqual(
            list_blocked_but_billing_candidates(workshop_store, profile_store), ["W1"]
        )

    def test_ignores_a_blocked_non_contractor_member(self):
        # design 1節: 通知対象は常に契約者本人のため、契約者以外のメンバーが
        # ブロックしていても本検知の対象外とする(billingの通知先ではないため)。
        workshop_store = InMemoryWorkshopStore()
        profile_store = InMemoryUserProfileStore()
        workshop_store.set_members(
            "W1", contractor_user_id="U1", member_user_ids=["U1", "U2"]
        )
        workshop_store.set_plan("W1", "multi")
        workshop_store.set_subscription_status("W1", "active")
        profile_store.set_is_following("U2", False)

        self.assertEqual(list_blocked_but_billing_candidates(workshop_store, profile_store), [])

    def test_returns_multiple_candidates_sorted_by_workshop_id(self):
        workshop_store = InMemoryWorkshopStore()
        profile_store = InMemoryUserProfileStore()
        _make_workshop(workshop_store, "W2", contractor_user_id="U2", subscription_status="active")
        _make_workshop(workshop_store, "W1", contractor_user_id="U1", subscription_status="active")
        profile_store.set_is_following("U1", False)
        profile_store.set_is_following("U2", False)

        self.assertEqual(
            list_blocked_but_billing_candidates(workshop_store, profile_store), ["W1", "W2"]
        )

    def test_ignores_workshops_with_no_contractor_unfollowed(self):
        workshop_store = InMemoryWorkshopStore()
        profile_store = InMemoryUserProfileStore()
        self.assertEqual(list_blocked_but_billing_candidates(workshop_store, profile_store), [])


if __name__ == "__main__":
    unittest.main()
