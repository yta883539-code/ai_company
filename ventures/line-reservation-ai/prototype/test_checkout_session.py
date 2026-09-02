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
    DEFAULT_SUCCESS_URL,
    build_checkout_session_params,
    build_liff_checkout_link,
    build_line_return_link,
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


if __name__ == "__main__":
    unittest.main()
