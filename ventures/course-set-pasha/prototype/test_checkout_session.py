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
    PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER,
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

    def test_omitted_plan_has_no_line_items_or_metadata(self):
        # checkout-session-plan-selection-design.md(フェーズ152)追加前の後方互換確認。
        params = build_checkout_session_params("Uabc123")
        self.assertNotIn("line_items", params)
        self.assertNotIn("metadata", params)

    def test_valid_plan_adds_line_items_and_metadata(self):
        params = build_checkout_session_params("Uabc123", plan="スタンダード")
        self.assertEqual(
            params["line_items"],
            [{"price": PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER["スタンダード"], "quantity": 1}],
        )
        self.assertEqual(params["metadata"], {"plan": "スタンダード"})

    def test_each_known_plan_maps_to_a_distinct_price_id(self):
        for plan in ("ライト", "スタンダード", "セッター複数"):
            params = build_checkout_session_params("Uabc123", plan=plan)
            self.assertEqual(params["metadata"]["plan"], plan)
        price_ids = set(PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER.values())
        self.assertEqual(len(price_ids), 3)

    def test_unknown_plan_raises(self):
        with self.assertRaises(ValueError):
            build_checkout_session_params("Uabc123", plan="プレミアム")


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

    def test_valid_plan_is_propagated_to_params(self):
        store = _StubUserProfileStore()
        result = create_checkout_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123",
            user_profile_store=store,
            plan="ライト",
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.checkout_session_params["metadata"], {"plan": "ライト"})

    def test_invalid_plan_returns_400_without_querying_store(self):
        store = _StubUserProfileStore()
        result = create_checkout_session(
            "Bearer valid-token",
            verify_id_token=lambda token: "Uabc123",
            user_profile_store=store,
            plan="プレミアム",
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_plan")
        self.assertIsNone(result.checkout_session_params)
        self.assertEqual(store.get_stripe_customer_id_calls, [])

    def test_invalid_plan_check_happens_after_authentication(self):
        # 未認証(invalid_id_token)が先に検出され、プラン名の有効集合を推測させない(design 2節)。
        store = _StubUserProfileStore()
        result = create_checkout_session(
            "Bearer invalid-token",
            verify_id_token=lambda token: None,
            user_profile_store=store,
            plan="プレミアム",
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_id_token")


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
    (test_stripe_webhook._StubFlaskRequestと対称)。

    `args`(クエリパラメータ、フェーズ152で`plan`読み取りに追加)は省略可能。省略時、
    `main()`側は`getattr(request, "args", {})`で空dict扱いにフォールバックするため、
    `args`を持たない旧来のリクエストスタブでも従来通り動作する
    (既存テストが本引数無しのまま変更不要である所以)。
    """

    def __init__(self, headers: dict, args: dict = None):
        self.headers = headers
        if args is not None:
            self.args = args


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

    def test_request_with_plan_query_param_does_not_crash(self):
        # request.argsからのplan読み取り配線(フェーズ152)の回帰確認。verify_id_token自体は
        # 未実装のプレースホルダのままなので、plan値に関わらず結果は501のまま変わらない
        # (プラン検証はcreate_checkout_session()内でverify_id_token成功後に行われるため、
        # 本エントリポイントのテストではまだ到達しない)。
        request = _StubFlaskRequest(
            {"Authorization": "Bearer some-id-token"}, args={"plan": "ライト"}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 501)
        self.assertEqual(response_body, "verify_id_token_not_implemented")

    def test_request_without_args_attribute_falls_back_to_no_plan(self):
        # `args`を持たない旧来のリクエストスタブ(本ファイルの他テスト全て)でも
        # AttributeErrorにならず従来通り動作することの明示的な回帰確認。
        request = _StubFlaskRequest({"Authorization": "Bearer some-id-token"})
        self.assertFalse(hasattr(request, "args"))

        response_body, status_code = main(request)

        self.assertEqual(status_code, 501)


if __name__ == "__main__":
    unittest.main()
