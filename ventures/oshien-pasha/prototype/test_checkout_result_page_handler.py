#!/usr/bin/env python3
import unittest

from checkout_result_page_handler import (
    CheckoutSessionNotFoundError,
    InMemoryStripeCheckoutSessionLookup,
    resolve_checkout_result,
)
from fan_pass_store import InMemoryFanPassStore


def _build_store_with_fan_pass(stripe_subscription_id: str) -> tuple[InMemoryFanPassStore, str]:
    store = InMemoryFanPassStore()
    _internal_id, access_token = store.create(
        email="fan@example.com",
        stripe_customer_id="cus_1",
        stripe_subscription_id=stripe_subscription_id,
    )
    return store, access_token


class ResolveCheckoutResultTests(unittest.TestCase):
    def test_ready_on_first_attempt_when_webhook_already_arrived(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        lookup.register("cs_1", "sub_1")
        store, access_token = _build_store_with_fan_pass("sub_1")

        result = resolve_checkout_result(lookup, store, "cs_1")

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.access_token, access_token)
        self.assertEqual(result.poll_attempts_used, 1)

    def test_ready_after_webhook_arrives_mid_poll(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        lookup.register("cs_2", "sub_2")
        store = InMemoryFanPassStore()
        sleeps: list[float] = []

        attempts = {"n": 0}
        created_token: dict[str, str] = {}

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            attempts["n"] += 1
            if attempts["n"] == 2:
                _internal_id, access_token = store.create(
                    email="fan2@example.com",
                    stripe_customer_id="cus_2",
                    stripe_subscription_id="sub_2",
                )
                created_token["value"] = access_token

        result = resolve_checkout_result(lookup, store, "cs_2", sleep=sleep)

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.access_token, created_token["value"])
        self.assertEqual(result.poll_attempts_used, 3)
        self.assertEqual(sleeps, [1.0, 1.0])

    def test_pending_when_webhook_never_arrives_within_max_attempts(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        lookup.register("cs_3", "sub_3")
        store = InMemoryFanPassStore()
        sleep_calls = []

        result = resolve_checkout_result(
            lookup, store, "cs_3", sleep=lambda s: sleep_calls.append(s)
        )

        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.access_token)
        self.assertEqual(result.poll_attempts_used, 5)
        self.assertEqual(len(sleep_calls), 4)

    def test_checkout_session_not_found_raises(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        store = InMemoryFanPassStore()

        with self.assertRaises(CheckoutSessionNotFoundError):
            resolve_checkout_result(lookup, store, "cs_missing")

    def test_custom_max_attempts_and_interval_respected(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        lookup.register("cs_4", "sub_4")
        store = InMemoryFanPassStore()
        sleep_calls = []

        result = resolve_checkout_result(
            lookup,
            store,
            "cs_4",
            sleep=lambda s: sleep_calls.append(s),
            max_attempts=2,
            interval_seconds=0.5,
        )

        self.assertEqual(result.status, "pending")
        self.assertEqual(result.poll_attempts_used, 2)
        self.assertEqual(sleep_calls, [0.5])


if __name__ == "__main__":
    unittest.main()
