import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import datetime, timezone

from deletion_candidate import InMemoryProfileDeletionCandidateStore
from payment_failure import InMemoryLinePushClient, LinePushDeliveryError
from payment_recovery_notification import (
    InMemoryLinePushClient as InMemoryRecoveryPushClient,
    LinePushDeliveryError as RecoveryLinePushDeliveryError,
)
from stripe_webhook import (
    get_stripe_runtime_dependencies,
    handle_checkout_session_completed,
    main,
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

        result = handle_checkout_session_completed(event, store, now=NOW_DT)

        self.assertTrue(result.linked)
        self.assertEqual(result.user_id, "user_1")
        self.assertEqual(result.stripe_customer_id, "cus_1")
        self.assertEqual(store.get("user_1").stripe_customer_id, "cus_1")
        self.assertTrue(result.upgraded_at_written)
        self.assertEqual(store.get("user_1").upgraded_at, NOW_DT)

    def test_upgraded_at_defaults_to_current_time_when_now_omitted(self):
        store = InMemoryUserProfileStore()
        _seed_profile(store, "user_1")
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "user_1", "customer": "cus_1"}},
        }

        result = handle_checkout_session_completed(event, store)

        self.assertTrue(result.upgraded_at_written)
        self.assertIsNotNone(store.get("user_1").upgraded_at)

    def test_already_upgraded_user_does_not_overwrite_upgraded_at(self):
        """upgraded_atは有料転換時に1回だけ書き込むフィールド(UserProfile docstring)
        であり、Stripeの再送等で同一イベントが複数回届いても最初の転換日時を保持する。"""
        store = InMemoryUserProfileStore()
        _seed_profile(store, "user_1")
        earlier = datetime.fromtimestamp(NOW - 1000, tz=timezone.utc)
        store.set_upgraded_at("user_1", earlier)
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "user_1", "customer": "cus_1"}},
        }

        result = handle_checkout_session_completed(event, store, now=NOW_DT)

        self.assertTrue(result.linked)
        self.assertFalse(result.upgraded_at_written)
        self.assertEqual(store.get("user_1").upgraded_at, earlier)

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
        self.assertTrue(result.checkout_link_result.upgraded_at_written)
        self.assertEqual(profile_store.get("user_1").upgraded_at, NOW_DT)

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


def _payment_profile_store(user_id="user_1") -> InMemoryUserProfileStore:
    store = InMemoryUserProfileStore()
    _seed_profile(store, user_id)
    return store


