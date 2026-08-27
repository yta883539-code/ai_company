import hashlib
import hmac
import json
import unittest
from datetime import datetime, timezone

from deletion_candidate import InMemoryProfileDeletionCandidateStore
from stripe_webhook import (
    handle_checkout_session_completed,
    make_resolve_user_id,
    receive_stripe_webhook,
    verify_stripe_signature,
)
from user_id_linking import InMemoryUserProfileStore, UserProfile

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


def _seed_profile(store, user_id="user_1"):
    store.save(
        user_id,
        UserProfile(
            business_name="テストクリーニング", business_type="独立系",
            email="owner@example.com", linked_at=NOW_DT,
        ),
    )


class HandleCheckoutSessionCompletedTest(unittest.TestCase):
    def test_links_known_user_profile_to_stripe_customer(self):
        store = InMemoryUserProfileStore()
        _seed_profile(store, "user_1")
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "user_1", "customer": "cus_1"}},
        }

        result = handle_checkout_session_completed(event, store)

        self.assertTrue(result.linked)
        self.assertEqual(result.user_id, "user_1")
        self.assertEqual(result.stripe_customer_id, "cus_1")
        self.assertEqual(store.get("user_1").stripe_customer_id, "cus_1")

    def test_missing_client_reference_id_is_not_linked(self):
        store = InMemoryUserProfileStore()
        _seed_profile(store, "user_1")
        event = {"type": "checkout.session.completed", "data": {"object": {"customer": "cus_1"}}}

        result = handle_checkout_session_completed(event, store)

        self.assertFalse(result.linked)
        self.assertEqual(result.error, "missing_fields")

    def test_missing_customer_is_not_linked(self):
        store = InMemoryUserProfileStore()
        _seed_profile(store, "user_1")
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "user_1"}},
        }

        result = handle_checkout_session_completed(event, store)

        self.assertFalse(result.linked)
        self.assertEqual(result.error, "missing_fields")

    def test_unknown_user_profile_is_not_linked(self):
        """design 4節: 決済前にuser_profileが存在している前提だが、想定外の順序で
        Checkout Sessionが作成された場合は存在しないuser_idへ書き込まず異常系として扱う。"""
        store = InMemoryUserProfileStore()
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "no-such-user", "customer": "cus_1"}},
        }

        result = handle_checkout_session_completed(event, store)

        self.assertFalse(result.linked)
        self.assertEqual(result.error, "user_profile_not_found")
        self.assertIsNone(store.get_user_id_by_stripe_customer_id("cus_1"))


class MakeResolveUserIdTest(unittest.TestCase):
    def test_delegates_to_store_reverse_lookup(self):
        store = InMemoryUserProfileStore()
        _seed_profile(store, "user_1")
        store.set_stripe_customer_id("user_1", "cus_1")

        resolve_user_id = make_resolve_user_id(store)

        self.assertEqual(resolve_user_id("cus_1"), "user_1")
        self.assertIsNone(resolve_user_id("cus_unknown"))


class ReceiveStripeWebhookCheckoutSessionCompletedTest(unittest.TestCase):
    def test_links_user_and_returns_200(self):
        store = InMemoryProfileDeletionCandidateStore()
        profile_store = InMemoryUserProfileStore()
        _seed_profile(profile_store, "user_1")
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "user_1", "customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=lambda customer: None,
            user_profile_store=profile_store,
            now=NOW_DT,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.dispatch_result)
        self.assertTrue(result.checkout_link_result.linked)
        self.assertEqual(profile_store.get("user_1").stripe_customer_id, "cus_1")

    def test_missing_user_profile_store_returns_200_without_linking(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "user_1", "customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=lambda customer: None,
            now=NOW_DT,
        )

        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.checkout_link_result.linked)
        self.assertEqual(result.checkout_link_result.error, "store_not_configured")

    def test_subsequent_subscription_event_resolves_via_linked_profile(self):
        """checkout.session.completedで紐付けたuser_idを、後続のcustomer.subscription.*
        イベントがmake_resolve_user_id()経由で正しく逆引きできることを確認する
        (deletion_candidate.pyへの実際のマーク付けまで一気通貫で確認)。"""
        store = InMemoryProfileDeletionCandidateStore()
        profile_store = InMemoryUserProfileStore()
        _seed_profile(profile_store, "user_1")
        resolve_user_id = make_resolve_user_id(profile_store)

        checkout_event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "user_1", "customer": "cus_1"}},
        }
        checkout_body = json.dumps(checkout_event).encode("utf-8")
        checkout_header = _header(checkout_body, SECRET, int(NOW))
        receive_stripe_webhook(
            checkout_body,
            checkout_header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            user_profile_store=profile_store,
            now=NOW_DT,
        )

        subscription_event = {
            "type": "customer.subscription.deleted",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_1"}},
        }
        subscription_body = json.dumps(subscription_event).encode("utf-8")
        subscription_header = _header(subscription_body, SECRET, int(NOW))
        result = receive_stripe_webhook(
            subscription_body,
            subscription_header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            user_profile_store=profile_store,
            now=NOW_DT,
        )

        self.assertEqual(result.dispatch_result.marked_user_ids, ["user_1"])
        self.assertIsNotNone(store.get_deletion_candidate_at("user_1"))


if __name__ == "__main__":
    unittest.main()
