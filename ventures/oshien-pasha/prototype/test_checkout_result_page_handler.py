#!/usr/bin/env python3
import unittest

from checkout_result_page_handler import (
    CheckoutSessionNotFoundError,
    CombinedPassLookup,
    InMemoryStripeCheckoutSessionLookup,
    InMemoryStripeCheckoutSessionModeLookup,
    receive_checkout_result_request,
    receive_checkout_result_request_combined,
    resolve_checkout_result,
    resolve_checkout_result_combined,
)
from fan_pass_store import InMemoryFanPassStore
from one_time_pass_store import InMemoryOneTimePassStore


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


class ReceiveCheckoutResultRequestTests(unittest.TestCase):
    def test_missing_checkout_session_id_returns_400(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        store = InMemoryFanPassStore()

        for value in (None, "", "   "):
            result = receive_checkout_result_request(lookup, store, value)
            self.assertEqual(result.status_code, 400)
            self.assertEqual(result.error, "missing_checkout_session_id")
            self.assertIsNone(result.result)

    def test_unknown_checkout_session_id_returns_404(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        store = InMemoryFanPassStore()

        result = receive_checkout_result_request(lookup, store, "cs_missing")

        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.error, "unknown_checkout_session_id")
        self.assertIsNone(result.result)

    def test_ready_returns_200_with_access_token_in_result(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        lookup.register("cs_ready", "sub_ready")
        store, access_token = _build_store_with_fan_pass("sub_ready")

        result = receive_checkout_result_request(lookup, store, "cs_ready")

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)
        self.assertEqual(result.result.status, "ready")
        self.assertEqual(result.result.access_token, access_token)

    def test_pending_returns_200_with_pending_status(self) -> None:
        lookup = InMemoryStripeCheckoutSessionLookup()
        lookup.register("cs_pending", "sub_pending")
        store = InMemoryFanPassStore()

        result = receive_checkout_result_request(
            lookup, store, "cs_pending", sleep=lambda _s: None
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)
        self.assertEqual(result.result.status, "pending")
        self.assertIsNone(result.result.access_token)


def _build_combined_lookup(
    mode_lookup: InMemoryStripeCheckoutSessionModeLookup,
    stripe_lookup: InMemoryStripeCheckoutSessionLookup,
    fan_pass_store: InMemoryFanPassStore,
    one_time_pass_store: InMemoryOneTimePassStore,
) -> CombinedPassLookup:
    return CombinedPassLookup(mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store)


class ResolveCheckoutResultCombinedTests(unittest.TestCase):
    def test_subscription_mode_ready_on_first_attempt(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        mode_lookup.register("cs_sub_1", "subscription")
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        stripe_lookup.register("cs_sub_1", "sub_1")
        fan_pass_store, access_token = _build_store_with_fan_pass("sub_1")
        one_time_pass_store = InMemoryOneTimePassStore()
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )

        result = resolve_checkout_result_combined(mode_lookup, combined, "cs_sub_1")

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.access_token, access_token)
        self.assertFalse(result.consumed)

    def test_payment_mode_ready_on_first_attempt(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        mode_lookup.register("cs_pay_1", "payment")
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        fan_pass_store = InMemoryFanPassStore()
        one_time_pass_store = InMemoryOneTimePassStore()
        _internal_id, access_token = one_time_pass_store.create(
            stripe_checkout_session_id="cs_pay_1", created_at=1_000_000
        )
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )

        result = resolve_checkout_result_combined(mode_lookup, combined, "cs_pay_1")

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.access_token, access_token)
        self.assertEqual(result.poll_attempts_used, 1)
        self.assertFalse(result.consumed)

    def test_payment_mode_pending_until_webhook_arrives(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        mode_lookup.register("cs_pay_2", "payment")
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        fan_pass_store = InMemoryFanPassStore()
        one_time_pass_store = InMemoryOneTimePassStore()
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )
        created_token: dict[str, str] = {}
        attempts = {"n": 0}

        def sleep(_seconds: float) -> None:
            attempts["n"] += 1
            if attempts["n"] == 1:
                _internal_id, access_token = one_time_pass_store.create(
                    stripe_checkout_session_id="cs_pay_2", created_at=2_000_000
                )
                created_token["value"] = access_token

        result = resolve_checkout_result_combined(mode_lookup, combined, "cs_pay_2", sleep=sleep)

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.access_token, created_token["value"])
        self.assertEqual(result.poll_attempts_used, 2)

    def test_payment_mode_surfaces_consumed_flag(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        mode_lookup.register("cs_pay_3", "payment")
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        fan_pass_store = InMemoryFanPassStore()
        one_time_pass_store = InMemoryOneTimePassStore()
        internal_id, _access_token = one_time_pass_store.create(
            stripe_checkout_session_id="cs_pay_3", created_at=3_000_000
        )
        one_time_pass_store.mark_consumed(internal_id, consumed_at=3_000_500)
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )

        result = resolve_checkout_result_combined(mode_lookup, combined, "cs_pay_3")

        self.assertEqual(result.status, "ready")
        self.assertTrue(result.consumed)

    def test_unknown_session_raises_without_polling_one_time_pass_store(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        fan_pass_store = InMemoryFanPassStore()
        one_time_pass_store = InMemoryOneTimePassStore()
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )

        with self.assertRaises(CheckoutSessionNotFoundError):
            resolve_checkout_result_combined(mode_lookup, combined, "cs_missing")


class ReceiveCheckoutResultRequestCombinedTests(unittest.TestCase):
    def test_payment_mode_returns_200_with_access_token(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        mode_lookup.register("cs_pay_http", "payment")
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        fan_pass_store = InMemoryFanPassStore()
        one_time_pass_store = InMemoryOneTimePassStore()
        _internal_id, access_token = one_time_pass_store.create(
            stripe_checkout_session_id="cs_pay_http", created_at=4_000_000
        )
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )

        result = receive_checkout_result_request_combined(mode_lookup, combined, "cs_pay_http")

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.result.status, "ready")
        self.assertEqual(result.result.access_token, access_token)

    def test_missing_checkout_session_id_returns_400(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        fan_pass_store = InMemoryFanPassStore()
        one_time_pass_store = InMemoryOneTimePassStore()
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )

        for value in (None, "", "   "):
            result = receive_checkout_result_request_combined(mode_lookup, combined, value)
            self.assertEqual(result.status_code, 400)
            self.assertEqual(result.error, "missing_checkout_session_id")

    def test_unknown_checkout_session_id_returns_404(self) -> None:
        mode_lookup = InMemoryStripeCheckoutSessionModeLookup()
        stripe_lookup = InMemoryStripeCheckoutSessionLookup()
        fan_pass_store = InMemoryFanPassStore()
        one_time_pass_store = InMemoryOneTimePassStore()
        combined = _build_combined_lookup(
            mode_lookup, stripe_lookup, fan_pass_store, one_time_pass_store
        )

        result = receive_checkout_result_request_combined(mode_lookup, combined, "cs_missing")

        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.error, "unknown_checkout_session_id")


if __name__ == "__main__":
    unittest.main()
