#!/usr/bin/env python3
"""checkout_session.pyの単体テスト。
checkout-initiation-flow-design.mdのパラメータ・リンク組み立てルールに沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import (  # noqa: E402
    DEFAULT_CANCEL_URL,
    DEFAULT_SUCCESS_URL,
    build_checkout_session_params,
    build_line_return_link,
)


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


if __name__ == "__main__":
    unittest.main()
