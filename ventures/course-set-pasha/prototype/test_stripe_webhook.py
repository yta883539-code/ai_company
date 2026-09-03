import hashlib
import hmac
import json
import os
import time
import unittest
from datetime import datetime, timezone

from application_form_submission_flow import InMemoryUserProfileStore
from cloud_function_webhook import (
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    InMemoryPortalLinkProvider,
    InMemoryUsageCounter,
)
from deletion_candidate import InMemoryProfileDeletionCandidateStore
from stripe_webhook import (
    InMemoryStripeEventIdStore,
    dispatch_stripe_event,
    get_stripe_runtime_dependencies,
    handle_checkout_session_completed,
    main,
    make_resolve_user_id,
    receive_stripe_webhook,
    verify_stripe_signature,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError

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

    def test_subscription_deleted_clears_blocked_but_billing_owner_notified_at(self):
        # blocked-but-billing-owner-notification-design.md 4節: 解約確定
        # (customer.subscription.deleted)時にも通知済みフラグをクリアする。
        user_profile_store = InMemoryUserProfileStore()
        user_profile_store.set_blocked_but_billing_owner_notified_at(
            "user_1", datetime(2026, 8, 1, tzinfo=timezone.utc)
        )
        event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            user_profile_store=user_profile_store,
        )
        self.assertEqual(result.marked_user_ids, ["user_1"])
        self.assertIsNone(
            user_profile_store.get_blocked_but_billing_owner_notified_at("user_1")
        )

    def test_subscription_deleted_without_user_profile_store_is_backward_compatible(self):
        event = {
            "type": "customer.subscription.deleted",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.marked_user_ids, ["user_1"])

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


class DispatchInvoicePaymentFailedTest(unittest.TestCase):
    """payment-failure-dunning-design.md 6節・フェーズ119対応。"""

    def setUp(self):
        self.store = InMemoryProfileDeletionCandidateStore()
        self.usage_counter = InMemoryUsageCounter()

    def test_marks_payment_failure_detected_when_customer_resolves(self):
        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
        )
        self.assertEqual(result.payment_failure_detected_user_ids, ["user_1"])
        self.assertEqual(
            self.usage_counter.get_payment_failure_detected_at("user_1"),
            datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        )

    def test_invalid_event_when_created_missing(self):
        event = {
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
        )
        self.assertEqual(result.invalid_events, ["invoice.payment_failed"])
        self.assertEqual(result.payment_failure_detected_user_ids, [])
        self.assertIsNone(self.usage_counter.get_payment_failure_detected_at("user_1"))

    def test_ignored_when_usage_counter_not_provided(self):
        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.ignored_types, ["invoice.payment_failed"])
        self.assertEqual(result.payment_failure_detected_user_ids, [])

    def test_unresolved_customer_is_recorded_and_no_write_happens(self):
        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_unknown"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({}),
            usage_counter=self.usage_counter,
        )
        self.assertEqual(result.unresolved_customers, ["cus_unknown"])
        self.assertEqual(result.payment_failure_detected_user_ids, [])


class DispatchInvoicePaymentFailedWithPushClientTest(unittest.TestCase):
    """payment-failure-dunning-design.md 4節・フェーズ124対応。push_client指定時、
    payment_recovery_notification.handle_payment_failure_detected()経由で実際に
    決済失敗検知時(段階1)の通知を送信してから状態を書き込むことを確認する。"""

    def setUp(self):
        self.store = InMemoryProfileDeletionCandidateStore()
        self.usage_counter = InMemoryUsageCounter()

    def test_sends_notification_and_marks_detected_at(self):
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
            portal_link_provider=InMemoryPortalLinkProvider(
                url="https://billing.stripe.com/p/session/user_1"
            ),
        )
        self.assertEqual(result.payment_failure_detected_user_ids, ["user_1"])
        self.assertEqual(result.payment_failure_detection_notification_failed_user_ids, [])
        self.assertEqual(len(push_client.sent), 1)
        self.assertEqual(push_client.sent[0][0], "user_1")
        self.assertIn("お支払いの確認をお願いします", push_client.sent[0][1])
        self.assertEqual(
            self.usage_counter.get_payment_failure_detected_at("user_1"),
            datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        )

    def test_send_failure_leaves_state_unwritten(self):
        class _FailingPushClient:
            def send_message(self, user_id: str, text: str) -> None:
                raise LinePushDeliveryError("simulated failure")

        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=_FailingPushClient(),
        )
        self.assertEqual(result.payment_failure_detected_user_ids, [])
        self.assertEqual(
            result.payment_failure_detection_notification_failed_user_ids, ["user_1"]
        )
        self.assertIsNone(self.usage_counter.get_payment_failure_detected_at("user_1"))

    def test_portal_link_provider_is_substituted_into_notification(self):
        """フェーズ127: portal_link_provider指定時、決済失敗検知時通知にも実URLが
        差し込まれることを確認する(dispatch_stripe_eventからhandle_payment_failure_
        detected()への配線)。"""
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
            portal_link_provider=InMemoryPortalLinkProvider(
                url="https://billing.stripe.com/p/session/user_1"
            ),
        )
        self.assertEqual(result.payment_failure_detected_user_ids, ["user_1"])
        self.assertIn("https://billing.stripe.com/p/session/user_1", push_client.sent[0][1])

    def test_no_portal_link_provider_sends_fallback_message(self):
        """portal_link_provider未指定時はPORTAL_LINK_UNAVAILABLE_FALLBACKが送られる
        (既存の安全側デフォルト、後方互換)。"""
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
        )
        self.assertEqual(push_client.sent[0][1], PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_invalid_event_when_created_missing_even_with_push_client(self):
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_failed",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
        )
        self.assertEqual(result.invalid_events, ["invoice.payment_failed"])
        self.assertEqual(push_client.sent, [])


