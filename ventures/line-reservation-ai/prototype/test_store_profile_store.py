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
    evaluate_onboarding_completion_message_dispatch,
    handle_checkout_session_completed,
    make_resolve_store_id_by_customer,
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


class GetStoreIdByStripeCustomerIdTest(unittest.TestCase):
    """stripe-webhook-event-dispatch-design.md 5節・
    stripe-customer-id-reverse-lookup-design.mdの逆引き。"""

    def test_returns_none_when_unset(self):
        store = InMemoryStoreProfileStore()
        self.assertIsNone(store.get_store_id_by_stripe_customer_id("cus_abc"))

    def test_reverse_lookup_after_forward_set(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        self.assertEqual(
            store.get_store_id_by_stripe_customer_id("cus_abc"), "Uowner123"
        )

    def test_replaying_same_link_is_idempotent(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        self.assertEqual(
            store.get_store_id_by_stripe_customer_id("cus_abc"), "Uowner123"
        )

    def test_relinking_user_to_new_customer_id_drops_stale_reverse_entry(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_old")
        store.set_stripe_customer_id("Uowner123", "cus_new")
        self.assertIsNone(store.get_store_id_by_stripe_customer_id("cus_old"))
        self.assertEqual(
            store.get_store_id_by_stripe_customer_id("cus_new"), "Uowner123"
        )
        self.assertEqual(store.get_stripe_customer_id("Uowner123"), "cus_new")

    def test_different_customers_are_isolated(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        store.set_stripe_customer_id("Uowner999", "cus_xyz")
        self.assertEqual(
            store.get_store_id_by_stripe_customer_id("cus_abc"), "Uowner123"
        )
        self.assertEqual(
            store.get_store_id_by_stripe_customer_id("cus_xyz"), "Uowner999"
        )


class MakeResolveStoreIdByCustomerTest(unittest.TestCase):
    def test_returns_callable_backed_by_store(self):
        store = InMemoryStoreProfileStore()
        store.set_stripe_customer_id("Uowner123", "cus_abc")
        resolve = make_resolve_store_id_by_customer(store)
        self.assertEqual(resolve("cus_abc"), "Uowner123")

    def test_returns_none_for_unknown_customer(self):
        store = InMemoryStoreProfileStore()
        resolve = make_resolve_store_id_by_customer(store)
        self.assertIsNone(resolve("cus_unknown"))


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

    def test_linking_also_populates_reverse_lookup(self):
        """stripe-webhook-event-dispatch-design.md 5節: checkout.session.completed受信時に
        後続のinvoice.payment_succeeded等が使う逆引きも同時に整備されることを確認する。"""
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "Uowner123", "customer": "cus_abc"}},
        }
        handle_checkout_session_completed(event, self.store)
        self.assertEqual(
            self.store.get_store_id_by_stripe_customer_id("cus_abc"), "Uowner123"
        )


class EvaluateOnboardingCompletionMessageDispatchTest(unittest.TestCase):
    """onboarding-completion-message-design.md 残課題。"""

    def setUp(self):
        self.store = InMemoryStoreProfileStore()

    def _call(self, **overrides):
        params = dict(
            user_id="Uowner123",
            business_hours_configured=True,
            slot_interval_minutes=30,
            concurrent_capacity=1,
            menu_count=1,
            store=self.store,
        )
        params.update(overrides)
        return evaluate_onboarding_completion_message_dispatch(**params)

    def test_returns_true_first_time_all_required_fields_present(self):
        self.assertTrue(self._call())
        self.assertTrue(
            self.store.is_onboarding_completion_message_sent("Uowner123")
        )

    def test_returns_false_on_second_call_even_if_still_complete(self):
        self._call()
        self.assertFalse(self._call())

    def test_returns_false_when_business_hours_not_configured(self):
        self.assertFalse(self._call(business_hours_configured=False))
        self.assertFalse(
            self.store.is_onboarding_completion_message_sent("Uowner123")
        )

    def test_returns_false_when_slot_interval_minutes_is_none(self):
        self.assertFalse(self._call(slot_interval_minutes=None))

    def test_returns_false_when_slot_interval_minutes_is_zero(self):
        self.assertFalse(self._call(slot_interval_minutes=0))

    def test_returns_false_when_concurrent_capacity_is_none(self):
        self.assertFalse(self._call(concurrent_capacity=None))

    def test_returns_false_when_concurrent_capacity_is_zero(self):
        self.assertFalse(self._call(concurrent_capacity=0))

    def test_returns_false_when_menu_count_is_zero(self):
        self.assertFalse(self._call(menu_count=0))

    def test_raises_on_empty_user_id(self):
        with self.assertRaises(ValueError):
            self._call(user_id="")

    def test_incomplete_then_complete_fires_only_once_on_the_completing_save(self):
        self.assertFalse(self._call(menu_count=0))
        self.assertTrue(self._call(menu_count=1))
        self.assertFalse(self._call(menu_count=1))

    def test_different_stores_are_isolated(self):
        self.assertTrue(self._call(user_id="Uowner123"))
        self.assertTrue(self._call(user_id="Uowner999"))


if __name__ == "__main__":
    unittest.main()
