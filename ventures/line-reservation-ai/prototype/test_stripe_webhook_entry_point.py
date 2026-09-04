#!/usr/bin/env python3
"""stripe_webhook_entry_point.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_stripe_webhook_entry_point -v で実行可能。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import datetime, timezone

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError
from cloud_function_send_dunning_notifications import StoreDunningState
from cloud_function_subscription_activated_webhook import StoreSubscriptionState
from cloud_function_subscription_cancelled_webhook import (
    StoreSubscriptionState as StoreCancellationState,
)
from dunning_notification_scheduler import DUNNING_CONFIG_A_7DAYS
from stripe_webhook import InMemoryStripeEventIdStore
from stripe_webhook_entry_point import (
    InMemoryStoreCancellationStateStore,
    InMemoryStoreDunningStateStore,
    InMemoryStoreSubscriptionStateStore,
    get_stripe_webhook_runtime_dependencies,
    main,
    receive_stripe_webhook,
)

SECRET = "whsec_test_secret"
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)


def _sign(payload: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def _header(payload: bytes, secret: str, timestamp: int) -> str:
    return f"t={timestamp},v1={_sign(payload, secret, timestamp)}"


def _event_payload(event_id: str, event_type: str, data_object: dict) -> bytes:
    return json.dumps(
        {"id": event_id, "type": event_type, "data": {"object": data_object}}
    ).encode("utf-8")


def _event_payload_with_previous(
    event_id: str, event_type: str, data_object: dict, previous_attributes: dict
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": event_type,
            "data": {"object": data_object, "previous_attributes": previous_attributes},
        }
    ).encode("utf-8")


def _resolve_by_customer(customer_id: str):
    return {"cus_1": "store-1"}.get(customer_id)


class ReceiveStripeWebhookSignatureAndParsingTest(unittest.TestCase):
    def test_invalid_signature_returns_401(self):
        payload = _event_payload("evt_1", "checkout.session.completed", {})
        result = receive_stripe_webhook(
            payload,
            "t=1,v1=deadbeef",
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            now=NOW,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_signature")

    def test_invalid_json_returns_400(self):
        payload = b"not-json"
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            now=NOW,
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_json")

    def test_ignored_event_type_returns_200_without_handler_call(self):
        payload = _event_payload("evt_1", "customer.updated", {})
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            now=NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.route.ignored)

    def test_unresolved_store_id_returns_200_without_handler_call(self):
        payload = _event_payload(
            "evt_1", "invoice.payment_succeeded", {"customer": "cus_unknown"}
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            now=NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.route.unresolved_customer)


class ReceiveStripeWebhookDuplicateTest(unittest.TestCase):
    def test_duplicate_event_skips_all_processing(self):
        event_id_store = InMemoryStripeEventIdStore()
        payload = _event_payload(
            "evt_1", "invoice.payment_succeeded", {"customer": "cus_1"}
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        first = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            event_id_store=event_id_store,
            now=NOW,
        )
        self.assertFalse(first.duplicate)

        second = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            event_id_store=event_id_store,
            now=NOW,
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.duplicate)


class ReceiveStripeWebhookSubscriptionActivatedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.subscription_store = InMemoryStoreSubscriptionStateStore()
        self.subscription_store.set_subscription_state(
            "store-1",
            StoreSubscriptionState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                plan_name="スタンダードプラン",
                next_billing_date="2026-10-03",
                portal_url="https://example.com/portal",
                suspension_reason="trial_unselected",
            ),
        )
        self.push_client = InMemoryLinePushClient()

    def _send(self):
        payload = _event_payload(
            "evt_1",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_1"},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        return receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            subscription_store=self.subscription_store,
            push_client=self.push_client,
            now=NOW,
        )

    def test_handler_is_called_and_state_is_written_back(self):
        result = self._send()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "activated")
        self.assertEqual(len(self.push_client.sent), 1)
        stored = self.subscription_store.get_subscription_state("store-1")
        self.assertIsNone(stored.suspension_reason)

    def test_skipped_when_subscription_store_missing(self):
        payload = _event_payload(
            "evt_1",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_1"},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            push_client=self.push_client,
            now=NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)
        self.assertEqual(len(self.push_client.sent), 0)

    def test_skipped_when_push_client_missing(self):
        payload = _event_payload(
            "evt_1",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_1"},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            subscription_store=self.subscription_store,
            now=NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)

    def test_skipped_when_store_id_has_no_known_state(self):
        payload = _event_payload(
            "evt_1",
            "checkout.session.completed",
            {"client_reference_id": "store-unknown", "customer": "cus_1"},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            subscription_store=self.subscription_store,
            push_client=self.push_client,
            now=NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)
        self.assertEqual(len(self.push_client.sent), 0)

    def test_send_failure_leaves_state_unchanged(self):
        class FailingPushClient:
            def send_message(self, user_id, text):
                raise LinePushDeliveryError()

        payload = _event_payload(
            "evt_1",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_1"},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            subscription_store=self.subscription_store,
            push_client=FailingPushClient(),
            now=NOW,
        )
        self.assertEqual(result.outcome, "send_failed")
        stored = self.subscription_store.get_subscription_state("store-1")
        self.assertEqual(stored.suspension_reason, "trial_unselected")


class ReceiveStripeWebhookPaymentSucceededTest(unittest.TestCase):
    def test_handler_is_called_and_state_is_written_back(self):
        dunning_store = InMemoryStoreDunningStateStore()
        dunning_store.set_dunning_state(
            "store-1",
            StoreDunningState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                payment_failure_detected_at=datetime(2026, 8, 17, 10, 0),
                config=DUNNING_CONFIG_A_7DAYS,
                payment_page_url="https://example.com/billing",
                suspension_reason="payment_failed",
                sent_event_keys={"detected", "reminder:final", "suspended"},
            ),
        )
        push_client = InMemoryLinePushClient()
        payload = _event_payload(
            "evt_1", "invoice.payment_succeeded", {"customer": "cus_1"}
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            dunning_store=dunning_store,
            push_client=push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "recovered_from_suspension")
        self.assertEqual(len(push_client.sent), 1)
        stored = dunning_store.get_dunning_state("store-1")
        self.assertIsNone(stored.suspension_reason)


class ReceiveStripeWebhookPaymentFailedTest(unittest.TestCase):
    def test_handler_is_called_without_push_client(self):
        dunning_store = InMemoryStoreDunningStateStore()
        dunning_store.set_dunning_state(
            "store-1",
            StoreDunningState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                payment_failure_detected_at=None,
                config=DUNNING_CONFIG_A_7DAYS,
                payment_page_url="https://example.com/billing",
            ),
        )
        payload = _event_payload(
            "evt_1", "invoice.payment_failed", {"customer": "cus_1"}
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            dunning_store=dunning_store,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "True")
        stored = dunning_store.get_dunning_state("store-1")
        self.assertEqual(stored.payment_failure_detected_at, NOW)

    def test_skipped_when_dunning_store_missing(self):
        payload = _event_payload(
            "evt_1", "invoice.payment_failed", {"customer": "cus_1"}
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)


class ReceiveStripeWebhookSubscriptionDeletedTest(unittest.TestCase):
    """subscription-deleted-event-routing-design.mdで追加した
    `customer.subscription.deleted`のディスパッチ(専用の`cancellation_store`経由)を、
    `ReceiveStripeWebhookSubscriptionActivatedTest`と同型の観点で確認する。"""

    def setUp(self) -> None:
        self.cancellation_store = InMemoryStoreCancellationStateStore()
        self.cancellation_store.set_cancellation_state(
            "store-1",
            StoreCancellationState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                plan_name="スタンダードプラン",
                period_end_date="2026-09-14",
                portal_url="https://example.com/portal",
                suspension_reason=None,
            ),
        )
        self.push_client = InMemoryLinePushClient()

    def _payload(self):
        return _event_payload(
            "evt_1", "customer.subscription.deleted", {"customer": "cus_1"}
        )

    def test_handler_is_called_and_state_is_written_back(self):
        payload = self._payload()
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            cancellation_store=self.cancellation_store,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(len(self.push_client.sent), 1)
        stored = self.cancellation_store.get_cancellation_state("store-1")
        self.assertEqual(stored.suspension_reason, "cancelled")

    def test_skipped_when_cancellation_store_missing(self):
        payload = self._payload()
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)
        self.assertEqual(len(self.push_client.sent), 0)

    def test_skipped_when_push_client_missing(self):
        payload = self._payload()
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            cancellation_store=self.cancellation_store,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)

    def test_skipped_when_store_id_has_no_known_state(self):
        payload = _event_payload(
            "evt_1", "customer.subscription.deleted", {"customer": "cus_unknown_store"}
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        def resolve(customer_id):
            return {"cus_unknown_store": "store-unknown"}.get(customer_id)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=resolve,
            cancellation_store=self.cancellation_store,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)
        self.assertEqual(len(self.push_client.sent), 0)

    def test_send_failure_leaves_state_unchanged(self):
        class FailingPushClient:
            def send_message(self, user_id, text):
                raise LinePushDeliveryError()

        payload = self._payload()
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            cancellation_store=self.cancellation_store,
            push_client=FailingPushClient(),
            now=NOW,
        )

        self.assertEqual(result.outcome, "send_failed")
        stored = self.cancellation_store.get_cancellation_state("store-1")
        self.assertIsNone(stored.suspension_reason)


class ReceiveStripeWebhookSubscriptionUpdatedTest(unittest.TestCase):
    """customer-subscription-updated-event-routing-design.mdで追加した
    `customer.subscription.updated`のディスパッチ(`cancellation_store`経由・書き戻し無し)
    を確認する。"""

    def setUp(self) -> None:
        self.cancellation_store = InMemoryStoreCancellationStateStore()
        self.cancellation_store.set_cancellation_state(
            "store-1",
            StoreCancellationState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                plan_name="スタンダードプラン",
                period_end_date="2026-09-14",
                portal_url="https://example.com/portal",
                suspension_reason=None,
            ),
        )
        self.push_client = InMemoryLinePushClient()

    def test_cancellation_scheduled_notifies_and_does_not_change_state(self):
        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {"customer": "cus_1", "cancel_at_period_end": True},
            {"cancel_at_period_end": False},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            cancellation_store=self.cancellation_store,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "cancellation_scheduled")
        self.assertEqual(len(self.push_client.sent), 1)
        stored = self.cancellation_store.get_cancellation_state("store-1")
        self.assertIsNone(stored.suspension_reason)

    def test_unrelated_field_change_is_no_change_and_no_notification(self):
        # previous_attributesにcancel_at_period_endが含まれない
        # (=このイベントで変化したのは別フィールド)場合はbefore==afterとして扱う。
        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {"customer": "cus_1", "cancel_at_period_end": False},
            {"default_payment_method": "pm_new"},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            cancellation_store=self.cancellation_store,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "no_change")
        self.assertEqual(len(self.push_client.sent), 0)

    def test_skipped_when_cancellation_store_missing(self):
        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {"customer": "cus_1", "cancel_at_period_end": True},
            {"cancel_at_period_end": False},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)
        self.assertEqual(len(self.push_client.sent), 0)

    def test_skipped_when_store_id_has_no_known_state(self):
        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {"customer": "cus_unknown_store", "cancel_at_period_end": True},
            {"cancel_at_period_end": False},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        def resolve(customer_id):
            return {"cus_unknown_store": "store-unknown"}.get(customer_id)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=resolve,
            cancellation_store=self.cancellation_store,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.outcome)
        self.assertEqual(len(self.push_client.sent), 0)

    def test_send_failure_leaves_state_unchanged(self):
        class FailingPushClient:
            def send_message(self, user_id, text):
                raise LinePushDeliveryError()

        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {"customer": "cus_1", "cancel_at_period_end": True},
            {"cancel_at_period_end": False},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            cancellation_store=self.cancellation_store,
            push_client=FailingPushClient(),
            now=NOW,
        )

        self.assertEqual(result.outcome, "send_failed")
        stored = self.cancellation_store.get_cancellation_state("store-1")
        self.assertIsNone(stored.suspension_reason)


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (course-set-pasha/test_stripe_webhook.py._StubFlaskRequestと対称)。"""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    def get_data(self) -> bytes:
        return self._body


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント、design 8節)のテスト。
    実リクエストオブジェクトからのbody・Stripe-Signatureヘッダ取り出し配線を検証する
    (receive_stripe_webhook()自体の分岐は上記各Testクラスで既にカバー済み)。"""

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

    def test_get_stripe_webhook_runtime_dependencies_output_is_accepted_by_receive_stripe_webhook(
        self,
    ):
        body = (
            b'{"id":"evt_1","type":"customer.subscription.deleted",'
            b'"data":{"object":{"customer":"cus_A"}}}'
        )
        header = self._signed_header(body, self.ENV_SECRET)

        result = receive_stripe_webhook(
            body, header, self.ENV_SECRET, **get_stripe_webhook_runtime_dependencies()
        )

        self.assertEqual(result.status_code, 200)


if __name__ == "__main__":
    unittest.main()
