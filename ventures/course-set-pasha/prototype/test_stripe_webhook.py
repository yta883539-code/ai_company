import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import datetime, timezone

from application_form_submission_flow import InMemoryUserProfileStore
from deletion_candidate import InMemoryProfileDeletionCandidateStore
from stripe_webhook import (
    dispatch_stripe_event,
    get_stripe_runtime_dependencies,
    handle_checkout_session_completed,
    main,
    make_resolve_user_id,
    receive_stripe_webhook,
    verify_stripe_signature,
)

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


class ReceiveStripeWebhookTest(unittest.TestCase):
    """stripe-webhook-http-entry-point-design.md 2節。LINE版ReceiveWebhookTestと対称。"""

    def setUp(self):
        self.store = InMemoryProfileDeletionCandidateStore()
        self.now = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)  # NOW相当
        self.resolve_user_id = _resolver({"cus_A": "user_1"})

    def _call(self, body: bytes, header: str) -> object:
        return receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=self.store,
            resolve_user_id=self.resolve_user_id,
            now=self.now,
        )

    def test_invalid_signature_returns_401_without_dispatch(self):
        body = b'{"id":"evt_1","type":"customer.subscription.deleted","created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        result = self._call(body, "not-a-valid-header")
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_signature")
        self.assertIsNone(result.dispatch_result)
        self.assertIsNone(self.store.get_deletion_candidate_at("user_1"))

    def test_unparseable_json_returns_400(self):
        body = b"not-json"
        header = _header(body, SECRET, int(NOW))
        result = self._call(body, header)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_json")

    def test_non_dict_event_returns_400(self):
        body = b"[1, 2, 3]"
        header = _header(body, SECRET, int(NOW))
        result = self._call(body, header)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_event")

    def test_valid_subscription_deleted_returns_200_and_marks_candidate(self):
        body = (
            b'{"id":"evt_1","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        header = _header(body, SECRET, int(NOW))
        result = self._call(body, header)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.marked_user_ids, ["user_1"])
        self.assertIsNotNone(self.store.get_deletion_candidate_at("user_1"))

    def test_unresolved_customer_still_returns_200(self):
        body = (
            b'{"id":"evt_1","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_unknown"}}}'
        )
        header = _header(body, SECRET, int(NOW))
        result = self._call(body, header)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.unresolved_customers, ["cus_unknown"])


class HandleCheckoutSessionCompletedTest(unittest.TestCase):
    """stripe-customer-id-linking-design.md 3節。"""

    def setUp(self):
        self.store = InMemoryUserProfileStore()

    def test_valid_event_links_customer_id_to_user_id(self):
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {"client_reference_id": "U1", "customer": "cus_A"}
            },
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertTrue(result.linked)
        self.assertEqual(result.user_id, "U1")
        self.assertEqual(result.stripe_customer_id, "cus_A")
        self.assertEqual(self.store.get_user_id_by_stripe_customer_id("cus_A"), "U1")

    def test_missing_client_reference_id_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)
        self.assertIsNone(self.store.get_user_id_by_stripe_customer_id("cus_A"))

    def test_missing_customer_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "U1"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)

    def test_empty_string_client_reference_id_does_not_link(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "", "customer": "cus_A"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)


class MakeResolveUserIdTest(unittest.TestCase):
    def test_returns_callable_backed_by_store(self):
        store = InMemoryUserProfileStore()
        store.set_stripe_customer_id("U1", "cus_A")
        resolve_user_id = make_resolve_user_id(store)
        self.assertEqual(resolve_user_id("cus_A"), "U1")
        self.assertIsNone(resolve_user_id("cus_unknown"))


