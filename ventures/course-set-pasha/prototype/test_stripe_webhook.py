import hashlib
import hmac
import unittest
from datetime import datetime, timezone

from deletion_candidate import InMemoryProfileDeletionCandidateStore
from stripe_webhook import dispatch_stripe_event, verify_stripe_signature

SECRET = "whsec_test_secret"
PAYLOAD = b'{"id":"evt_1","type":"customer.subscription.deleted"}'
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
        self.assertTrue(
            verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW)
        )

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
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW)
        )

    def test_valid_signature_outside_tolerance_returns_false(self):
        timestamp = int(NOW) - 301
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW)
        )

    def test_future_timestamp_outside_tolerance_returns_false(self):
        timestamp = int(NOW) + 301
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW)
        )

    def test_secret_rotation_matches_any_v1_signature(self):
        timestamp = int(NOW)
        correct_sig = _sign(PAYLOAD, SECRET, timestamp)
        header = f"t={timestamp},v1=deadbeef,v1={correct_sig}"
        self.assertTrue(
            verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW)
        )

    def test_only_v0_present_returns_false(self):
        timestamp = int(NOW)
        v0_sig = hmac.new(
            SECRET.encode("utf-8"), PAYLOAD, hashlib.sha1
        ).hexdigest()
        header = f"t={timestamp},v0={v0_sig}"
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW)
        )


def _resolver(mapping):
    return lambda customer: mapping.get(customer)


class DispatchStripeEventTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryProfileDeletionCandidateStore()
        self.now = datetime(2026, 8, 22, tzinfo=timezone.utc)

    def test_subscription_deleted_marks_deletion_candidate(self):
        event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.marked_user_ids, ["user_1"])
        self.assertIsNotNone(self.store.get_deletion_candidate_at("user_1"))

    def test_subscription_deleted_with_non_numeric_created_is_invalid(self):
        event = {
            "type": "customer.subscription.deleted",
            "created": "not-a-timestamp",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.invalid_events, ["customer.subscription.deleted"])
        self.assertIsNone(self.store.get_deletion_candidate_at("user_1"))

    def test_subscription_created_clears_deletion_candidate(self):
        self.store.set_deletion_candidate_at("user_1", self.now)
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.cleared_user_ids, ["user_1"])
        self.assertIsNone(self.store.get_deletion_candidate_at("user_1"))

    def test_subscription_created_is_idempotent_when_nothing_set(self):
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.cleared_user_ids, ["user_1"])
        self.assertIsNone(self.store.get_deletion_candidate_at("user_1"))

    def test_subscription_updated_active_clears_deletion_candidate(self):
        self.store.set_deletion_candidate_at("user_1", self.now)
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": "cus_A", "status": "active"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.cleared_user_ids, ["user_1"])
        self.assertIsNone(self.store.get_deletion_candidate_at("user_1"))

    def test_subscription_updated_trialing_clears_deletion_candidate(self):
        self.store.set_deletion_candidate_at("user_1", self.now)
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": "cus_A", "status": "trialing"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.cleared_user_ids, ["user_1"])

    def test_subscription_updated_other_status_is_no_op(self):
        self.store.set_deletion_candidate_at("user_1", self.now)
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": "cus_A", "status": "past_due"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.cleared_user_ids, [])
        self.assertEqual(result.marked_user_ids, [])
        self.assertIsNotNone(self.store.get_deletion_candidate_at("user_1"))

    def test_unhandled_type_is_recorded_as_ignored(self):
        event = {"type": "invoice.paid", "data": {"object": {"customer": "cus_A"}}}
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.ignored_types, ["invoice.paid"])

    def test_unresolved_customer_is_recorded_and_no_store_write_happens(self):
        event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_unknown"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({})
        )
        self.assertEqual(result.unresolved_customers, ["cus_unknown"])
        self.assertEqual(result.marked_user_ids, [])


if __name__ == "__main__":
    unittest.main()
