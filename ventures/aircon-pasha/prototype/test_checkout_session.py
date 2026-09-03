#!/usr/bin/env python3
"""checkout_session.pyの単体テスト。
checkout-initiation-flow-design.md(フェーズ131)のパラメータ組み立てルールに沿った挙動を
確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import (  # noqa: E402
    DEFAULT_CANCEL_URL,
    DEFAULT_CHECKOUT_PLAN,
    DEFAULT_SUCCESS_URL,
    PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER,
    START_CHECKOUT_POSTBACK_DATA,
    build_checkout_session_params,
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

    def test_falsy_existing_customer_id_is_ignored(self):
        params = build_checkout_session_params("Uabc123", existing_stripe_customer_id="")
        self.assertNotIn("customer", params)

    def test_success_and_cancel_url_can_be_overridden(self):
        params = build_checkout_session_params(
            "Uabc123",
            success_url="https://example.com/custom/success",
            cancel_url="https://example.com/custom/cancel",
        )
        self.assertEqual(params["success_url"], "https://example.com/custom/success")
        self.assertEqual(params["cancel_url"], "https://example.com/custom/cancel")

    def test_default_plan_is_used_when_omitted(self):
        params = build_checkout_session_params("Uabc123")
        self.assertEqual(
            params["line_items"],
            [{"price": PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER[DEFAULT_CHECKOUT_PLAN], "quantity": 1}],
        )

    def test_explicit_plan_selects_matching_price(self):
        params = build_checkout_session_params("Uabc123", plan="スモール")
        self.assertEqual(
            params["line_items"],
            [{"price": PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER["スモール"], "quantity": 1}],
        )

    def test_busy_plan_selects_matching_price(self):
        params = build_checkout_session_params("Uabc123", plan="繁忙期対応")
        self.assertEqual(
            params["line_items"],
            [{"price": PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER["繁忙期対応"], "quantity": 1}],
        )

    def test_raises_on_unknown_plan(self):
        with self.assertRaises(ValueError):
            build_checkout_session_params("Uabc123", plan="プレミアム")

    def test_line_items_present_even_for_existing_customer(self):
        params = build_checkout_session_params(
            "Uabc123", existing_stripe_customer_id="cus_existing456"
        )
        self.assertIn("line_items", params)


class StartCheckoutPostbackDataTest(unittest.TestCase):
    def test_postback_data_constant_matches_design(self):
        # checkout-initiation-flow-design.md 2節: トライアル終了通知メッセージ内の
        # postbackボタンに埋め込む固定データ。
        self.assertEqual(START_CHECKOUT_POSTBACK_DATA, "action=start_checkout")


if __name__ == "__main__":
    unittest.main()
