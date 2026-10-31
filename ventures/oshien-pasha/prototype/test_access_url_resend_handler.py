#!/usr/bin/env python3
"""access_url_resend_handler.pyのテスト(フェーズ42)。
test_fan_pass_store.py・test_usage_counter.pyと同じ、標準ライブラリunittestのみを用いる
最小構成のテストランナーに揃える。
"""

from __future__ import annotations

import itertools
import unittest

from access_url_resend_handler import (
    FanPassNotFoundForSubscriptionError,
    InMemoryStripeSubscriptionLookup,
    MultipleActiveSubscriptionsError,
    handle_resend_request,
)
from fan_pass_store import InMemoryFanPassStore

_token_counter = itertools.count(1)


def _next_token() -> str:
    return f"new-token-{next(_token_counter)}"


class HandleResendRequestTest(unittest.TestCase):
    def test_unknown_email_returns_not_found_without_touching_fan_pass_store(self) -> None:
        store = InMemoryFanPassStore()
        lookup = InMemoryStripeSubscriptionLookup()
        internal_id, access_token = store.create(
            email="known@example.com",
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
        )
        lookup.register("known@example.com", "sub_1")

        result = handle_resend_request(
            store, lookup, "unknown@example.com", new_access_token_factory=_next_token
        )

        self.assertFalse(result.found)
        self.assertIsNone(result.internal_id)
        self.assertIsNone(result.new_access_token)
        self.assertIsNone(result.destination_email)
        # アクセストークンが書き換わっていないことを確認する(見つからない場合は無操作)。
        self.assertEqual(store.get_by_access_token(access_token).internal_id, internal_id)

    def test_known_email_reissues_token_and_returns_destination_email(self) -> None:
        store = InMemoryFanPassStore()
        lookup = InMemoryStripeSubscriptionLookup()
        internal_id, old_access_token = store.create(
            email="registered@example.com",
            stripe_customer_id="cus_2",
            stripe_subscription_id="sub_2",
        )
        lookup.register("registered@example.com", "sub_2")

        result = handle_resend_request(
            store, lookup, "registered@example.com", new_access_token_factory=_next_token
        )

        self.assertTrue(result.found)
        self.assertEqual(result.internal_id, internal_id)
        self.assertEqual(result.destination_email, "registered@example.com")
        self.assertIsNotNone(result.new_access_token)
        self.assertNotEqual(result.new_access_token, old_access_token)
        # 旧トークンは即時失効し、新トークンで引けることを確認する。
        self.assertIsNone(store.get_by_access_token(old_access_token))
        self.assertEqual(
            store.get_by_access_token(result.new_access_token).internal_id, internal_id
        )

    def test_multiple_active_subscriptions_raises_before_touching_fan_pass_store(self) -> None:
        store = InMemoryFanPassStore()
        lookup = InMemoryStripeSubscriptionLookup()
        _, access_token = store.create(
            email="dup@example.com",
            stripe_customer_id="cus_3",
            stripe_subscription_id="sub_3a",
        )
        lookup.register("dup@example.com", "sub_3a")
        lookup.register("dup@example.com", "sub_3b")

        with self.assertRaises(MultipleActiveSubscriptionsError):
            handle_resend_request(
                store, lookup, "dup@example.com", new_access_token_factory=_next_token
            )

        # 異常系で早期に例外を上げ、既存のアクセストークンへは一切触れていないことを確認する。
        self.assertEqual(store.get_by_access_token(access_token).internal_id is not None, True)

    def test_subscription_without_matching_fan_pass_document_raises(self) -> None:
        store = InMemoryFanPassStore()
        lookup = InMemoryStripeSubscriptionLookup()
        # Stripe側には有効なサブスクリプションが存在するが、fan_passドキュメントは
        # 一度もcreate()されていない(Webhook処理の未完了・不整合を想定した異常系)。
        lookup.register("orphan@example.com", "sub_orphan")

        with self.assertRaises(FanPassNotFoundForSubscriptionError):
            handle_resend_request(
                store, lookup, "orphan@example.com", new_access_token_factory=_next_token
            )


def _run() -> None:
    suite = unittest.TestLoader().loadTestsFromTestCase(HandleResendRequestTest)
    result = unittest.TextTestRunner(verbosity=0).run(suite)
    total = result.testsRun
    failed = len(result.failures) + len(result.errors)
    print(f"PASS={total - failed} FAIL={failed}")


if __name__ == "__main__":
    _run()
