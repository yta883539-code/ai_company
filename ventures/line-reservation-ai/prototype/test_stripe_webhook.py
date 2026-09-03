import hashlib
import hmac
import unittest

from store_profile_store import (
    InMemoryStoreProfileStore,
    handle_checkout_session_completed,
    make_resolve_store_id_by_customer,
)
from stripe_webhook import (
    EVENT_CHECKOUT_SESSION_COMPLETED,
    EVENT_CUSTOMER_SUBSCRIPTION_DELETED,
    EVENT_CUSTOMER_SUBSCRIPTION_UPDATED,
    EVENT_INVOICE_PAYMENT_FAILED,
    EVENT_INVOICE_PAYMENT_SUCCEEDED,
    InMemoryStripeEventIdStore,
    route_stripe_event,
    verify_stripe_signature,
)

SECRET = "whsec_test_secret"
PAYLOAD = b'{"id":"evt_1","type":"checkout.session.completed"}'
NOW = 1_700_000_000.0


def _sign(payload: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def _header(payload: bytes, secret: str, timestamp: int, *, extra_v1=None, v0=None) -> str:
    parts = [f"t={timestamp}"]
    sig = _sign(payload, secret, timestamp)
    parts.append(f"v1={sig}")
    if extra_v1:
        parts.append(f"v1={extra_v1}")
    if v0:
        parts.append(f"v0={v0}")
    return ",".join(parts)


class VerifyStripeSignatureTest(unittest.TestCase):
    def test_valid_signature_within_tolerance_returns_true(self):
        timestamp = int(NOW)
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertTrue(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_missing_header_returns_false(self):
        self.assertFalse(verify_stripe_signature(PAYLOAD, None, SECRET, now=NOW))
        self.assertFalse(verify_stripe_signature(PAYLOAD, "", SECRET, now=NOW))

    def test_malformed_header_returns_false(self):
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, "not-a-valid-header", SECRET, now=NOW)
        )
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, "t=1700000000", SECRET, now=NOW)
        )
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, "v1=deadbeef", SECRET, now=NOW)
        )

    def test_signature_mismatch_returns_false(self):
        timestamp = int(NOW)
        header = _header(PAYLOAD, "wrong_secret", timestamp)
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_valid_signature_outside_tolerance_returns_false(self):
        timestamp = int(NOW) - 301
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_future_timestamp_outside_tolerance_returns_false(self):
        timestamp = int(NOW) + 301
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_secret_rotation_matches_any_v1_signature(self):
        timestamp = int(NOW)
        correct_sig = _sign(PAYLOAD, SECRET, timestamp)
        header = f"t={timestamp},v1=deadbeef,v1={correct_sig}"
        self.assertTrue(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_only_v0_present_returns_false(self):
        timestamp = int(NOW)
        v0_sig = hmac.new(SECRET.encode("utf-8"), PAYLOAD, hashlib.sha1).hexdigest()
        header = f"t={timestamp},v0={v0_sig}"
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))


def _raise_if_called(customer_id: str):
    raise AssertionError(
        "resolve_store_id_by_customer must not be called for checkout.session.completed"
    )


