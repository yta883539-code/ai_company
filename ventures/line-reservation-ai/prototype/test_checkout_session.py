#!/usr/bin/env python3
"""checkout_session.pyの単体テスト。
checkout-initiation-flow-design.mdのパラメータ・リンク組み立てルールに沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import (  # noqa: E402
    AUTHORIZATION_DENIED_OWNER_NOT_SET,
    AUTHORIZATION_DENIED_USER_ID_MISMATCH,
    DEFAULT_CANCEL_URL,
    DEFAULT_LIFF_ID,
    DEFAULT_LINE_BASIC_ID,
    DEFAULT_SUCCESS_URL,
    build_checkout_session_params,
    build_liff_checkout_link,
    build_line_return_link,
    create_checkout_session,
    get_checkout_runtime_dependencies,
    main,
    render_checkout_authorization_error_page,
    verify_checkout_authorization,
)
from store_profile_store import InMemoryStoreProfileStore  # noqa: E402


class BuildCheckoutSessionParamsTest(unittest.TestCase):
    def test_raises_on_empty_user_id(self):
        with self.assertRaises(ValueError):
            build_checkout_session_params("")

    def test_raises_on_none_user_id(self):
        with self.assertRaises(ValueError):
            build_checkout_session_params(None)

    def test_new_customer_has_no_customer_key(self):
        params = build_checkout_session_params("Uowner123")
        self.assertEqual(params["mode"], "subscription")
        self.assertEqual(params["client_reference_id"], "Uowner123")
        self.assertEqual(params["success_url"], DEFAULT_SUCCESS_URL)
        self.assertEqual(params["cancel_url"], DEFAULT_CANCEL_URL)
        self.assertNotIn("customer", params)

    def test_existing_customer_is_reused(self):
        params = build_checkout_session_params(
            "Uowner123", existing_stripe_customer_id="cus_existing456"
        )
        self.assertEqual(params["customer"], "cus_existing456")
        self.assertEqual(params["client_reference_id"], "Uowner123")

    def test_custom_success_and_cancel_urls_are_used(self):
        params = build_checkout_session_params(
            "Uowner123",
            success_url="https://example.com/ok",
            cancel_url="https://example.com/ng",
        )
        self.assertEqual(params["success_url"], "https://example.com/ok")
        self.assertEqual(params["cancel_url"], "https://example.com/ng")


class BuildLineReturnLinkTest(unittest.TestCase):
    def test_raises_on_empty_basic_id(self):
        with self.assertRaises(ValueError):
            build_line_return_link("")

    def test_raises_on_none_basic_id(self):
        with self.assertRaises(ValueError):
            build_line_return_link(None)

    def test_builds_universal_link_for_basic_id(self):
        link = build_line_return_link("@abc1234")
        self.assertEqual(link, "https://line.me/R/ti/p/%40abc1234")

    def test_percent_encodes_special_characters(self):
        link = build_line_return_link("@ab c")
        self.assertTrue(link.startswith("https://line.me/R/ti/p/"))
        self.assertIn("%40ab%20c", link)


class BuildLiffCheckoutLinkTest(unittest.TestCase):
    def test_raises_on_empty_store_id(self):
        with self.assertRaises(ValueError):
            build_liff_checkout_link("")

    def test_raises_on_none_store_id(self):
        with self.assertRaises(ValueError):
            build_liff_checkout_link(None)

    def test_builds_link_with_default_liff_id_and_store_id_param(self):
        link = build_liff_checkout_link("Ustore123")
        self.assertEqual(
            link, f"https://liff.line.me/{DEFAULT_LIFF_ID}?store_id=Ustore123"
        )

    def test_custom_liff_id_is_used(self):
        link = build_liff_checkout_link("Ustore123", liff_id="1234567890-abcdefgh")
        self.assertTrue(link.startswith("https://liff.line.me/1234567890-abcdefgh?"))

    def test_percent_encodes_special_characters_in_store_id(self):
        link = build_liff_checkout_link("Ustore 123")
        self.assertIn("store_id=Ustore%20123", link)

    def test_different_stores_get_different_links(self):
        link_a = build_liff_checkout_link("UstoreA")
        link_b = build_liff_checkout_link("UstoreB")
        self.assertNotEqual(link_a, link_b)


class VerifyCheckoutAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStoreProfileStore()

    def test_raises_on_empty_store_id(self):
        with self.assertRaises(ValueError):
            verify_checkout_authorization("", "Uowner123", self.store)

    def test_raises_on_empty_requester_user_id(self):
        with self.assertRaises(ValueError):
            verify_checkout_authorization("store123", "", self.store)

    def test_denied_when_owner_user_id_not_set(self):
        result = verify_checkout_authorization("store123", "Uowner123", self.store)
        self.assertFalse(result.authorized)
        self.assertEqual(result.denied_reason, AUTHORIZATION_DENIED_OWNER_NOT_SET)

    def test_denied_when_requester_does_not_match_owner(self):
        self.store.set_owner_user_id("store123", "Uowner123")
        result = verify_checkout_authorization("store123", "Ucustomer999", self.store)
        self.assertFalse(result.authorized)
        self.assertEqual(result.denied_reason, AUTHORIZATION_DENIED_USER_ID_MISMATCH)

    def test_authorized_when_requester_matches_owner(self):
        self.store.set_owner_user_id("store123", "Uowner123")
        result = verify_checkout_authorization("store123", "Uowner123", self.store)
        self.assertTrue(result.authorized)
        self.assertIsNone(result.denied_reason)

    def test_different_stores_have_independent_owners(self):
        self.store.set_owner_user_id("store123", "Uowner123")
        self.store.set_owner_user_id("store456", "Uowner456")
        result = verify_checkout_authorization("store456", "Uowner123", self.store)
        self.assertFalse(result.authorized)
        self.assertEqual(result.denied_reason, AUTHORIZATION_DENIED_USER_ID_MISMATCH)


class RenderCheckoutAuthorizationErrorPageTest(unittest.TestCase):
    def test_raises_on_unknown_denied_reason(self):
        with self.assertRaises(ValueError):
            render_checkout_authorization_error_page(
                "unknown_reason", "https://line.me/R/ti/p/%40abc1234"
            )

    def test_raises_on_empty_line_return_link(self):
        with self.assertRaises(ValueError):
            render_checkout_authorization_error_page(
                AUTHORIZATION_DENIED_OWNER_NOT_SET, ""
            )

    def test_owner_not_set_message_mentions_connection_test(self):
        page = render_checkout_authorization_error_page(
            AUTHORIZATION_DENIED_OWNER_NOT_SET, "https://line.me/R/ti/p/%40abc1234"
        )
        self.assertIn("接続テスト", page)
        self.assertIn("https://line.me/R/ti/p/%40abc1234", page)

    def test_user_id_mismatch_message_mentions_owner_account(self):
        page = render_checkout_authorization_error_page(
            AUTHORIZATION_DENIED_USER_ID_MISMATCH, "https://line.me/R/ti/p/%40abc1234"
        )
        self.assertIn("オーナー様ご本人", page)
        self.assertIn("https://line.me/R/ti/p/%40abc1234", page)


_VALID_LINE_RETURN_LINK = "https://line.me/R/ti/p/%40abc1234"


class CreateCheckoutSessionTest(unittest.TestCase):
    """create_checkout_session()(design 9節手順1〜4・10節を結ぶエンドポイント本体、
    フェーズ続き174新設)のテスト。"""

    def setUp(self):
        self.store = InMemoryStoreProfileStore()

    def test_missing_store_id_returns_400_without_touching_authorization(self):
        verify_calls = []
        result = create_checkout_session(
            None,
            "Bearer some-token",
            verify_id_token=lambda token: verify_calls.append(token) or "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "missing_store_id")
        self.assertIsNone(result.checkout_session_params)
        self.assertEqual(verify_calls, [])

    def test_empty_store_id_returns_400(self):
        result = create_checkout_session(
            "",
            "Bearer some-token",
            verify_id_token=lambda token: "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "missing_store_id")

    def test_missing_authorization_header_returns_401_without_verifying(self):
        verify_calls = []
        result = create_checkout_session(
            "store123",
            None,
            verify_id_token=lambda token: verify_calls.append(token) or "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "missing_or_malformed_authorization_header")
        self.assertEqual(verify_calls, [])

    def test_non_bearer_authorization_header_returns_401_without_verifying(self):
        verify_calls = []
        result = create_checkout_session(
            "store123",
            "Basic xxx",
            verify_id_token=lambda token: verify_calls.append(token) or "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "missing_or_malformed_authorization_header")
        self.assertEqual(verify_calls, [])

    def test_invalid_id_token_returns_401_without_authorization_check(self):
        result = create_checkout_session(
            "store123",
            "Bearer invalid-token",
            verify_id_token=lambda token: None,
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_id_token")
        self.assertIsNone(result.checkout_session_params)

    def test_owner_not_set_returns_403_with_error_page(self):
        result = create_checkout_session(
            "store123",
            "Bearer valid-token",
            verify_id_token=lambda token: "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 403)
        self.assertIsNone(result.checkout_session_params)
        self.assertIn("接続テスト", result.error_page)
        self.assertIn(_VALID_LINE_RETURN_LINK, result.error_page)

    def test_user_id_mismatch_returns_403_with_error_page(self):
        self.store.set_owner_user_id("store123", "Uowner123")
        result = create_checkout_session(
            "store123",
            "Bearer valid-token",
            verify_id_token=lambda token: "Ucustomer999",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 403)
        self.assertIsNone(result.checkout_session_params)
        self.assertIn("オーナー様ご本人", result.error_page)

    def test_authorized_new_store_gets_200_without_customer_key(self):
        self.store.set_owner_user_id("store123", "Uowner123")
        result = create_checkout_session(
            "store123",
            "Bearer valid-token",
            verify_id_token=lambda token: "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)
        self.assertIsNone(result.error_page)
        self.assertEqual(result.checkout_session_params["client_reference_id"], "store123")
        self.assertNotIn("customer", result.checkout_session_params)

    def test_authorized_existing_customer_is_reused(self):
        self.store.set_owner_user_id("store123", "Uowner123")
        self.store.set_stripe_customer_id("store123", "cus_existing456")
        result = create_checkout_session(
            "store123",
            "Bearer valid-token",
            verify_id_token=lambda token: "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.checkout_session_params["customer"], "cus_existing456")

    def test_custom_success_and_cancel_urls_are_propagated(self):
        self.store.set_owner_user_id("store123", "Uowner123")
        result = create_checkout_session(
            "store123",
            "Bearer valid-token",
            verify_id_token=lambda token: "Uowner123",
            store=self.store,
            line_return_link=_VALID_LINE_RETURN_LINK,
            success_url="https://example.com/ok",
            cancel_url="https://example.com/ng",
        )
        self.assertEqual(result.checkout_session_params["success_url"], "https://example.com/ok")
        self.assertEqual(result.checkout_session_params["cancel_url"], "https://example.com/ng")


class GetCheckoutRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_store_verify_id_token_placeholder_and_line_return_link(self):
        deps = get_checkout_runtime_dependencies()
        self.assertIn("store", deps)
        self.assertIn("verify_id_token", deps)
        self.assertIn("line_return_link", deps)
        self.assertIsNone(deps["store"].get_stripe_customer_id("store123"))
        with self.assertRaises(NotImplementedError):
            deps["verify_id_token"]("some-id-token")
        self.assertEqual(
            deps["line_return_link"],
            build_line_return_link(DEFAULT_LINE_BASIC_ID),
        )


class _StubQueryArgs:
    """Flask Requestの`request.args`(MultiDict)相当の必要最小限のスタブ。"""

    def __init__(self, args: dict):
        self._args = args

    def get(self, key):
        return self._args.get(key)


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (course-set-pasha/test_checkout_session._StubFlaskRequestと対称)。"""

    def __init__(self, headers: dict, args: dict = None):
        self.headers = headers
        self.args = _StubQueryArgs(args or {})


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント)のテスト。design 9節手順1の
    `store_id`クエリパラメータ取り出し配線・verify_id_token未実装時の501分岐を検証する
    (create_checkout_session()自体の分岐はCreateCheckoutSessionTestで既にカバー済み)。"""

    def test_missing_store_id_returns_400(self):
        request = _StubFlaskRequest({"Authorization": "Bearer some-token"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 400)
        self.assertEqual(response_body, "missing_store_id")

    def test_missing_authorization_header_returns_401(self):
        request = _StubFlaskRequest({}, args={"store_id": "store123"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)
        self.assertEqual(response_body, "missing_or_malformed_authorization_header")

    def test_non_bearer_authorization_header_returns_401(self):
        request = _StubFlaskRequest(
            {"Authorization": "Basic xxx"}, args={"store_id": "store123"}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)
        self.assertEqual(response_body, "missing_or_malformed_authorization_header")

    def test_well_formed_bearer_header_returns_501_pending_verify_id_token(self):
        request = _StubFlaskRequest(
            {"Authorization": "Bearer some-id-token"}, args={"store_id": "store123"}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 501)
        self.assertEqual(response_body, "verify_id_token_not_implemented")


if __name__ == "__main__":
    unittest.main()
