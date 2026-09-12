#!/usr/bin/env python3
"""subscription_plan_sync.pyの単体テスト。
subscription-plan-sync-design.md(フェーズ93)のテスト観点に沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from subscription_plan_sync import (  # noqa: E402
    LOOKUP_KEY_TO_PLAN_ID,
    resolve_plan_id_from_subscription,
    sync_plan_on_subscription_event,
)
from usage_counter_workshop import InMemoryWorkshopStore  # noqa: E402

_WORKSHOP_ID = "W1"


class _CountingPlanStore:
    """`set_plan`の呼び出し回数を数える薄いラッパー(委譲先は`InMemoryWorkshopStore`)。
    差分チェックによる書き込み省略を検証するためだけに使う。"""

    def __init__(self, inner: InMemoryWorkshopStore) -> None:
        self._inner = inner
        self.set_call_count = 0

    def get_plan_id(self, workshop_id: str) -> str:
        return self._inner.get_plan_id(workshop_id)

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        self.set_call_count += 1
        self._inner.set_plan(workshop_id, plan_id)


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
        self.assertIsNone(resolve_plan_id_from_subscription({"items": {"data": []}}))

    def test_none_when_items_data_not_list(self):
        self.assertIsNone(
            resolve_plan_id_from_subscription({"items": {"data": "not-a-list"}})
        )

    def test_none_when_price_missing(self):
        self.assertIsNone(resolve_plan_id_from_subscription({"items": {"data": [{}]}}))

    def test_none_when_lookup_key_not_string(self):
        self.assertIsNone(
            resolve_plan_id_from_subscription(
                {"items": {"data": [{"price": {"lookup_key": None}}]}}
            )
        )


class SyncPlanOnSubscriptionEventTest(unittest.TestCase):
    def test_writes_resolved_plan_id_and_returns_it(self):
        store = InMemoryWorkshopStore()
        store.set_plan(_WORKSHOP_ID, "light")
        plan_id = sync_plan_on_subscription_event(
            store, _WORKSHOP_ID, _subscription_object("kura_pasha_standard")
        )
        self.assertEqual(plan_id, "standard")
        self.assertEqual(store.get_plan_id(_WORKSHOP_ID), "standard")

    def test_writes_even_when_plan_id_not_yet_set(self):
        store = InMemoryWorkshopStore()
        plan_id = sync_plan_on_subscription_event(
            store, _WORKSHOP_ID, _subscription_object("kura_pasha_light")
        )
        self.assertEqual(plan_id, "light")
        self.assertEqual(store.get_plan_id(_WORKSHOP_ID), "light")

    def test_overwrites_previous_plan_id_on_upgrade(self):
        store = InMemoryWorkshopStore()
        store.set_plan(_WORKSHOP_ID, "light")
        sync_plan_on_subscription_event(
            store, _WORKSHOP_ID, _subscription_object("kura_pasha_multi_craftsman")
        )
        self.assertEqual(store.get_plan_id(_WORKSHOP_ID), "multi_craftsman")

    def test_leaves_existing_plan_id_untouched_when_unresolvable(self):
        store = InMemoryWorkshopStore()
        store.set_plan(_WORKSHOP_ID, "standard")
        result = sync_plan_on_subscription_event(
            store, _WORKSHOP_ID, _subscription_object("unknown_price")
        )
        self.assertIsNone(result)
        self.assertEqual(store.get_plan_id(_WORKSHOP_ID), "standard")

    def test_unknown_workshop_id_still_resolves_and_writes(self):
        store = InMemoryWorkshopStore()
        result = sync_plan_on_subscription_event(
            store, "no-such-workshop", _subscription_object("kura_pasha_light")
        )
        self.assertEqual(result, "light")
        self.assertEqual(store.get_plan_id("no-such-workshop"), "light")

    def test_skips_write_when_resolved_plan_id_unchanged(self):
        store = _CountingPlanStore(InMemoryWorkshopStore())
        store.set_plan(_WORKSHOP_ID, "standard")
        self.assertEqual(store.set_call_count, 1)
        result = sync_plan_on_subscription_event(
            store, _WORKSHOP_ID, _subscription_object("kura_pasha_standard")
        )
        self.assertEqual(result, "standard")
        self.assertEqual(store.set_call_count, 1)  # 値が同じなので書き込まれない
        self.assertEqual(store.get_plan_id(_WORKSHOP_ID), "standard")

    def test_writes_again_when_resolved_plan_id_changes(self):
        store = _CountingPlanStore(InMemoryWorkshopStore())
        store.set_plan(_WORKSHOP_ID, "light")
        self.assertEqual(store.set_call_count, 1)
        sync_plan_on_subscription_event(
            store, _WORKSHOP_ID, _subscription_object("kura_pasha_standard")
        )
        self.assertEqual(store.set_call_count, 2)
        self.assertEqual(store.get_plan_id(_WORKSHOP_ID), "standard")


if __name__ == "__main__":
    unittest.main()
