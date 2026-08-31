#!/usr/bin/env python3
"""subscription_plan_sync.pyの単体テスト。
user-account-linking-design.md 4節・subscription-cancellation-flow-design.md
「当月生成回数上限の適用方法」節のテスト観点に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from subscription_plan_sync import (  # noqa: E402
    LOOKUP_KEY_TO_PLAN_ID,
    clear_current_plan_on_subscription_deleted,
    resolve_plan_id_from_subscription,
    sync_current_plan_on_subscription_event,
)
from user_id_linking import InMemoryUserProfileStore, UserProfile  # noqa: E402

_USER_ID = "U1"


def _profile_store_with_user() -> InMemoryUserProfileStore:
    store = InMemoryUserProfileStore()
    store.save(
        _USER_ID,
        UserProfile(
            business_name="テスト洗浄社",
            business_type="独立系",
            email="test@example.com",
            linked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        ),
    )
    return store


def _subscription_object(lookup_key) -> dict:
    return {
        "customer": "cus_ABC123",
        "items": {"data": [{"price": {"lookup_key": lookup_key}}]},
    }


class ResolvePlanIdFromSubscriptionTest(unittest.TestCase):
    def test_resolves_each_known_lookup_key(self):
        for lookup_key, plan_id in LOOKUP_KEY_TO_PLAN_ID.items():
            with self.subTest(lookup_key=lookup_key):
                self.assertEqual(
                    resolve_plan_id_from_subscription(_subscription_object(lookup_key)),
                    plan_id,
                )

    def test_none_when_lookup_key_unknown(self):
        self.assertIsNone(
            resolve_plan_id_from_subscription(_subscription_object("some_other_price"))
        )

    def test_none_when_items_missing(self):
        self.assertIsNone(resolve_plan_id_from_subscription({"customer": "cus_ABC123"}))

    def test_none_when_items_data_empty(self):
        self.assertIsNone(
            resolve_plan_id_from_subscription({"items": {"data": []}})
        )

    def test_none_when_items_data_not_list(self):
        self.assertIsNone(
            resolve_plan_id_from_subscription({"items": {"data": "not-a-list"}})
        )

    def test_none_when_price_missing(self):
        self.assertIsNone(
            resolve_plan_id_from_subscription({"items": {"data": [{}]}})
        )

    def test_none_when_lookup_key_not_string(self):
        self.assertIsNone(
            resolve_plan_id_from_subscription(
                {"items": {"data": [{"price": {"lookup_key": None}}]}}
            )
        )


class SyncCurrentPlanOnSubscriptionEventTest(unittest.TestCase):
    def test_writes_resolved_plan_id_and_returns_it(self):
        store = _profile_store_with_user()
        plan_id = sync_current_plan_on_subscription_event(
            store, _USER_ID, _subscription_object("aircon_pasha_standard")
        )
        self.assertEqual(plan_id, "スタンダード")
        self.assertEqual(store.get_current_plan_id(_USER_ID), "スタンダード")

    def test_overwrites_previous_plan_id_on_upgrade(self):
        store = _profile_store_with_user()
        sync_current_plan_on_subscription_event(
            store, _USER_ID, _subscription_object("aircon_pasha_small")
        )
        sync_current_plan_on_subscription_event(
            store, _USER_ID, _subscription_object("aircon_pasha_busy")
        )
        self.assertEqual(store.get_current_plan_id(_USER_ID), "繁忙期対応")

    def test_leaves_existing_plan_id_untouched_when_unresolvable(self):
        store = _profile_store_with_user()
        sync_current_plan_on_subscription_event(
            store, _USER_ID, _subscription_object("aircon_pasha_small")
        )
        result = sync_current_plan_on_subscription_event(
            store, _USER_ID, _subscription_object("unknown_price")
        )
        self.assertIsNone(result)
        self.assertEqual(store.get_current_plan_id(_USER_ID), "スモール")

    def test_unknown_user_id_is_a_no_op(self):
        store = InMemoryUserProfileStore()
        result = sync_current_plan_on_subscription_event(
            store, "no-such-user", _subscription_object("aircon_pasha_small")
        )
        self.assertEqual(result, "スモール")  # 解決自体は行うがstore書き込みはno-op
        self.assertIsNone(store.get_current_plan_id("no-such-user"))


class ClearCurrentPlanOnSubscriptionDeletedTest(unittest.TestCase):
    def test_resets_plan_id_to_none(self):
        store = _profile_store_with_user()
        sync_current_plan_on_subscription_event(
            store, _USER_ID, _subscription_object("aircon_pasha_standard")
        )
        clear_current_plan_on_subscription_deleted(store, _USER_ID)
        self.assertIsNone(store.get_current_plan_id(_USER_ID))

    def test_idempotent_when_already_none(self):
        store = _profile_store_with_user()
        clear_current_plan_on_subscription_deleted(store, _USER_ID)
        self.assertIsNone(store.get_current_plan_id(_USER_ID))


if __name__ == "__main__":
    unittest.main()
