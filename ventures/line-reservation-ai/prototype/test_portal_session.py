#!/usr/bin/env python3
"""portal_session.pyの単体テスト。
portal-session-provider-design.mdのパラメータ組み立てルール・StripePortalLinkProviderの
挙動を確認する(aircon-pasha/prototype/test_portal_session.pyと対称の構成。本ventureにも
LIFF IDトークン検証を伴うHTTPエンドポイントが無いためcreate_portal_session()/main()相当の
テストは無い、design 4節参照)。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from portal_session import (  # noqa: E402
    DEFAULT_RETURN_URL,
    InMemoryPortalLinkProvider,
    StripePortalLinkProvider,
    build_portal_session_params,
)


class BuildPortalSessionParamsTest(unittest.TestCase):
    def test_raises_on_empty_stripe_customer_id(self):
        with self.assertRaises(ValueError):
            build_portal_session_params("")

    def test_raises_on_none_stripe_customer_id(self):
        with self.assertRaises(ValueError):
            build_portal_session_params(None)

    def test_params_contain_customer_and_default_return_url(self):
        params = build_portal_session_params("cus_existing456")
        self.assertEqual(params["customer"], "cus_existing456")
        self.assertEqual(params["return_url"], DEFAULT_RETURN_URL)

    def test_custom_return_url_is_used(self):
        params = build_portal_session_params(
            "cus_existing456", return_url="https://example.com/back"
        )
        self.assertEqual(params["return_url"], "https://example.com/back")


class _StubStoreProfileStore:
    """portal-session-provider-design.md 4節のテスト用最小限スタブ。"""

    def __init__(self, stripe_customer_ids=None):
        self._stripe_customer_ids = stripe_customer_ids or {}
        self.get_stripe_customer_id_calls = []

    def get_stripe_customer_id(self, store_id):
        self.get_stripe_customer_id_calls.append(store_id)
        return self._stripe_customer_ids.get(store_id)


class StripePortalLinkProviderTest(unittest.TestCase):
    """`StripePortalLinkProvider`(`PortalLinkProvider`実装本体、
    portal-session-provider-design.md 4節)のテスト。"""

    def test_returns_none_when_store_has_no_stripe_customer_id(self):
        store = _StubStoreProfileStore()
        creator_calls = []
        provider = StripePortalLinkProvider(
            store, session_creator=lambda params: creator_calls.append(params) or "unused"
        )

        result = provider.get_portal_url("store-1")

        self.assertIsNone(result)
        self.assertEqual(creator_calls, [])
        self.assertEqual(store.get_stripe_customer_id_calls, ["store-1"])

    def test_calls_session_creator_with_built_params_and_returns_its_result(self):
        store = _StubStoreProfileStore({"store-1": "cus_existing456"})
        creator_calls = []

        def fake_session_creator(params):
            creator_calls.append(params)
            return "https://billing.stripe.com/p/session/fake123"

        provider = StripePortalLinkProvider(store, session_creator=fake_session_creator)

        result = provider.get_portal_url("store-1")

        self.assertEqual(result, "https://billing.stripe.com/p/session/fake123")
        self.assertEqual(
            creator_calls,
            [{"customer": "cus_existing456", "return_url": DEFAULT_RETURN_URL}],
        )

    def test_custom_return_url_is_propagated_to_session_creator(self):
        store = _StubStoreProfileStore({"store-1": "cus_existing456"})
        creator_calls = []
        provider = StripePortalLinkProvider(
            store,
            session_creator=lambda params: creator_calls.append(params) or "url",
            return_url="https://example.com/back",
        )

        provider.get_portal_url("store-1")

        self.assertEqual(creator_calls[0]["return_url"], "https://example.com/back")

    def test_default_session_creator_raises_not_implemented(self):
        store = _StubStoreProfileStore({"store-1": "cus_existing456"})
        provider = StripePortalLinkProvider(store)

        with self.assertRaises(NotImplementedError):
            provider.get_portal_url("store-1")


class InMemoryPortalLinkProviderTest(unittest.TestCase):
    def test_default_returns_stub_url(self):
        provider = InMemoryPortalLinkProvider()
        self.assertEqual(
            provider.get_portal_url("store-1"), "https://billing.stripe.com/p/session/stub"
        )

    def test_custom_url_is_returned(self):
        provider = InMemoryPortalLinkProvider("https://example.test/portal")
        self.assertEqual(provider.get_portal_url("store-1"), "https://example.test/portal")

    def test_none_url_is_returned_as_is(self):
        provider = InMemoryPortalLinkProvider(None)
        self.assertIsNone(provider.get_portal_url("store-1"))


if __name__ == "__main__":
    unittest.main()
