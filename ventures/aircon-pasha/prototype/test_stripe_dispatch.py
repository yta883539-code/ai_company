#!/usr/bin/env python3
"""stripe_dispatch.pyの単体テスト。
stripe-webhook-event-dispatch-design.md(フェーズ126)4節のテスト観点に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from deletion_candidate import InMemoryProfileDeletionCandidateStore  # noqa: E402
from stripe_dispatch import StripeDispatchResult, dispatch_stripe_event  # noqa: E402

_CUSTOMER = "cus_ABC123"
_USER_ID = "U1"


def _resolve_known(customer):
    return _USER_ID if customer == _CUSTOMER else None


def _resolve_none(customer):
    return None


class DispatchSubscriptionDeletedTest(unittest.TestCase):
    def test_marks_deletion_candidate_when_customer_resolves(self):
        store = InMemoryProfileDeletionCandidateStore()
        created = int(datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc).timestamp())
        event = {
            "type": "customer.subscription.deleted",
            "created": created,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.marked_user_ids, [_USER_ID])
        self.assertIsNotNone(store.get_deletion_candidate_at(_USER_ID))

    def test_invalid_event_when_created_missing(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.invalid_events, ["customer.subscription.deleted"])
        self.assertEqual(result.marked_user_ids, [])
        self.assertIsNone(store.get_deletion_candidate_at(_USER_ID))

    def test_invalid_event_when_created_not_numeric(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.deleted",
            "created": "not-a-timestamp",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.invalid_events, ["customer.subscription.deleted"])

    def test_invalid_event_when_created_is_bool(self):
        # bool は int のサブクラスのため明示的に除外する分岐を確認する
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.deleted",
            "created": True,
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.invalid_events, ["customer.subscription.deleted"])


class DispatchSubscriptionCreatedTest(unittest.TestCase):
    def test_clears_deletion_candidate_unconditionally(self):
        store = InMemoryProfileDeletionCandidateStore()
        store.set_deletion_candidate_at(_USER_ID, datetime(2027, 8, 25, tzinfo=timezone.utc))
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])
        self.assertIsNone(store.get_deletion_candidate_at(_USER_ID))

    def test_clears_even_when_nothing_was_set_idempotent(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])


class DispatchSubscriptionUpdatedTest(unittest.TestCase):
    def test_clears_when_status_active(self):
        store = InMemoryProfileDeletionCandidateStore()
        store.set_deletion_candidate_at(_USER_ID, datetime(2027, 8, 25, tzinfo=timezone.utc))
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "active"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])
        self.assertIsNone(store.get_deletion_candidate_at(_USER_ID))

    def test_clears_when_status_trialing(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "trialing"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [_USER_ID])

    def test_does_nothing_when_status_past_due(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "past_due"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [])
        self.assertEqual(result.marked_user_ids, [])

    def test_does_nothing_when_status_canceled(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": _CUSTOMER, "status": "canceled"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.cleared_user_ids, [])


class DispatchIgnoredAndUnresolvedTest(unittest.TestCase):
    def test_ignored_type_is_recorded_and_no_handler_called(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "invoice.paid",
            "data": {"object": {"customer": _CUSTOMER}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_known)
        self.assertEqual(result.ignored_types, ["invoice.paid"])
        self.assertEqual(result.marked_user_ids, [])
        self.assertEqual(result.cleared_user_ids, [])

    def test_unresolved_customer_is_recorded(self):
        store = InMemoryProfileDeletionCandidateStore()
        event = {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": "cus_UNKNOWN"}},
        }
        result = dispatch_stripe_event(event, store=store, resolve_user_id=_resolve_none)
        self.assertEqual(result.unresolved_customers, ["cus_UNKNOWN"])
        self.assertEqual(result.cleared_user_ids, [])

    def test_default_result_is_all_empty(self):
        self.assertEqual(StripeDispatchResult(), StripeDispatchResult())


if __name__ == "__main__":
    unittest.main()
