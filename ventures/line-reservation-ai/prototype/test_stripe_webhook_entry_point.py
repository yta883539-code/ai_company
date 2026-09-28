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
from portal_session import InMemoryPortalLinkProvider
from store_profile_store import InMemoryStoreProfileStore
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


def _event_payload_with_created(
    event_id: str, event_type: str, data_object: dict, created: int
) -> bytes:
    return json.dumps(
        {"id": event_id, "type": event_type, "data": {"object": data_object}, "created": created}
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


def _event_payload_with_created_and_previous(
    event_id: str,
    event_type: str,
    data_object: dict,
    previous_attributes: dict,
    created: int,
) -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "type": event_type,
            "data": {"object": data_object, "previous_attributes": previous_attributes},
            "created": created,
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

    def test_portal_link_provider_resolves_url_into_message(self):
        # portal-session-provider-design.md 4節3.: providerが渡された場合のみ都度解決する。
        result = receive_stripe_webhook(
            *self._signed_payload(),
            resolve_store_id_by_customer=_resolve_by_customer,
            subscription_store=self.subscription_store,
            push_client=self.push_client,
            portal_link_provider=InMemoryPortalLinkProvider("https://example.test/portal"),
            now=NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIn("https://example.test/portal", self.push_client.sent[0][1])

    def test_omitted_portal_link_provider_falls_back_to_no_portal_line(self):
        result = self._send()
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("マイページ", self.push_client.sent[0][1])

    def _signed_payload(self):
        payload = _event_payload(
            "evt_1",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_1"},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        return payload, header, SECRET

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

    def test_stale_event_is_skipped_without_reverting_cancellation(self):
        # フェーズ続き282が「次回候補」に残していた、route_stripe_event()から
        # handle_subscription_activated()へのevent_time配線の検証(subscription-event-
        # order-guard-design.md)。解約確定後に、それより前に発生していたが遅延配信された
        # checkout.session.completedが届いても、既にcancelled済みの状態を誤って
        # 解除してはならない。
        state = self.subscription_store.get_subscription_state("store-1")
        state.suspension_reason = "cancelled"
        state.last_subscription_event_time = datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc)

        payload = _event_payload_with_created(
            "evt_1",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_1"},
            int(datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc).timestamp()),
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
        self.assertEqual(result.outcome, "stale_event")
        self.assertEqual(len(self.push_client.sent), 0)
        stored = self.subscription_store.get_subscription_state("store-1")
        self.assertEqual(stored.suspension_reason, "cancelled")


class ReceiveStripeWebhookCheckoutSessionCompletedProfileLinkingTest(unittest.TestCase):
    """checkout-initiation-flow-design.md 7節: `checkout.session.completed`受信時に
    `store_profile_store.handle_checkout_session_completed()`が呼ばれ、
    stripe_customer_id・plan が実際に書き込まれることを検証する(この配線が
    抜けていたため、統合エントリポイント経由では一度も呼ばれていなかった)。"""

    def _payload(self, metadata: dict | None = None) -> bytes:
        data_object = {"client_reference_id": "store-1", "customer": "cus_1"}
        if metadata is not None:
            data_object["metadata"] = metadata
        return _event_payload("evt_1", "checkout.session.completed", data_object)

    def _send(self, *, store_profile_store, **kwargs):
        payload = self._payload(kwargs.pop("metadata", None))
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)
        return receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            store_profile_store=store_profile_store,
            now=NOW,
            **kwargs,
        )

    def test_stripe_customer_id_is_linked_even_without_subscription_store_or_push_client(self):
        store = InMemoryStoreProfileStore()
        result = self._send(store_profile_store=store)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_1")

    def test_plan_metadata_is_written_when_known(self):
        store = InMemoryStoreProfileStore()
        self._send(store_profile_store=store, metadata={"plan": "スタンダードプラン"})
        self.assertEqual(store.get_plan("store-1"), "スタンダードプラン")

    def test_unknown_plan_metadata_is_not_written(self):
        store = InMemoryStoreProfileStore()
        self._send(store_profile_store=store, metadata={"plan": "存在しないプラン"})
        self.assertIsNone(store.get_plan("store-1"))

    def test_stale_checkout_session_completed_does_not_overwrite_newer_customer_id(self):
        # checkout-session-completed-event-order-guard-design.md: 統合エントリポイント
        # 経由でもevent_timeが実際に渡り、古いイベントが新しい書き込みを上書きしない
        # ことを確認する(subscription_activated/deleted側の配線確認と同じ観点)。
        store = InMemoryStoreProfileStore()

        newer_payload = _event_payload_with_created(
            "evt_new",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_new"},
            int(datetime(2026, 9, 28, 5, 0, tzinfo=timezone.utc).timestamp()),
        )
        timestamp = int(NOW.timestamp())
        receive_stripe_webhook(
            newer_payload,
            _header(newer_payload, SECRET, timestamp),
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            store_profile_store=store,
            now=NOW,
        )

        stale_payload = _event_payload_with_created(
            "evt_old",
            "checkout.session.completed",
            {"client_reference_id": "store-1", "customer": "cus_old"},
            int(datetime(2026, 9, 28, 4, 0, tzinfo=timezone.utc).timestamp()),
        )
        result = receive_stripe_webhook(
            stale_payload,
            _header(stale_payload, SECRET, timestamp),
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            store_profile_store=store,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_new")

    def test_skipped_without_error_when_store_profile_store_omitted(self):
        payload = self._payload()
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

    def test_linking_still_happens_alongside_subscription_activation(self):
        # 通知送信(subscription_store/push_client)とprofile linkingが両立することを確認する。
        store = InMemoryStoreProfileStore()
        subscription_store = InMemoryStoreSubscriptionStateStore()
        subscription_store.set_subscription_state(
            "store-1",
            StoreSubscriptionState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                plan_name="スタンダードプラン",
                next_billing_date="2026-10-03",
                suspension_reason="trial_unselected",
            ),
        )
        push_client = InMemoryLinePushClient()
        result = self._send(
            store_profile_store=store,
            subscription_store=subscription_store,
            push_client=push_client,
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "activated")
        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_1")


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

    def test_stale_event_is_skipped_without_reverting_reactivation(self):
        # フェーズ続き282が「次回候補」に残していた、route_stripe_event()から
        # handle_subscription_deleted()へのevent_time配線の検証(subscription-event-
        # order-guard-design.md)。解約直後に即再契約した場合、それより前に発生していたが
        # 遅延配信されたcustomer.subscription.deletedが届いても、既に有効な契約を誤って
        # cancelledへ書き換えてはならない。
        state = self.cancellation_store.get_cancellation_state("store-1")
        state.suspension_reason = None
        state.last_subscription_event_time = datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc)

        payload = _event_payload_with_created(
            "evt_1",
            "customer.subscription.deleted",
            {"customer": "cus_1"},
            int(datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc).timestamp()),
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
        self.assertEqual(result.outcome, "stale_event")
        self.assertEqual(len(self.push_client.sent), 0)
        stored = self.cancellation_store.get_cancellation_state("store-1")
        self.assertIsNone(stored.suspension_reason)

    def test_stale_event_does_not_set_store_profile_store_suspension_reason(self):
        # subscription-event-order-guard-design.md 6節(2026-09-28定例更新)。
        # test_stale_event_is_skipped_without_reverting_reactivationと同じstaleな
        # customer.subscription.deletedを、store_profile_storeも渡して受信した場合、
        # cancellation_store側だけでなくstore_profile_store側のsuspension_reasonも
        # "cancelled"へ書き換えてはならない(以前はcancellation_store側のstale判定と
        # 無関係に無条件で書き換えていた非対称)。
        state = self.cancellation_store.get_cancellation_state("store-1")
        state.suspension_reason = None
        state.last_subscription_event_time = datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc)
        store_profile_store = InMemoryStoreProfileStore()

        payload = _event_payload_with_created(
            "evt_1",
            "customer.subscription.deleted",
            {"customer": "cus_1"},
            int(datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc).timestamp()),
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
            store_profile_store=store_profile_store,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "stale_event")
        self.assertIsNone(store_profile_store.get_suspension_reason("store-1"))

    def test_stale_event_does_not_clear_dunning_state(self):
        # 同上、dunning_store側(payment_failure_detected_at・sent_event_keys・
        # suspension_reason)についても同様にstale時はクリアしてはならない。
        state = self.cancellation_store.get_cancellation_state("store-1")
        state.suspension_reason = None
        state.last_subscription_event_time = datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc)
        dunning_store = InMemoryStoreDunningStateStore()
        dunning_store.set_dunning_state(
            "store-1",
            StoreDunningState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                payment_failure_detected_at=datetime(2026, 8, 30, 9, 0),
                config=DUNNING_CONFIG_A_7DAYS,
                payment_page_url="https://example.com/billing",
                suspension_reason=None,
                sent_event_keys={"detected"},
            ),
        )

        payload = _event_payload_with_created(
            "evt_1",
            "customer.subscription.deleted",
            {"customer": "cus_1"},
            int(datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc).timestamp()),
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
            dunning_store=dunning_store,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "stale_event")
        stored = dunning_store.get_dunning_state("store-1")
        self.assertEqual(stored.payment_failure_detected_at, datetime(2026, 8, 30, 9, 0))
        self.assertEqual(stored.sent_event_keys, {"detected"})
        self.assertIsNone(stored.suspension_reason)

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

    def test_store_profile_store_suspension_reason_is_set_independently_of_notification(
        self,
    ):
        """blocked-but-billing-detection-design.md 3節・2節: `store_profile_store`側の
        `suspension_reason`は`list_blocked_but_billing_candidates()`が除外判定に使う
        フィールド(`_EXCLUDED_SUSPENSION_REASONS`に`"cancelled"`を含む)であり、
        checkout.session.completed分岐のhandle_checkout_session_completed()と同じ
        「通知の成否とは独立して書き込む」方針で反映されるべきことを確認する。
        `cancellation_store`/`push_client`を渡さない(=通知は行われない)場合でも
        `store_profile_store`側には`"cancelled"`が書き込まれる。"""
        store_profile_store = InMemoryStoreProfileStore()
        payload = self._payload()
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            store_profile_store=store_profile_store,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            store_profile_store.get_suspension_reason("store-1"), "cancelled"
        )

    def test_omitted_store_profile_store_skips_suspension_reason_write_without_error(
        self,
    ):
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

    def test_dunning_state_is_cleared_independently_of_notification(self):
        """dunning-state-clear-on-subscription-deleted-design.md: 猶予期間中に契約が終了
        すると、`dunning_store`側の`payment_failure_detected_at`・`sent_event_keys`が
        クリアされ`suspension_reason`が`"cancelled"`になることを確認する。
        `store_profile_store`の書き込みと同じく`cancellation_store`/`push_client`の
        要否とは独立して行われる(本テストは両方省略)。"""
        dunning_store = InMemoryStoreDunningStateStore()
        dunning_store.set_dunning_state(
            "store-1",
            StoreDunningState(
                store_id="store-1",
                owner_line_user_id="owner-line-1",
                payment_failure_detected_at=datetime(2026, 8, 30, 9, 0),
                config=DUNNING_CONFIG_A_7DAYS,
                payment_page_url="https://example.com/billing",
                suspension_reason=None,
                sent_event_keys={"detected"},
            ),
        )
        payload = self._payload()
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
        stored = dunning_store.get_dunning_state("store-1")
        self.assertIsNone(stored.payment_failure_detected_at)
        self.assertEqual(stored.sent_event_keys, set())
        self.assertEqual(stored.suspension_reason, "cancelled")

    def test_omitted_dunning_store_skips_clear_without_error(self):
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

    def test_dunning_store_with_no_known_state_for_store_id_is_left_untouched(self):
        dunning_store = InMemoryStoreDunningStateStore()
        payload = self._payload()
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
        self.assertIsNone(dunning_store.get_dunning_state("store-1"))


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

    def test_portal_link_provider_resolves_url_into_message(self):
        # portal-session-provider-design.md 4節3.: providerが渡された場合のみ都度解決する。
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
            portal_link_provider=InMemoryPortalLinkProvider("https://example.test/portal"),
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIn("https://example.test/portal", self.push_client.sent[0][1])

    def test_omitted_portal_link_provider_falls_back_to_reply_in_chat(self):
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
        self.assertIn("トークルーム", self.push_client.sent[0][1])

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

    def test_plan_is_synced_when_store_profile_store_provided(self):
        # subscription-plan-sync-design.md(フェーズ続き220)。
        store_profile_store = InMemoryStoreProfileStore()
        store_profile_store.set_plan("store-1", "スタンダードプラン")
        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {
                "customer": "cus_1",
                "cancel_at_period_end": False,
                "items": {
                    "data": [{"price": {"lookup_key": "line_reservation_ai_pro"}}]
                },
            },
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
            store_profile_store=store_profile_store,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(store_profile_store.get_plan("store-1"), "プロプラン")

    def test_plan_sync_is_independent_of_push_client_and_cancellation_store(self):
        # 通知(cancellation_store/push_client)が未指定・stateが無い場合でも
        # プラン同期自体は行われる。
        store_profile_store = InMemoryStoreProfileStore()
        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {
                "customer": "cus_1",
                "cancel_at_period_end": False,
                "items": {
                    "data": [{"price": {"lookup_key": "line_reservation_ai_starter"}}]
                },
            },
            {},
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            store_profile_store=store_profile_store,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(store_profile_store.get_plan("store-1"), "スタータープラン")

    def test_omitted_store_profile_store_skips_plan_sync_without_error(self):
        payload = _event_payload_with_previous(
            "evt_1",
            "customer.subscription.updated",
            {
                "customer": "cus_1",
                "cancel_at_period_end": False,
                "items": {
                    "data": [{"price": {"lookup_key": "line_reservation_ai_pro"}}]
                },
            },
            {},
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

    # subscription-updated-event-order-guard-design.md準拠(kura-pashaフェーズ198・
    # course-set-pashaの横展開)。

    def test_event_time_is_recorded_when_newer_than_recorded(self):
        payload = _event_payload_with_created_and_previous(
            "evt_1",
            "customer.subscription.updated",
            {"customer": "cus_1", "cancel_at_period_end": True},
            {"cancel_at_period_end": False},
            int(datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc).timestamp()),
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
        self.assertEqual(
            stored.last_subscription_updated_event_time,
            datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc),
        )

    def test_stale_updated_event_skips_plan_sync_and_notification(self):
        # 遅延配信ケース: 既により新しい.updatedイベント(11:00)でplan・解約予約状態が
        # 確定済みの店舗に対し、それより前(10:00)に発生していたはずのイベントが
        # 遅れて届いても、plan同期・通知のいずれも行わない
        # (subscription-updated-event-order-guard-design.md、DELETED分岐と同じ
        # 「stale全体スキップ」方針)。
        state = self.cancellation_store.get_cancellation_state("store-1")
        state.last_subscription_updated_event_time = datetime(
            2026, 9, 3, 11, 0, tzinfo=timezone.utc
        )
        store_profile_store = InMemoryStoreProfileStore()
        store_profile_store.set_plan("store-1", "スタンダードプラン")

        payload = _event_payload_with_created_and_previous(
            "evt_1",
            "customer.subscription.updated",
            {
                "customer": "cus_1",
                "cancel_at_period_end": True,
                "items": {
                    "data": [{"price": {"lookup_key": "line_reservation_ai_pro"}}]
                },
            },
            {"cancel_at_period_end": False},
            int(datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc).timestamp()),
        )
        timestamp = int(NOW.timestamp())
        header = _header(payload, SECRET, timestamp)

        result = receive_stripe_webhook(
            payload,
            header,
            SECRET,
            resolve_store_id_by_customer=_resolve_by_customer,
            cancellation_store=self.cancellation_store,
            store_profile_store=store_profile_store,
            push_client=self.push_client,
            now=NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(self.push_client.sent), 0)
        self.assertEqual(store_profile_store.get_plan("store-1"), "スタンダードプラン")
        stored = self.cancellation_store.get_cancellation_state("store-1")
        self.assertIsNone(stored.suspension_reason)
        self.assertEqual(
            stored.last_subscription_updated_event_time,
            datetime(2026, 9, 3, 11, 0, tzinfo=timezone.utc),
        )


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
