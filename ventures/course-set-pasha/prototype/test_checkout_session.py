#!/usr/bin/env python3
"""checkout_session.pyの単体テスト。
checkout-initiation-flow-design.mdのパラメータ組み立てルールに沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import (  # noqa: E402
    DEFAULT_CANCEL_URL,
    DEFAULT_SUCCESS_URL,
    build_checkout_session_params,
    create_checkout_session,
    get_checkout_runtime_dependencies,
    main,
)


class BuildCheckoutSessionParamsTest(unittest.TestCase):
    def test_raises_on_empty_user_id(self):
        with self.assertRaises(ValueError):
            build_checkout_session_params("")

    def test_raises_on_none_user_id(self):
        with self.assertRaises(ValueError):
            build_checkout_session_params(None)

    def test_new_customer_has_no_customer_key(self):
        params = build_checkout_session_params("Uabc123")
        self.assertEqual(params["mode"], "subscription")
        self.assertEqual(params["client_reference_id"], "Uabc123")
        self.assertEqual(params["success_url"], DEFAULT_SUCCESS_URL)
        self.assertEqual(params["cancel_url"], DEFAULT_CANCEL_URL)
        self.assertNotIn("customer", params)

    def test_existing_customer_is_reused(self):
        params = build_checkout_session_params(
            "Uabc123", existing_stripe_customer_id="cus_existing456"
        )
        self.assertEqual(params["customer"], "cus_existing456")
        self.assertEqual(params["client_reference_id"], "Uabc123")

    def test_custom_success_and_cancel_urls_are_used(self):
        params = build_checkout_session_params(
            "Uabc123",
            success_url="https://example.com/ok",
            cancel_url="https://example.com/ng",
        )
        self.assertEqual(params["success_url"], "https://example.com/ok")
        self.assertEqual(params["cancel_url"], "https://example.com/ng")


class _StubUserProfileStore:
    """checkout-session-endpoint-design.md 3節のテスト用最小限スタブ。"""

    def __init__(self, stripe_customer_ids=None):
        self._stripe_customer_ids = stripe_customer_ids or {}
        self.get_stripe_customer_id_calls = []

    def get_stripe_customer_id(self, user_id):
        self.get_stripe_customer_id_calls.append(user_id)
        return self._stripe_customer_ids.get(user_id)


class CreateCheckoutSessionTest(unittest.TestCase):
    def test_missing_authorization_header_returns_401_without_verifying(self):
        verify_calls = []
        result = create_checkout_session(
            None,
            verify_id_token=lambda token: verify_calls.append(token) or "Uabc123",
            user_profile_store=_StubUserProfileStore(),
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "missing_or_malformed_authorization_header")
        self.assertIsNone(result.checkout_session_params)
        self.assertEqual(verify_calls, [])

    def test_non_bearer_authorization_header_returns_401_without_verifying(self):
        verify_calls = []
        result = create_checkout_session(
            "Basic xxx",
            verify_id_token=lambda token: verify_calls.append(token) or "Uabc123",
            user_profile_store=_StubUserProfileStore(),
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "missing_or_malformed_authorization_header")
        self.assertEqual(verify_calls, [])

    def test_invalid_id_token_returns_401_without_querying_store(self):
        store = _StubUserProfileStore()
        result = create_checkout_session(
            "Bearer invalid-token",
            verify_id_token=lambda token: None,
            user_profile_store=store,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_id_token")
        self.assertIsNone(result.checkout_session_params)
        self.assertEqual(store.get_stripe_customer_id_calls, [])

    def test_new_user_gets_200_without_customer_key(self):
        store = _StubUserProfileStore()
        result = create_checkout_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123" if token == "valid-token" else None,
            user_profile_store=store,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)
        self.assertEqual(result.checkout_session_params["client_reference_id"], "Uabc123")
        self.assertNotIn("customer", result.checkout_session_params)
        self.assertEqual(store.get_stripe_customer_id_calls, ["Uabc123"])

    def test_existing_customer_is_reused_in_params(self):
        store = _StubUserProfileStore({"Uabc123": "cus_existing456"})
        result = create_checkout_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123",
            user_profile_store=store,
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.checkout_session_params["customer"], "cus_existing456")

    def test_custom_success_and_cancel_urls_are_propagated(self):
        store = _StubUserProfileStore()
        result = create_checkout_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123",
            user_profile_store=store,
            success_url="https://example.com/ok",
            cancel_url="https://example.com/ng",
        )
        self.assertEqual(result.checkout_session_params["success_url"], "https://example.com/ok")
        self.assertEqual(result.checkout_session_params["cancel_url"], "https://example.com/ng")


class GetCheckoutRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_user_profile_store_and_placeholder_verify_id_token(self):
        deps = get_checkout_runtime_dependencies()
        self.assertIn("user_profile_store", deps)
        self.assertIn("verify_id_token", deps)
        self.assertIsNone(deps["user_profile_store"].get_stripe_customer_id("Uabc123"))
        with self.assertRaises(NotImplementedError):
            deps["verify_id_token"]("some-id-token")


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (test_stripe_webhook._StubFlaskRequestと対称)。"""

    def __init__(self, headers: dict):
        self.headers = headers


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント、Checkout Session版)のテスト。
    checkout-session-cloud-function-entry-point-design.mdで設計した、実リクエスト
    オブジェクトからのAuthorizationヘッダ取り出し配線・verify_id_token未実装時の501分岐を
    検証する(create_checkout_session()自体の分岐はCreateCheckoutSessionTestで既にカバー済み)。"""

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