class RouteStripeEventTest(unittest.TestCase):
    def test_ignored_event_type(self):
        route = route_stripe_event(
            {"type": "invoice.paid", "data": {"object": {}}},
            resolve_store_id_by_customer=_raise_if_called,
        )
        self.assertTrue(route.ignored)
        self.assertIsNone(route.store_id)

    def test_checkout_session_completed_uses_client_reference_id_directly(self):
        event = {
            "type": EVENT_CHECKOUT_SESSION_COMPLETED,
            "data": {
                "object": {
                    "client_reference_id": "store-owner-line-id-1",
                    "customer": "cus_ABC123",
                }
            },
        }
        route = route_stripe_event(event, resolve_store_id_by_customer=_raise_if_called)
        self.assertEqual(route.store_id, "store-owner-line-id-1")
        self.assertEqual(route.customer_id, "cus_ABC123")
        self.assertFalse(route.unresolved_customer)
        self.assertFalse(route.ignored)

    def test_checkout_session_completed_missing_client_reference_id_is_unresolved(self):
        event = {
            "type": EVENT_CHECKOUT_SESSION_COMPLETED,
            "data": {"object": {"customer": "cus_ABC123"}},
        }
        route = route_stripe_event(event, resolve_store_id_by_customer=_raise_if_called)
        self.assertTrue(route.unresolved_customer)
        self.assertIsNone(route.store_id)

    def test_invoice_payment_succeeded_resolves_via_customer(self):
        event = {
            "type": EVENT_INVOICE_PAYMENT_SUCCEEDED,
            "data": {"object": {"customer": "cus_XYZ789"}},
        }
        route = route_stripe_event(
            event,
            resolve_store_id_by_customer=lambda customer_id: {
                "cus_XYZ789": "store-owner-line-id-2"
            }.get(customer_id),
        )
        self.assertEqual(route.store_id, "store-owner-line-id-2")
        self.assertFalse(route.unresolved_customer)

    def test_invoice_payment_failed_unknown_customer_is_unresolved(self):
        event = {
            "type": EVENT_INVOICE_PAYMENT_FAILED,
            "data": {"object": {"customer": "cus_UNKNOWN"}},
        }
        route = route_stripe_event(
            event, resolve_store_id_by_customer=lambda customer_id: None
        )
        self.assertTrue(route.unresolved_customer)
        self.assertIsNone(route.store_id)

    def test_invoice_event_missing_customer_is_unresolved(self):
        event = {"type": EVENT_INVOICE_PAYMENT_FAILED, "data": {"object": {}}}
        route = route_stripe_event(event, resolve_store_id_by_customer=_raise_if_called)
        self.assertTrue(route.unresolved_customer)

    def test_customer_subscription_deleted_resolves_via_customer(self):
        # subscription-deleted-event-routing-design.md 2節: 追加の分岐は無く、
        # invoice系と同じcustomerベースの解決に乗ることを確認する。
        event = {
            "type": EVENT_CUSTOMER_SUBSCRIPTION_DELETED,
            "data": {"object": {"customer": "cus_XYZ789"}},
        }
        route = route_stripe_event(
            event,
            resolve_store_id_by_customer=lambda customer_id: {
                "cus_XYZ789": "store-owner-line-id-2"
            }.get(customer_id),
        )
        self.assertEqual(route.store_id, "store-owner-line-id-2")
        self.assertFalse(route.unresolved_customer)
        self.assertFalse(route.ignored)

    def test_customer_subscription_deleted_unknown_customer_is_unresolved(self):
        event = {
            "type": EVENT_CUSTOMER_SUBSCRIPTION_DELETED,
            "data": {"object": {"customer": "cus_UNKNOWN"}},
        }
        route = route_stripe_event(
            event, resolve_store_id_by_customer=lambda customer_id: None
        )
        self.assertTrue(route.unresolved_customer)
        self.assertIsNone(route.store_id)

    def test_customer_subscription_updated_resolves_via_customer(self):
        # customer-subscription-updated-event-routing-design.md 2節: deletedと同じく
        # 追加の分岐は無く、customerベースの既存else分岐に乗ることを確認する。
        event = {
            "type": EVENT_CUSTOMER_SUBSCRIPTION_UPDATED,
            "data": {
                "object": {"customer": "cus_XYZ789", "cancel_at_period_end": True},
                "previous_attributes": {"cancel_at_period_end": False},
            },
        }
        route = route_stripe_event(
            event,
            resolve_store_id_by_customer=lambda customer_id: {
                "cus_XYZ789": "store-owner-line-id-2"
            }.get(customer_id),
        )
        self.assertEqual(route.store_id, "store-owner-line-id-2")
        self.assertFalse(route.unresolved_customer)
        self.assertFalse(route.ignored)

    def test_customer_subscription_updated_unknown_customer_is_unresolved(self):
        event = {
            "type": EVENT_CUSTOMER_SUBSCRIPTION_UPDATED,
            "data": {"object": {"customer": "cus_UNKNOWN"}},
        }
        route = route_stripe_event(
            event, resolve_store_id_by_customer=lambda customer_id: None
        )
        self.assertTrue(route.unresolved_customer)
        self.assertIsNone(route.store_id)