class ReceiveStripeWebhookCheckoutSessionTest(unittest.TestCase):
    """receive_stripe_webhook()のcheckout.session.completed振り分け
    (stripe-customer-id-linking-design.md 3節)。"""

    def setUp(self):
        self.deletion_store = InMemoryProfileDeletionCandidateStore()
        self.user_profile_store = InMemoryUserProfileStore()
        self.now = datetime(2026, 8, 23, tzinfo=timezone.utc)

    def _call(self, body: bytes, header: str, *, user_profile_store=None):
        return receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=self.deletion_store,
            resolve_user_id=lambda _customer: None,
            user_profile_store=user_profile_store,
            now=self.now,
        )

    def test_checkout_session_completed_links_and_returns_200(self):
        body = (
            b'{"id":"evt_1","type":"checkout.session.completed",'
            b'"data":{"object":{"client_reference_id":"U1","customer":"cus_A"}}}'
        )
        header = _header(body, SECRET, int(self.now.timestamp()))
        result = self._call(body, header, user_profile_store=self.user_profile_store)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.dispatch_result)
        self.assertTrue(result.checkout_link_result.linked)
        self.assertEqual(
            self.user_profile_store.get_user_id_by_stripe_customer_id("cus_A"), "U1"
        )

    def test_checkout_session_completed_without_user_profile_store_is_noop_200(self):
        body = (
            b'{"id":"evt_1","type":"checkout.session.completed",'
            b'"data":{"object":{"client_reference_id":"U1","customer":"cus_A"}}}'
        )
        header = _header(body, SECRET, int(self.now.timestamp()))
        result = self._call(body, header, user_profile_store=None)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.checkout_link_result.linked)

    def test_subsequent_subscription_event_resolves_via_linked_customer_id(self):
        # checkout.session.completedで紐付けた後、実際のresolve_user_idを使うと
        # customer.subscription.*がその紐付けを引ける(get_stripe_runtime_dependenciesと
        # 同じ配線パターンをテストレベルで確認する)。
        checkout_body = (
            b'{"id":"evt_1","type":"checkout.session.completed",'
            b'"data":{"object":{"client_reference_id":"U1","customer":"cus_A"}}}'
        )
        checkout_header = _header(checkout_body, SECRET, int(self.now.timestamp()))
        receive_stripe_webhook(
            checkout_body,
            checkout_header,
            SECRET,
            store=self.deletion_store,
            resolve_user_id=lambda _customer: None,
            user_profile_store=self.user_profile_store,
            now=self.now,
        )

        subscription_body = (
            b'{"id":"evt_2","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        subscription_header = _header(
            subscription_body, SECRET, int(self.now.timestamp())
        )
        result = receive_stripe_webhook(
            subscription_body,
            subscription_header,
            SECRET,
            store=self.deletion_store,
            resolve_user_id=make_resolve_user_id(self.user_profile_store),
            user_profile_store=self.user_profile_store,
            now=self.now,
        )
        self.assertEqual(result.dispatch_result.marked_user_ids, ["U1"])


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (LINE版test_cloud_function_webhook._StubFlaskRequestと対称)。"""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    def get_data(self) -> bytes:
        return self._body


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント、Stripe版)のテスト。
    stripe-webhook-cloud-function-entry-point-design.mdで設計した、実リクエスト
    オブジェクトからのbody・Stripe-Signatureヘッダ取り出し配線を検証する
    (receive_stripe_webhook()自体の分岐はReceiveStripeWebhookTestで既にカバー済み)。"""

    ENV_SECRET = "demo-webhook-secret"

    def _signed_header(self, body: bytes, secret: str) -> str:
        timestamp = int(time.time())
        return _header(body, secret, timestamp)

    def setUp(self):
        self._original_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        os.environ["STRIPE_WEBHOOK_SECRET"] = self.ENV_SECRET

    def tearDown(self):
        if self._original_secret is None:
            os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        else:
            os.environ["STRIPE_WEBHOOK_SECRET"] = self._original_secret

    def test_valid_request_extracts_body_and_signature_and_returns_200(self):
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubFlaskRequest(
            body, {"Stripe-Signature": self._signed_header(body, self.ENV_SECRET)}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 200)
        self.assertEqual(response_body, "OK")

    def test_invalid_signature_returns_401_with_error_body(self):
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubFlaskRequest(body, {"Stripe-Signature": "t=1,v1=invalid"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)
        self.assertEqual(response_body, "invalid_signature")

    def test_missing_signature_header_returns_401(self):
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubFlaskRequest(body, {})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)

    def test_missing_webhook_secret_env_returns_401(self):
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubFlaskRequest(
            body, {"Stripe-Signature": self._signed_header(body, self.ENV_SECRET)}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)

    def test_get_stripe_runtime_dependencies_output_is_accepted_by_receive_stripe_webhook(self):
        body = (
            b'{"id":"evt_1","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        header = self._signed_header(body, self.ENV_SECRET)

        result = receive_stripe_webhook(
            body, header, self.ENV_SECRET, **get_stripe_runtime_dependencies()
        )

        self.assertEqual(result.status_code, 200)
        # resolve_user_idが常にNoneを返す暫定実装のため、unresolved_customersとして扱われる。
        self.assertEqual(result.dispatch_result.unresolved_customers, ["cus_A"])


if __name__ == "__main__":
    unittest.main()