class ReceiveStripeWebhookPaymentFailureWiringTest(unittest.TestCase):
    """フェーズ149: `dispatch_stripe_event()`は`invoice.payment_failed`/
    `invoice.payment_succeeded`をpayment_store/push_client/recovery_push_client
    経由で処理できる設計(フェーズ140・147・148)だが、`receive_stripe_webhook()`が
    これらを委譲していなかった配線漏れを解消したことの確認。"""

    def test_payment_failed_ignored_without_payment_store(self):
        """後方互換: payment_store省略時はこれまで通りignored_typesに落ちる。"""
        store, resolve_user_id = _make_store_and_resolver({"cus_1": "user_1"})
        event = {
            "type": "invoice.payment_failed",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body, header, SECRET, store=store, resolve_user_id=resolve_user_id, now=NOW_DT
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.ignored_types, ["invoice.payment_failed"])
        self.assertEqual(result.dispatch_result.payment_failure_detected_user_ids, [])

    def test_payment_failed_marks_state_when_payment_store_provided(self):
        store, _ = _make_store_and_resolver()
        payment_store = _payment_profile_store("user_1")
        resolve_user_id = make_resolve_user_id(payment_store)
        payment_store.set_stripe_customer_id("user_1", "cus_1")
        event = {
            "type": "invoice.payment_failed",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            payment_store=payment_store,
            now=NOW_DT,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            result.dispatch_result.payment_failure_detected_user_ids, ["user_1"]
        )
        self.assertEqual(payment_store.get_payment_failure_detected_at("user_1"), NOW_DT)

    def test_payment_failed_sends_notification_when_push_client_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _payment_profile_store("user_1")
        resolve_user_id = make_resolve_user_id(payment_store)
        payment_store.set_stripe_customer_id("user_1", "cus_1")
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_failed",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            payment_store=payment_store,
            push_client=push_client,
            now=NOW_DT,
        )

        self.assertEqual(
            result.dispatch_result.payment_failure_detected_user_ids, ["user_1"]
        )
        self.assertEqual(len(push_client.sent), 1)
        self.assertEqual(push_client.sent[0][0], "user_1")

    def test_payment_failed_notification_failure_leaves_state_unwritten(self):
        class _FailingPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise LinePushDeliveryError("boom")

        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _payment_profile_store("user_1")
        resolve_user_id = make_resolve_user_id(payment_store)
        payment_store.set_stripe_customer_id("user_1", "cus_1")
        event = {
            "type": "invoice.payment_failed",
            "created": int(NOW),
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            payment_store=payment_store,
            push_client=_FailingPushClient(),
            now=NOW_DT,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            result.dispatch_result.payment_failure_notification_failed_user_ids,
            ["user_1"],
        )
        self.assertIsNone(payment_store.get_payment_failure_detected_at("user_1"))

    def test_payment_succeeded_clears_state_when_payment_store_provided(self):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _payment_profile_store("user_1")
        resolve_user_id = make_resolve_user_id(payment_store)
        payment_store.set_stripe_customer_id("user_1", "cus_1")
        payment_store.set_payment_failure_detected_at("user_1", NOW_DT)
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            payment_store=payment_store,
            now=NOW_DT,
        )

        self.assertEqual(result.dispatch_result.payment_recovered_user_ids, ["user_1"])
        self.assertIsNone(payment_store.get_payment_failure_detected_at("user_1"))

    def test_payment_succeeded_sends_recovery_notification_when_recovery_push_client_provided(
        self,
    ):
        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _payment_profile_store("user_1")
        resolve_user_id = make_resolve_user_id(payment_store)
        payment_store.set_stripe_customer_id("user_1", "cus_1")
        payment_store.set_payment_suspended_at("user_1", NOW_DT)
        payment_store.set_payment_failure_detected_at("user_1", NOW_DT)
        recovery_push_client = InMemoryRecoveryPushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            payment_store=payment_store,
            recovery_push_client=recovery_push_client,
            now=NOW_DT,
        )

        self.assertEqual(result.dispatch_result.payment_recovered_user_ids, ["user_1"])
        self.assertEqual(len(recovery_push_client.sent), 1)
        self.assertEqual(recovery_push_client.sent[0][0], "user_1")
        self.assertIsNone(payment_store.get_payment_suspended_at("user_1"))

    def test_payment_succeeded_recovery_notification_failure_leaves_state_unchanged(self):
        class _FailingRecoveryPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise RecoveryLinePushDeliveryError("boom")

        store = InMemoryProfileDeletionCandidateStore()
        payment_store = _payment_profile_store("user_1")
        resolve_user_id = make_resolve_user_id(payment_store)
        payment_store.set_stripe_customer_id("user_1", "cus_1")
        payment_store.set_payment_suspended_at("user_1", NOW_DT)
        payment_store.set_payment_failure_detected_at("user_1", NOW_DT)
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_1"}},
        }
        body = json.dumps(event).encode("utf-8")
        header = _header(body, SECRET, int(NOW))

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            payment_store=payment_store,
            recovery_push_client=_FailingRecoveryPushClient(),
            now=NOW_DT,
        )

        self.assertEqual(
            result.dispatch_result.payment_recovery_notification_failed_user_ids,
            ["user_1"],
        )
        self.assertIsNotNone(payment_store.get_payment_suspended_at("user_1"))


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (course-set-pasha/prototype/test_stripe_webhook.py `_StubFlaskRequest`と対称)。"""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    def get_data(self) -> bytes:
        return self._body


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント、Stripe版)のテスト。
    stripe-webhook-http-entry-point-design.md「残課題」で未着手のまま残っていた、
    実リクエストオブジェクトからのbody・Stripe-Signatureヘッダ取り出し配線を検証する
    (receive_stripe_webhook()自体の分岐は他のテストクラスで既にカバー済み)。"""

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

    def test_get_stripe_runtime_dependencies_output_is_accepted_by_receive_stripe_webhook(
        self,
    ):
        body = (
            b'{"id":"evt_1","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        header = self._signed_header(body, self.ENV_SECRET)

        result = receive_stripe_webhook(
            body, header, self.ENV_SECRET, **get_stripe_runtime_dependencies()
        )

        self.assertEqual(result.status_code, 200)
        # cus_Aはcheckout.session.completedで一度も紐付けられていないため未解決のまま。
        self.assertEqual(result.dispatch_result.unresolved_customers, ["cus_A"])


class GetStripeRuntimeDependenciesResolutionTest(unittest.TestCase):
    """get_stripe_runtime_dependencies()が返すresolve_user_id・payment_storeが、
    checkout.session.completedで書き込んだ紐付け・決済失敗状態を実際に読み書きできる
    ことを検証する(course-set-pashaのGetStripeRuntimeDependenciesResolutionTestと
    同じ回帰防止の位置づけ)。同一の戻り値(=同一プロセス内のInMemoryUserProfileStore)を
    使い回した場合に限り状態が引き継がれる。"""

    ENV_SECRET = "demo-webhook-secret"

    def _signed_header(self, body: bytes, secret: str) -> str:
        timestamp = int(time.time())
        return _header(body, secret, timestamp)

    def test_checkout_link_is_resolved_by_subsequent_subscription_event(self):
        deps = get_stripe_runtime_dependencies()
        deps["user_profile_store"].save(
            "U1",
            UserProfile(
                business_name="テスト事業者",
                business_type="独立系",
                email="u1@example.com",
                linked_at=NOW_DT,
            ),
        )

        checkout_body = json.dumps(
            {
                "id": "evt_checkout",
                "type": "checkout.session.completed",
                "data": {
                    "object": {"client_reference_id": "U1", "customer": "cus_A"}
                },
            }
        ).encode("utf-8")
        checkout_result = receive_stripe_webhook(
            checkout_body,
            self._signed_header(checkout_body, self.ENV_SECRET),
            self.ENV_SECRET,
            **deps,
        )
        self.assertEqual(checkout_result.status_code, 200)
        self.assertTrue(checkout_result.checkout_link_result.linked)

        subscription_body = (
            b'{"id":"evt_sub","type":"invoice.payment_failed",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        subscription_result = receive_stripe_webhook(
            subscription_body,
            self._signed_header(subscription_body, self.ENV_SECRET),
            self.ENV_SECRET,
            **deps,
        )

        self.assertEqual(subscription_result.status_code, 200)
        self.assertEqual(subscription_result.dispatch_result.unresolved_customers, [])
        # 紐付けが解決され、同じuser_profile_storeインスタンス(=payment_store)に
        # 決済失敗検知状態が書き込まれる。
        self.assertIsNotNone(deps["user_profile_store"].get_payment_failure_detected_at("U1"))

    def test_two_separate_calls_do_not_share_state(self):
        checkout_body = json.dumps(
            {
                "id": "evt_checkout",
                "type": "checkout.session.completed",
                "data": {
                    "object": {"client_reference_id": "U1", "customer": "cus_A"}
                },
            }
        ).encode("utf-8")
        receive_stripe_webhook(
            checkout_body,
            self._signed_header(checkout_body, self.ENV_SECRET),
            self.ENV_SECRET,
            **get_stripe_runtime_dependencies(),
        )

        subscription_body = (
            b'{"id":"evt_sub","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        subscription_result = receive_stripe_webhook(
            subscription_body,
            self._signed_header(subscription_body, self.ENV_SECRET),
            self.ENV_SECRET,
            **get_stripe_runtime_dependencies(),
        )

        self.assertEqual(
            subscription_result.dispatch_result.unresolved_customers, ["cus_A"]
        )


if __name__ == "__main__":
    unittest.main()
