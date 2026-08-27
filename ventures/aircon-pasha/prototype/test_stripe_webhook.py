import hashlib
import hmac
import json
import unittest
from datetime import datetime, timezone

from deletion_candidate import InMemoryProfileDeletionCandidateStore
from stripe_webhook import receive_stripe_webhook, verify_stripe_signature

SECRET = "whsec_test_secret"
PAYLOAD = b'{"id":"evt_1","type":"customer.subscription.deleted"}'
NOW = 1_700_000_000.0
NOW_DT = datetime.fromtimestamp(NOW, tz=timezone.utc)


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


def _make_store_and_resolver(customer_to_user=None):
    store = InMemoryProfileDeletionCandidateStore()
    mapping = customer_to_user or {}

    def resolve_user_id(customer):
        return mapping.get(customer)

    return store, resolve_user_id


class ReceiveStripeWebhookTest(unittest.TestCase):
    def test_invalid_signature_returns_401_without_dispatch(self):
        store, resolve_user_id = _make_store_and_resolver({"cus_1": "user_1"})
        event = {
            "type": "customer.subscription.deleted",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        result = receive_stripe_webhook(
            body,
            "not-a-valid-header",
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            now=NOW_DT,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_signature")
        self.assertIsNone(result.dispatch_result)
        self.assertIsNone(store.get_deletion_candidate_at("user_1"))

    def test_unparsable_json_returns_400(self):
        store, resolve_user_id = _make_store_and_resolver()
        body = b"not-json{"
        header = _header(body, SECRET, int(NOW))
        result = receive_stripe_webhook(
            body, header, SECRET, store=store, resolve_user_id=resolve_user_id, now=NOW_DT
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_json")

    def test_non_dict_json_returns_400(self):
        store, resolve_user_id = _make_store_and_resolver()
        body = json.dumps(["not", "a", "dict"]).encode("utf-8")
        header = _header(body, SECRET, int(NOW))
        result = receive_stripe_webhook(
            body, header, SECRET, store=store, resolve_user_id=resolve_user_id, now=NOW_DT
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_event")

    def test_valid_subscription_deleted_event_returns_200_and_marks_user(self):
        store, resolve_user_id = _make_store_and_resolver({"cus_1": "user_1"})
        event = {
            "type": "customer.subscription.deleted",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))
        result = receive_stripe_webhook(
            body, header, SECRET, store=store, resolve_user_id=resolve_user_id, now=NOW_DT
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.marked_user_ids, ["user_1"])
        self.assertIsNotNone(store.get_deletion_candidate_at("user_1"))

    def test_unresolved_customer_still_returns_200(self):
        store, resolve_user_id = _make_store_and_resolver({})
        event = {
            "type": "customer.subscription.deleted",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_unknown"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))
        result = receive_stripe_webhook(
            body, header, SECRET, store=store, resolve_user_id=resolve_user_id, now=NOW_DT
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.unresolved_customers, ["cus_unknown"])


if __name__ == "__main__":
    unittest.main()
