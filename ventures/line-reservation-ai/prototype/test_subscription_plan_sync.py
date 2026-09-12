#!/usr/bin/env python3
"""subscription_plan_sync.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_subscription_plan_sync -v で実行可能。
"""

from __future__ import annotations

import unittest

from store_profile_store import InMemoryStoreProfileStore
from subscription_plan_sync import (
    LOOKUP_KEY_TO_PLAN,
    resolve_plan_from_subscription,
    sync_plan_on_subscription_event,
)


def _data_object_with_lookup_key(lookup_key) -> dict:
    return {"items": {"data": [{"price": {"lookup_key": lookup_key}}]}}


class ResolvePlanFromSubscriptionTest(unittest.TestCase):
    def test_resolves_each_known_lookup_key(self):
        for lookup_key, plan in LOOKUP_KEY_TO_PLAN.items():
            with self.subTest(lookup_key=lookup_key):
                self.assertEqual(
                    resolve_plan_from_subscription(_data_object_with_lookup_key(lookup_key)),
                    plan,
                )

    def test_unknown_lookup_key_returns_none(self):
        self.assertIsNone(
            resolve_plan_from_subscription(_data_object_with_lookup_key("unknown_key"))
        )

    def test_missing_items_returns_none(self):
        self.assertIsNone(resolve_plan_from_subscription({}))

    def test_items_not_dict_returns_none(self):
        self.assertIsNone(resolve_plan_from_subscription({"items": ["not", "a", "dict"]}))

    def test_missing_data_list_returns_none(self):
        self.assertIsNone(resolve_plan_from_subscription({"items": {}}))

    def test_data_not_list_returns_none(self):
        self.assertIsNone(resolve_plan_from_subscription({"items": {"data": {}}}))

    def test_empty_data_list_returns_none(self):
        self.assertIsNone(resolve_plan_from_subscription({"items": {"data": []}}))

    def test_first_item_not_dict_returns_none(self):
        self.assertIsNone(resolve_plan_from_subscription({"items": {"data": ["not-a-dict"]}}))

    def test_missing_price_returns_none(self):
        self.assertIsNone(resolve_plan_from_subscription({"items": {"data": [{}]}}))

    def test_price_not_dict_returns_none(self):
        self.assertIsNone(
            resolve_plan_from_subscription({"items": {"data": [{"price": "not-a-dict"}]}})
        )

    def test_missing_lookup_key_returns_none(self):
        self.assertIsNone(
            resolve_plan_from_subscription({"items": {"data": [{"price": {}}]}})
        )

    def test_lookup_key_not_string_returns_none(self):
        self.assertIsNone(
            resolve_plan_from_subscription(_data_object_with_lookup_key(12345))
        )


class SyncPlanOnSubscriptionEventTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryStoreProfileStore()

    def test_writes_plan_when_resolved_and_different_from_existing(self):
        result = sync_plan_on_subscription_event(
            self.store,
            "store-1",
            _data_object_with_lookup_key("line_reservation_ai_pro"),
        )
        self.assertEqual(result, "プロプラン")
        self.assertEqual(self.store.get_plan("store-1"), "プロプラン")

    def test_does_not_write_when_resolved_plan_matches_existing(self):
        self.store.set_plan("store-1", "スタンダードプラン")

        class _CountingPlanStore:
            def __init__(self, inner):
                self._inner = inner
                self.set_plan_calls = 0

            def get_plan(self, store_id):
                return self._inner.get_plan(store_id)

            def set_plan(self, store_id, plan):
                self.set_plan_calls += 1
                self._inner.set_plan(store_id, plan)

        counting_store = _CountingPlanStore(self.store)
        result = sync_plan_on_subscription_event(
            counting_store,
            "store-1",
            _data_object_with_lookup_key("line_reservation_ai_standard"),
        )

        self.assertEqual(result, "スタンダードプラン")
        self.assertEqual(counting_store.set_plan_calls, 0)

    def test_writes_again_when_plan_actually_changes(self):
        self.store.set_plan("store-1", "スタータープラン")

        result = sync_plan_on_subscription_event(
            self.store,
            "store-1",
            _data_object_with_lookup_key("line_reservation_ai_pro"),
        )

        self.assertEqual(result, "プロプラン")
        self.assertEqual(self.store.get_plan("store-1"), "プロプラン")

    def test_unresolvable_event_leaves_existing_plan_untouched(self):
        self.store.set_plan("store-1", "スタンダードプラン")

        result = sync_plan_on_subscription_event(self.store, "store-1", {})

        self.assertIsNone(result)
        self.assertEqual(self.store.get_plan("store-1"), "スタンダードプラン")

    def test_unresolvable_event_on_unset_store_stays_none(self):
        result = sync_plan_on_subscription_event(self.store, "store-1", {})

        self.assertIsNone(result)
        self.assertIsNone(self.store.get_plan("store-1"))


if __name__ == "__main__":
    unittest.main()
