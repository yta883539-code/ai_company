#!/usr/bin/env python3
"""store_profile_store.pyの単体テスト。
checkout-initiation-flow-design.md 3節の「既存customerの再利用」判定に必要な
読み書きロジックを検証する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from store_profile_store import (  # noqa: E402
    InMemoryStoreProfileStore,
    resolve_existing_stripe_customer_id,
)


class InMemoryStoreProfileStoreTest(unittest.TestCase):
    def test_get_returns_none_when_unset(self):
        store = InMemoryStoreProfileStore()
        self.assertIsNone(store.get_stripe_customer_id("Uowner123"))

    def test_set_then_get_roundtrip(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        self.assertEqual(store.get_stripe_customer_id("Uowner123"), "cus_abc")

    def test_set_raises_on_empty_user_id(self):
        store = InMemoryStoreProfileStore()
        with self.assertRaises(ValueError):
            store.set_stripe_customer_id("", "cus_abc")

    def test_set_raises_on_empty_stripe_customer_id(self):
        store = InMemoryStoreProfileStore()
        with self.assertRaises(ValueError):
            store.set_stripe_customer_id("Uowner123", "")

    def test_different_users_are_isolated(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        self.assertIsNone(store.get_stripe_customer_id("Uowner999"))


class ResolveExistingStripeCustomerIdTest(unittest.TestCase):
    def test_returns_none_when_not_yet_linked(self):
        store = InMemoryStoreProfileStore()
        self.assertIsNone(resolve_existing_stripe_customer_id("Uowner123", store))

    def test_returns_existing_customer_id(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        self.assertEqual(
            resolve_existing_stripe_customer_id("Uowner123", store), "cus_abc"
        )

    def test_raises_on_empty_user_id(self):
        store = InMemoryStoreProfileStore()
        with self.assertRaises(ValueError):
            resolve_existing_stripe_customer_id("", store)


if __name__ == "__main__":
    unittest.main()
