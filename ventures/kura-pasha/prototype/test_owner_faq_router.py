#!/usr/bin/env python3
"""owner_faq_router.pyの単体テスト。
owner-faq-routing-design.md(フェーズ126)の仕様に沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from owner_faq_router import (  # noqa: E402
    is_owner_faq_menu_trigger,
    match_owner_faq_item_code,
    render_owner_faq_answer_message,
    render_owner_faq_menu_message,
)


class IsOwnerFaqMenuTriggerTests(unittest.TestCase):
    def test_exact_match(self):
        self.assertTrue(is_owner_faq_menu_trigger("FAQ"))

    def test_case_insensitive(self):
        self.assertTrue(is_owner_faq_menu_trigger("faq"))
        self.assertTrue(is_owner_faq_menu_trigger("Faq"))

    def test_surrounding_whitespace_ignored(self):
        self.assertTrue(is_owner_faq_menu_trigger("  FAQ  "))

    def test_none_is_false(self):
        self.assertFalse(is_owner_faq_menu_trigger(None))

    def test_unrelated_text_is_false(self):
        self.assertFalse(is_owner_faq_menu_trigger("鞍の修理をお願いします"))

    def test_partial_word_is_false(self):
        self.assertFalse(is_owner_faq_menu_trigger("FAQについて教えて"))


class MatchOwnerFaqItemCodeTests(unittest.TestCase):
    def test_all_eight_codes_match(self):
        for n in range(1, 9):
            with self.subTest(n=n):
                self.assertEqual(match_owner_faq_item_code(f"Q{n}"), f"Q{n}")

    def test_case_insensitive(self):
        self.assertEqual(match_owner_faq_item_code("q3"), "Q3")

    def test_surrounding_whitespace_ignored(self):
        self.assertEqual(match_owner_faq_item_code("  Q7  "), "Q7")

    def test_out_of_range_code_is_none(self):
        self.assertIsNone(match_owner_faq_item_code("Q9"))
        self.assertIsNone(match_owner_faq_item_code("Q0"))

    def test_none_is_none(self):
        self.assertIsNone(match_owner_faq_item_code(None))

    def test_unrelated_text_is_none(self):
        self.assertIsNone(match_owner_faq_item_code("鞍の修理をお願いします"))


class RenderOwnerFaqMenuMessageTests(unittest.TestCase):
    def test_contains_all_eight_headings_in_order(self):
        message = render_owner_faq_menu_message()
        lines = message.split("\n")
        codes_in_order = [line.split(".", 1)[0] for line in lines[1:]]
        self.assertEqual(codes_in_order, [f"Q{n}" for n in range(1, 9)])


class RenderOwnerFaqAnswerMessageTests(unittest.TestCase):
    def test_known_code_returns_heading_and_body(self):
        message = render_owner_faq_answer_message("Q1")
        self.assertTrue(message.startswith("Q1."))
        self.assertIn("カスタマーポータル", message)

    def test_unknown_code_raises_key_error(self):
        with self.assertRaises(KeyError):
            render_owner_faq_answer_message("Q9")

    def test_all_eight_codes_render_without_error(self):
        for n in range(1, 9):
            with self.subTest(n=n):
                message = render_owner_faq_answer_message(f"Q{n}")
                self.assertIn(f"Q{n}.", message)


if __name__ == "__main__":
    unittest.main()
