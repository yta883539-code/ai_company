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
    handle_checkout_session_completed,
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


class HandleCheckoutSessionCompletedTest(unittest.TestCase):
    """checkout-initiation-flow-design.md 残課題。"""

    def setUp(self):
        self.store = InMemoryStoreProfileStore()

    def test_valid_event_links_customer_id_to_user_id(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "Uowner123", "customer": "cus_abc"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertTrue(result.linked)
        self.assertEqual(result.user_id, "Uowner123")
        self.assertEqual(result.stripe_customer_id, "cus_abc")
        self.assertEqual(self.store.get_stripe_customer_id("Uowner123"), "cus_abc")

    def test_missing_client_reference_id_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_abc"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)
        self.assertIsNone(self.store.get_stripe_customer_id("Uowner123"))

    def test_missing_customer_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "Uowner123"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)

    def test_empty_string_client_reference_id_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "", "customer": "cus_abc"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)

    def test_empty_string_customer_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "Uowner123", "customer": ""}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)

    def test_non_string_customer_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "Uowner123", "customer": None}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)

    def test_missing_data_object_does_not_link(self):
        event = {"type": "checkout.session.completed"}
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)

    def test_replay_of_same_event_is_idempotent(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "Uowner123", "customer": "cus_abc"}},
        }
        handle_checkout_session_completed(event, self.store)
        second = handle_checkout_session_completed(event, self.store)
        self.assertTrue(second.linked)
        self.assertEqual(self.store.get_stripe_customer_id("Uowner123"), "cus_abc")


if __name__ == "__main__":
    unittest.main()
