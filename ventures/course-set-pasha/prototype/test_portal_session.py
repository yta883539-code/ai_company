#!/usr/bin/env python3
"""portal_session.pyの単体テスト。
customer-portal-session-endpoint-design.mdのパラメータ組み立てルールに沿った挙動を確認する
(test_checkout_session.pyと対称の構成)。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from portal_session import (  # noqa: E402
    DEFAULT_RETURN_URL,
    build_portal_session_params,
    create_portal_session,
    get_portal_runtime_dependencies,
    main,
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


class _StubUserProfileStore:
    """customer-portal-session-endpoint-design.md 5節のテスト用最小限スタブ。"""

    def __init__(self, stripe_customer_ids=None):
        self._stripe_customer_ids = stripe_customer_ids or {}
        self.get_stripe_customer_id_calls = []

    def get_stripe_customer_id(self, user_id):
        self.get_stripe_customer_id_calls.append(user_id)
        return self._stripe_customer_ids.get(user_id)


class CreatePortalSessionTest(unittest.TestCase):
    def test_missing_authorization_header_returns_401_without_verifying(self):
        verify_calls = []
        result = create_portal_session(
            None,
            verify_id_token=lambda token: verify_calls.append(token) or "Uabc123",
            user_profile_store=_StubUserProfileStore(),
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "missing_or_malformed_authorization_header")
        self.assertIsNone(result.portal_session_params)
        self.assertEqual(verify_calls, [])

    def test_non_bearer_authorization_header_returns_401_without_verifying(self):
        verify_calls = []
        result = create_portal_session(
            "Basic xxx",
            verify_id_token=lambda token: verify_calls.append(token) or "Uabc123",
            user_profile_store=_StubUserProfileStore(),
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "missing_or_malformed_authorization_header")
        self.assertEqual(verify_calls, [])

    def test_invalid_id_token_returns_401_without_querying_store(self):
        store = _StubUserProfileStore()
        result = create_portal_session(
            "Bearer invalid-token",
            verify_id_token=lambda token: None,
            user_profile_store=store,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_id_token")
        self.assertIsNone(result.portal_session_params)
        self.assertEqual(store.get_stripe_customer_id_calls, [])

    def test_user_without_stripe_customer_returns_404(self):
        store = _StubUserProfileStore()
        result = create_portal_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123" if token == "valid-token" else None,
            user_profile_store=store,
        )
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.error, "no_stripe_customer")
        self.assertIsNone(result.portal_session_params)
        self.assertEqual(store.get_stripe_customer_id_calls, ["Uabc123"])

    def test_existing_customer_gets_200_with_params(self):
        store = _StubUserProfileStore({"Uabc123": "cus_existing456"})
        result = create_portal_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123",
            user_profile_store=store,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)
        self.assertEqual(
            result.portal_session_params,
            {"customer": "cus_existing456", "return_url": DEFAULT_RETURN_URL},
        )

    def test_custom_return_url_is_propagated(self):
        store = _StubUserProfileStore({"Uabc123": "cus_existing456"})
        result = create_portal_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123",
            user_profile_store=store,
            return_url="https://example.com/back",
        )
        self.assertEqual(result.portal_session_params["return_url"], "https://example.com/back")


class GetPortalRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_user_profile_store_and_placeholder_verify_id_token(self):
        deps = get_portal_runtime_dependencies()
        self.assertIn("user_profile_store", deps)
        self.assertIn("verify_id_token", deps)
        self.assertIsNone(deps["user_profile_store"].get_stripe_customer_id("Uabc123"))
        with self.assertRaises(NotImplementedError):
            deps["verify_id_token"]("some-id-token")


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (test_checkout_session._StubFlaskRequestと対称)。"""

    def __init__(self, headers: dict):
        self.headers = headers


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント、Portal Session版)のテスト。"""

    def test_missing_authorization_header_returns_401(self):
        request = _StubFlaskRequest({})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)
        self.assertEqual(response_body, "missing_or_malformed_authorization_header")

    def test_non_bearer_authorization_header_returns_401(self):
        request = _StubFlaskRequest({"Authorization": "Basic xxx"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)
        self.assertEqual(response_body, "missing_or_malformed_authorization_header")

    def test_well_formed_bearer_header_returns_501_pending_verify_id_token(self):
        request = _StubFlaskRequest({"Authorization": "Bearer some-id-token"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 501)
        self.assertEqual(response_body, "verify_id_token_not_implemented")


if __name__ == "__main__":
    unittest.main()