class DispatchInvoicePaymentSucceededTest(unittest.TestCase):
    """payment-failure-dunning-design.md 6節・フェーズ119対応。"""

    def setUp(self):
        self.store = InMemoryProfileDeletionCandidateStore()
        self.usage_counter = InMemoryUsageCounter()

    def test_clears_payment_failure_detected_at(self):
        self.usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
        )
        self.assertEqual(result.payment_recovered_user_ids, ["user_1"])
        self.assertIsNone(self.usage_counter.get_payment_failure_detected_at("user_1"))

    def test_idempotent_when_nothing_was_set(self):
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
        )
        self.assertEqual(result.payment_recovered_user_ids, [])

    def test_ignored_when_usage_counter_not_provided(self):
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event, store=self.store, resolve_user_id=_resolver({"cus_A": "user_1"})
        )
        self.assertEqual(result.ignored_types, ["invoice.payment_succeeded"])
        self.assertEqual(result.payment_recovered_user_ids, [])


class DispatchInvoicePaymentSucceededWithPushClientTest(unittest.TestCase):
    """payment-failure-dunning-design.md 6節・フェーズ122対応。push_client指定時、
    payment_recovery_notification.handle_payment_succeeded()経由で実際に通知を送信して
    から状態をクリアすることを確認する。"""

    def setUp(self):
        self.store = InMemoryProfileDeletionCandidateStore()
        self.usage_counter = InMemoryUsageCounter()

    def test_recovered_from_suspension_sends_notification_and_clears_state(self):
        self.usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2026, 8, 20, tzinfo=timezone.utc)
        )
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
            now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(result.payment_recovered_user_ids, ["user_1"])
        self.assertEqual(result.payment_recovery_notification_failed_user_ids, [])
        self.assertEqual(len(push_client.sent), 1)
        self.assertEqual(push_client.sent[0][0], "user_1")
        self.assertIsNone(self.usage_counter.get_payment_failure_detected_at("user_1"))

    def test_confirmed_in_grace_sends_notification(self):
        self.usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2026, 8, 26, tzinfo=timezone.utc)
        )
        self.usage_counter.set_payment_failure_reminder_sent_at(
            "user_1", datetime(2026, 8, 27, tzinfo=timezone.utc)
        )
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
            now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(result.payment_recovered_user_ids, ["user_1"])
        self.assertEqual(len(push_client.sent), 1)

    def test_silent_reset_sends_no_notification(self):
        self.usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
            now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        # 状態はクリアされるが(push_client未指定時と同じ意味)、通知は送信されない。
        self.assertEqual(result.payment_recovered_user_ids, ["user_1"])
        self.assertEqual(result.payment_recovery_notification_failed_user_ids, [])
        self.assertEqual(push_client.sent, [])
        self.assertIsNone(self.usage_counter.get_payment_failure_detected_at("user_1"))

    def test_no_dunning_is_untouched(self):
        push_client = InMemoryLinePushClient()
        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
            now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(result.payment_recovered_user_ids, [])
        self.assertEqual(push_client.sent, [])

    def test_send_failure_leaves_state_untouched(self):
        self.usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2026, 8, 20, tzinfo=timezone.utc)
        )

        class _FailingPushClient:
            def send_message(self, user_id: str, text: str) -> None:
                raise LinePushDeliveryError("simulated failure")

        event = {
            "type": "invoice.payment_succeeded",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=_FailingPushClient(),
            now=datetime(2026, 8, 29, tzinfo=timezone.utc),
        )
        self.assertEqual(result.payment_recovered_user_ids, [])
        self.assertEqual(result.payment_recovery_notification_failed_user_ids, ["user_1"])
        self.assertIsNotNone(self.usage_counter.get_payment_failure_detected_at("user_1"))