class RouteStripeEventWithStoreProfileStoreWiringTest(unittest.TestCase):
    """stripe-webhook-event-dispatch-design.md 5節・stripe-customer-id-reverse-lookup-
    design.md: checkout.session.completed受信でstore_profile_store.pyに書き込まれた
    紐付けを、後続のinvoice.payment_succeeded/invoice.payment_failedが
    make_resolve_store_id_by_customer()経由で実際に解決できることを結線レベルで確認する
    (course-set-pashaのDispatchStripeEventWiringTest系と同種のテスト)。"""

    def setUp(self):
        self.store = InMemoryStoreProfileStore()
        self.resolve_store_id_by_customer = make_resolve_store_id_by_customer(self.store)

    def test_customer_unresolved_before_checkout_session_completed(self):
        event = {
            "type": EVENT_INVOICE_PAYMENT_SUCCEEDED,
            "data": {"object": {"customer": "cus_ABC123"}},
        }
        route = route_stripe_event(
            event, resolve_store_id_by_customer=self.resolve_store_id_by_customer
        )
        self.assertTrue(route.unresolved_customer)
        self.assertIsNone(route.store_id)

    def test_invoice_payment_succeeded_resolves_after_checkout_session_completed(self):
        checkout_event = {
            "type": EVENT_CHECKOUT_SESSION_COMPLETED,
            "data": {
                "object": {
                    "client_reference_id": "store-owner-line-id-1",
                    "customer": "cus_ABC123",
                }
            },
        }
        handle_checkout_session_completed(checkout_event, self.store)

        invoice_event = {
            "type": EVENT_INVOICE_PAYMENT_SUCCEEDED,
            "data": {"object": {"customer": "cus_ABC123"}},
        }
        route = route_stripe_event(
            invoice_event, resolve_store_id_by_customer=self.resolve_store_id_by_customer
        )
        self.assertEqual(route.store_id, "store-owner-line-id-1")
        self.assertFalse(route.unresolved_customer)

    def test_invoice_payment_failed_resolves_after_checkout_session_completed(self):
        checkout_event = {
            "type": EVENT_CHECKOUT_SESSION_COMPLETED,
            "data": {
                "object": {
                    "client_reference_id": "store-owner-line-id-1",
                    "customer": "cus_ABC123",
                }
            },
        }
        handle_checkout_session_completed(checkout_event, self.store)

        invoice_event = {
            "type": EVENT_INVOICE_PAYMENT_FAILED,
            "data": {"object": {"customer": "cus_ABC123"}},
        }
        route = route_stripe_event(
            invoice_event, resolve_store_id_by_customer=self.resolve_store_id_by_customer
        )
        self.assertEqual(route.store_id, "store-owner-line-id-1")
        self.assertFalse(route.unresolved_customer)


class RouteStripeEventIdempotencyTest(unittest.TestCase):
    """stripe-event-idempotency-design.md(フェーズ続き179)対応。aircon-pasha/
    course-set-pashaのべき等性テストと同種の観点を、本ventureのroute_stripe_event()に
    対して確認する。"""

    def _checkout_event(self, event_id: str = "evt_1"):
        return {
            "id": event_id,
            "type": EVENT_CHECKOUT_SESSION_COMPLETED,
            "data": {
                "object": {
                    "client_reference_id": "store-owner-line-id-1",
                    "customer": "cus_ABC123",
                }
            },
        }

    def test_first_delivery_is_processed_and_marked(self):
        store = InMemoryStripeEventIdStore()
        route = route_stripe_event(
            self._checkout_event(),
            resolve_store_id_by_customer=_raise_if_called,
            event_id_store=store,
        )
        self.assertFalse(route.duplicate)
        self.assertEqual(route.store_id, "store-owner-line-id-1")
        self.assertTrue(store.has_processed("evt_1"))

    def test_duplicate_delivery_skips_resolution(self):
        store = InMemoryStripeEventIdStore()
        route_stripe_event(
            self._checkout_event(),
            resolve_store_id_by_customer=_raise_if_called,
            event_id_store=store,
        )
        duplicate_route = route_stripe_event(
            self._checkout_event(),
            resolve_store_id_by_customer=_raise_if_called,
            event_id_store=store,
        )
        self.assertTrue(duplicate_route.duplicate)
        self.assertIsNone(duplicate_route.store_id)

    def test_ignored_event_type_is_also_marked_processed(self):
        store = InMemoryStripeEventIdStore()
        event = {"id": "evt_ignored", "type": "invoice.paid", "data": {"object": {}}}
        route = route_stripe_event(
            event, resolve_store_id_by_customer=_raise_if_called, event_id_store=store
        )
        self.assertTrue(route.ignored)
        self.assertFalse(route.duplicate)
        self.assertTrue(store.has_processed("evt_ignored"))

        duplicate_route = route_stripe_event(
            event, resolve_store_id_by_customer=_raise_if_called, event_id_store=store
        )
        self.assertTrue(duplicate_route.duplicate)

    def test_missing_event_id_skips_idempotency_check(self):
        store = InMemoryStripeEventIdStore()
        event = {
            "type": EVENT_CHECKOUT_SESSION_COMPLETED,
            "data": {
                "object": {
                    "client_reference_id": "store-owner-line-id-1",
                    "customer": "cus_ABC123",
                }
            },
        }
        first = route_stripe_event(
            event, resolve_store_id_by_customer=_raise_if_called, event_id_store=store
        )
        second = route_stripe_event(
            event, resolve_store_id_by_customer=_raise_if_called, event_id_store=store
        )
        self.assertFalse(first.duplicate)
        self.assertFalse(second.duplicate)
        self.assertEqual(second.store_id, "store-owner-line-id-1")

    def test_event_id_store_omitted_defaults_to_no_check(self):
        route = route_stripe_event(
            self._checkout_event(), resolve_store_id_by_customer=_raise_if_called
        )
        self.assertFalse(route.duplicate)
        self.assertEqual(route.store_id, "store-owner-line-id-1")


if __name__ == "__main__":
    unittest.main()
