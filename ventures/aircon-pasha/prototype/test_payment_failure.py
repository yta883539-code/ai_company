#!/usr/bin/env python3
"""payment_failure.pyの単体テスト。
payment-failure-dunning-design.md(フェーズ139)3・4節の状態更新ロジックの仕様に沿った
挙動を確認する。InMemoryUserProfileStore(user_id_linking.py)がPaymentFailureStoreProtocol
を構造的に満たすことも本テストで併せて確認する。"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from payment_failure import (  # noqa: E402
    clear_payment_failure_on_success,
    mark_payment_failure_detected,
)
from user_id_linking import InMemoryUserProfileStore, UserProfile  # noqa: E402

_EVENT_TIME = datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc)


def _store_with_user(user_id: str = "U1") -> InMemoryUserProfileStore:
    store = InMemoryUserProfileStore()
    store.save(
        user_id,
        UserProfile(
            business_name="テスト洗浄社",
            business_type="独立系",
            email="test@example.com",
            linked_at=_EVENT_TIME,
        ),
    )
    return store


class MarkPaymentFailureDetectedTest(unittest.TestCase):
    def test_sets_payment_failure_detected_at_to_event_time(self):
        store = _store_with_user()
        result = mark_payment_failure_detected(store, "U1", _EVENT_TIME)
        self.assertEqual(result, _EVENT_TIME)
        self.assertEqual(store.get_payment_failure_detected_at("U1"), _EVENT_TIME)

    def test_overwrites_an_existing_value_with_the_latest_failure(self):
        store = _store_with_user()
        mark_payment_failure_detected(store, "U1", _EVENT_TIME)
        later_event_time = _EVENT_TIME + timedelta(days=3)
        result = mark_payment_failure_detected(store, "U1", later_event_time)
        self.assertEqual(result, later_event_time)
        self.assertEqual(store.get_payment_failure_detected_at("U1"), later_event_time)

    def test_does_not_touch_payment_suspended_at(self):
        store = _store_with_user()
        mark_payment_failure_detected(store, "U1", _EVENT_TIME)
        self.assertIsNone(store.get_payment_suspended_at("U1"))

    def test_does_not_affect_other_users(self):
        store = _store_with_user()
        mark_payment_failure_detected(store, "U1", _EVENT_TIME)
        self.assertIsNone(store.get_payment_failure_detected_at("U2"))


class ClearPaymentFailureOnSuccessTest(unittest.TestCase):
    def test_clears_both_fields_and_returns_true(self):
        store = _store_with_user()
        mark_payment_failure_detected(store, "U1", _EVENT_TIME)
        store.set_payment_suspended_at("U1", _EVENT_TIME + timedelta(days=7))
        cleared = clear_payment_failure_on_success(store, "U1")
        self.assertTrue(cleared)
        self.assertIsNone(store.get_payment_failure_detected_at("U1"))
        self.assertIsNone(store.get_payment_suspended_at("U1"))

    def test_clears_when_only_failure_detected_at_is_set(self):
        store = _store_with_user()
        mark_payment_failure_detected(store, "U1", _EVENT_TIME)
        cleared = clear_payment_failure_on_success(store, "U1")
        self.assertTrue(cleared)
        self.assertIsNone(store.get_payment_failure_detected_at("U1"))

    def test_is_idempotent_when_nothing_is_set(self):
        store = _store_with_user()
        cleared = clear_payment_failure_on_success(store, "U1")
        self.assertFalse(cleared)

    def test_unknown_user_id_is_a_harmless_no_op(self):
        store = _store_with_user()
        cleared = clear_payment_failure_on_success(store, "unknown-user")
        self.assertFalse(cleared)


if __name__ == "__main__":
    unittest.main()