class ReceiveStripeWebhookInvoicePaymentEventsTest(unittest.TestCase):
    """receive_stripe_webhook()がinvoice.payment_failed/succeededをusage_counterごと
    dispatch_stripe_event()へ委譲することを確認する(フェーズ119)。"""

    def setUp(self):
        self.store = InMemoryProfileDeletionCandidateStore()
        self.usage_counter = InMemoryUsageCounter()

    def _send(self, body: bytes):
        timestamp = int(NOW)
        header = _header(body, SECRET, timestamp)
        return receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            now=datetime.fromtimestamp(NOW, tz=timezone.utc),
        )

    def test_payment_failed_event_marks_detected_at(self):
        body = (
            b'{"id":"evt_1","type":"invoice.payment_failed","created":1700000000,'
            b'"data":{"object":{"customer":"cus_A"}}}'
        )
        result = self._send(body)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.payment_failure_detected_user_ids, ["user_1"])
        self.assertIsNotNone(self.usage_counter.get_payment_failure_detected_at("user_1"))

    def test_payment_succeeded_event_clears_detected_at(self):
        self.usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2026, 8, 28, tzinfo=timezone.utc)
        )
        body = (
            b'{"id":"evt_2","type":"invoice.payment_succeeded",'
            b'"data":{"object":{"customer":"cus_A"}}}'
        )
        result = self._send(body)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.payment_recovered_user_ids, ["user_1"])
        self.assertIsNone(self.usage_counter.get_payment_failure_detected_at("user_1"))

    def test_payment_succeeded_event_sends_notification_when_push_client_given(self):
        """フェーズ122: receive_stripe_webhook()もpush_clientをdispatch_stripe_event()へ
        委譲することを確認する。"""
        self.usage_counter.set_payment_failure_detected_at(
            "user_1", datetime(2020, 1, 1, tzinfo=timezone.utc)
        )
        push_client = InMemoryLinePushClient()
        body = (
            b'{"id":"evt_2","type":"invoice.payment_succeeded",'
            b'"data":{"object":{"customer":"cus_A"}}}'
        )
        timestamp = int(NOW)
        header = _header(body, SECRET, timestamp)
        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=self.store,
            resolve_user_id=_resolver({"cus_A": "user_1"}),
            usage_counter=self.usage_counter,
            push_client=push_client,
            now=datetime.fromtimestamp(NOW, tz=timezone.utc),
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.dispatch_result.payment_recovered_user_ids, ["user_1"])
        self.assertEqual(len(push_client.sent), 1)
        self.assertIsNone(self.usage_counter.get_payment_failure_detected_at("user_1"))


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

    def test_usage_counter_writes_upgraded_at_when_provided(self):
        usage_counter = InMemoryUsageCounter()
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "U1", "customer": "cus_A"}},
        }
        now = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)

        result = handle_checkout_session_completed(
            event, self.store, usage_counter=usage_counter, now=now
        )

        self.assertTrue(result.upgraded_at_written)
        self.assertEqual(usage_counter.get_upgraded_at("U1"), now)

    def test_usage_counter_upgraded_at_is_idempotent(self):
        usage_counter = InMemoryUsageCounter()
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "U1", "customer": "cus_A"}},
        }
        first = datetime(2026, 8, 23, 18, 0, tzinfo=timezone.utc)
        second = datetime(2026, 8, 24, 3, 0, tzinfo=timezone.utc)

        handle_checkout_session_completed(
            event, self.store, usage_counter=usage_counter, now=first
        )
        handle_checkout_session_completed(
            event, self.store, usage_counter=usage_counter, now=second
        )

        # 既に設定済みの場合は上書きしない(trial_start_atと同じ冪等性)。
        self.assertEqual(usage_counter.get_upgraded_at("U1"), first)

    def test_no_usage_counter_does_not_write_upgraded_at(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "U1", "customer": "cus_A"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.upgraded_at_written)

    def test_link_failure_does_not_write_upgraded_at_even_with_usage_counter(self):
        usage_counter = InMemoryUsageCounter()
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_A"}},
        }
        result = handle_checkout_session_completed(
            event, self.store, usage_counter=usage_counter
        )
        self.assertFalse(result.upgraded_at_written)
        self.assertIsNone(usage_counter.get_upgraded_at("U1"))

    def test_metadata_plan_is_written_to_store(self):
        # checkout-session-plan-selection-design.md(フェーズ152)。
        # checkout_session.build_checkout_session_params()がmetadata.planとして設定した
        # 値を、line_itemsのexpand等の追加API呼び出しなしにそのまま読み取れることの確認。
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "U1",
                    "customer": "cus_A",
                    "metadata": {"plan": "スタンダード"},
                }
            },
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertTrue(result.plan_written)
        self.assertEqual(self.store.get_plan("U1"), "スタンダード")

    def test_missing_metadata_does_not_write_plan(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "U1", "customer": "cus_A"}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.plan_written)
        self.assertIsNone(self.store.get_plan("U1"))

    def test_unknown_plan_value_does_not_write_plan(self):
        # PLAN_MONTHLY_LIMITSにない値(古いフロントエンド由来の想定外文字列等)は書き込まない。
        event = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "U1",
                    "customer": "cus_A",
                    "metadata": {"plan": "プレミアム"},
                }
            },
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.plan_written)
        self.assertIsNone(self.store.get_plan("U1"))

    def test_link_failure_does_not_write_plan_even_with_metadata(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_A", "metadata": {"plan": "ライト"}}},
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertFalse(result.linked)
        self.assertFalse(result.plan_written)


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

    def _call(self, body: bytes, header: str, *, user_profile_store=None, usage_counter=None):
        return receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=self.deletion_store,
            resolve_user_id=lambda _customer: None,
            user_profile_store=user_profile_store,
            usage_counter=usage_counter,
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

    def test_checkout_session_completed_writes_upgraded_at_when_usage_counter_provided(self):
        body = (
            b'{"id":"evt_1","type":"checkout.session.completed",'
            b'"data":{"object":{"client_reference_id":"U1","customer":"cus_A"}}}'
        )
        header = _header(body, SECRET, int(self.now.timestamp()))
        usage_counter = InMemoryUsageCounter()
        result = self._call(
            body,
            header,
            user_profile_store=self.user_profile_store,
            usage_counter=usage_counter,
        )
        self.assertTrue(result.checkout_link_result.upgraded_at_written)
        self.assertEqual(usage_counter.get_upgraded_at("U1"), self.now)

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
        # cus_Aはcheckout.session.completedで一度も紐付けられていないため未解決のまま
        # (resolve_user_idが常にNoneを返す暫定実装だからではない。紐付け済みcustomerが
        # 実際に解決されることはGetStripeRuntimeDependenciesResolutionTestで検証する)。
        self.assertEqual(result.dispatch_result.unresolved_customers, ["cus_A"])


class GetStripeRuntimeDependenciesResolutionTest(unittest.TestCase):
    """get_stripe_runtime_dependencies()が返すresolve_user_id・storeが、常にNoneを返す
    暫定実装ではなく実際にstripe_customer_id→user_idの紐付けを解決できることを検証する
    (stripe-webhook-cloud-function-entry-point-design.md「残課題」がフェーズ96時点の
    記述のまま更新されておらず、フェーズ97のmake_resolve_user_id()導入後も常時Noneを返す
    ままだと誤って読めた点への回帰防止。同一のget_stripe_runtime_dependencies()呼び出し
    結果(=同一プロセス内)を使い回した場合に限り、checkout.session.completedで書き込んだ
    紐付けをcustomer.subscription.*側で読めることを確認する)。"""

    ENV_SECRET = "demo-webhook-secret"

    def _signed_header(self, body: bytes, secret: str) -> str:
        timestamp = int(time.time())
        return _header(body, secret, timestamp)

    def test_checkout_link_is_resolved_by_subsequent_subscription_event(self):
        deps = get_stripe_runtime_dependencies()

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
            b'{"id":"evt_sub","type":"customer.subscription.deleted",'
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
        # 紐付けが解決されたため、cus_A→U1がdeletion candidateとしてmarkされる。
        self.assertEqual(subscription_result.dispatch_result.marked_user_ids, ["U1"])

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


class ReceiveStripeWebhookIdempotencyWiringTest(unittest.TestCase):
    """stripe-event-idempotency-design.md対応(フェーズ151)。`event_id_store`指定時に
    同一`event.id`の2回目以降の配信でハンドラが呼ばれず副作用ゼロで200を返すことを
    検証する(aircon-pashaフェーズ177版と同じ検証パターン)。"""

    def setUp(self):
        self.now = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

    def test_duplicate_event_id_is_ignored_on_second_delivery(self):
        store = InMemoryProfileDeletionCandidateStore()
        resolve_user_id = _resolver({"cus_A": "user_1"})
        event_id_store = InMemoryStripeEventIdStore()
        body = (
            b'{"id":"evt_dup_1","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        header = _header(body, SECRET, int(NOW))

        first = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            event_id_store=event_id_store,
            now=self.now,
        )
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.duplicate)
        self.assertEqual(first.dispatch_result.marked_user_ids, ["user_1"])

        second = receive_stripe_webhook(
            body,
            header,
            SECRET,
            store=store,
            resolve_user_id=resolve_user_id,
            event_id_store=event_id_store,
            now=self.now,
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.duplicate)
        self.assertIsNone(second.dispatch_result)

    def test_duplicate_checkout_session_completed_does_not_relink(self):
        store = InMemoryUserProfileStore()
        event_id_store = InMemoryStripeEventIdStore()
        body = json.dumps(
            {
                "id": "evt_dup_checkout",
                "type": "checkout.session.completed",
                "data": {
                    "object": {"client_reference_id": "user_1", "customer": "cus_new"}
                },
            }
        ).encode("utf-8")
        header = _header(body, SECRET, int(NOW))
        base_kwargs = dict(
            store=InMemoryProfileDeletionCandidateStore(),
            resolve_user_id=lambda customer: None,
            user_profile_store=store,
            event_id_store=event_id_store,
            now=self.now,
        )

        first = receive_stripe_webhook(body, header, SECRET, **base_kwargs)
        self.assertTrue(first.checkout_link_result.linked)

        second = receive_stripe_webhook(body, header, SECRET, **base_kwargs)
        self.assertTrue(second.duplicate)
        self.assertIsNone(second.checkout_link_result)

    def test_missing_event_id_skips_idempotency_check(self):
        store = InMemoryProfileDeletionCandidateStore()
        resolve_user_id = _resolver({"cus_A": "user_1"})
        event_id_store = InMemoryStripeEventIdStore()
        body = (
            b'{"type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        header = _header(body, SECRET, int(NOW))

        for _ in range(2):
            result = receive_stripe_webhook(
                body,
                header,
                SECRET,
                store=store,
                resolve_user_id=resolve_user_id,
                event_id_store=event_id_store,
                now=self.now,
            )
            self.assertEqual(result.status_code, 200)
            self.assertFalse(result.duplicate)

    def test_event_id_store_none_preserves_existing_behavior(self):
        store = InMemoryProfileDeletionCandidateStore()
        resolve_user_id = _resolver({"cus_A": "user_1"})
        body = (
            b'{"id":"evt_no_store","type":"customer.subscription.deleted",'
            b'"created":1700000000,"data":{"object":{"customer":"cus_A"}}}'
        )
        header = _header(body, SECRET, int(NOW))

        for _ in range(2):
            result = receive_stripe_webhook(
                body, header, SECRET, store=store, resolve_user_id=resolve_user_id, now=self.now
            )
            self.assertEqual(result.status_code, 200)
            self.assertFalse(result.duplicate)


class InMemoryStripeEventIdStoreTest(unittest.TestCase):
    def test_unmarked_event_id_has_not_processed(self):
        self.assertFalse(InMemoryStripeEventIdStore().has_processed("evt_1"))

    def test_marked_event_id_has_processed(self):
        event_id_store = InMemoryStripeEventIdStore()
        event_id_store.mark_processed("evt_1")
        self.assertTrue(event_id_store.has_processed("evt_1"))
        self.assertFalse(event_id_store.has_processed("evt_2"))


class GetStripeRuntimeDependenciesEventIdStoreTest(unittest.TestCase):
    def test_event_id_store_key_present_and_independent_per_call(self):
        deps = get_stripe_runtime_dependencies()
        self.assertIsInstance(deps["event_id_store"], InMemoryStripeEventIdStore)
        deps["event_id_store"].mark_processed("evt_1")

        other_deps = get_stripe_runtime_dependencies()
        self.assertFalse(other_deps["event_id_store"].has_processed("evt_1"))


if __name__ == "__main__":
    unittest.main()
