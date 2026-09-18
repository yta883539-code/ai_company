#!/usr/bin/env python3
import unittest

from owner_faq_router import (
    is_owner_faq_menu_trigger,
    match_owner_faq_item_code,
    render_owner_faq_answer_message,
    render_owner_faq_menu_message,
)


class OwnerFaqTriggerTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(is_owner_faq_menu_trigger("FAQ"))

    def test_case_insensitive(self):
        self.assertTrue(is_owner_faq_menu_trigger("faq"))

    def test_ignores_surrounding_whitespace(self):
        self.assertTrue(is_owner_faq_menu_trigger("  FAQ  "))

    def test_unrelated_text_does_not_match(self):
        self.assertFalse(is_owner_faq_menu_trigger("FAQを見たい"))
        self.assertFalse(is_owner_faq_menu_trigger(""))

    def test_fullwidth_input_matches_via_nfkc_normalization(self):
        self.assertTrue(is_owner_faq_menu_trigger("ＦＡＱ"))
        self.assertTrue(is_owner_faq_menu_trigger("ｆａｑ"))
        self.assertTrue(is_owner_faq_menu_trigger("　ＦＡＱ　"))


class OwnerFaqItemCodeMatchTests(unittest.TestCase):
    def test_matches_all_known_codes_case_insensitively(self):
        for code in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"):
            with self.subTest(code=code):
                self.assertEqual(match_owner_faq_item_code(code), code)
                self.assertEqual(match_owner_faq_item_code(code.lower()), code)

    def test_ignores_surrounding_whitespace(self):
        self.assertEqual(match_owner_faq_item_code("  q1  "), "Q1")

    def test_unknown_code_returns_none(self):
        self.assertIsNone(match_owner_faq_item_code("Q8"))
        self.assertIsNone(match_owner_faq_item_code("Q"))
        self.assertIsNone(match_owner_faq_item_code(""))
        self.assertIsNone(match_owner_faq_item_code("エアコン 室外機 異音 型番不明"))

    def test_fullwidth_code_matches_via_nfkc_normalization(self):
        self.assertEqual(match_owner_faq_item_code("Ｑ１"), "Q1")
        self.assertEqual(match_owner_faq_item_code("ｑ３"), "Q3")


class OwnerFaqMenuMessageTests(unittest.TestCase):
    def test_menu_lists_all_seven_items_in_order(self):
        message = render_owner_faq_menu_message()
        positions = [message.index(f"Q{n}") for n in range(1, 8)]
        self.assertEqual(positions, sorted(positions))
        for n in range(1, 8):
            self.assertIn(f"Q{n}", message)


class OwnerFaqAnswerMessageTests(unittest.TestCase):
    def test_answer_includes_code_and_return_to_menu_hint(self):
        message = render_owner_faq_answer_message("Q3")
        self.assertTrue(message.startswith("Q3."))
        self.assertIn("解約", message)
        self.assertIn("FAQ", message)

    def test_btob_management_company_item_is_venture_specific(self):
        message = render_owner_faq_answer_message("Q6")
        self.assertTrue(message.startswith("Q6."))
        self.assertIn("管理会社", message)

    def test_all_known_codes_render_without_error(self):
        for code in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7"):
            with self.subTest(code=code):
                message = render_owner_faq_answer_message(code)
                self.assertTrue(message.startswith(f"{code}."))

    def test_unknown_code_raises_key_error(self):
        with self.assertRaises(KeyError):
            render_owner_faq_answer_message("Q9")


if __name__ == "__main__":
    unittest.main()
