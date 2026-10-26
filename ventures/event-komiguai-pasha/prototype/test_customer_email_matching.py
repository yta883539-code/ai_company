#!/usr/bin/env python3
"""customer_email_matching.pyの机上テスト(実LLM・実クラウド接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import unittest

from customer_email_matching import customer_emails_match, normalize_customer_email


class NormalizeCustomerEmailTest(unittest.TestCase):
    def test_strips_leading_and_trailing_half_width_space(self):
        self.assertEqual(normalize_customer_email("  foo@example.com  "), "foo@example.com")

    def test_strips_leading_and_trailing_full_width_space(self):
        self.assertEqual(normalize_customer_email("　foo@example.com　"), "foo@example.com")

    def test_lowercases_mixed_case_address(self):
        self.assertEqual(normalize_customer_email("Foo.BAR@Example.COM"), "foo.bar@example.com")

    def test_nfkc_normalizes_full_width_alphanumeric(self):
        self.assertEqual(normalize_customer_email("ｆｏｏ＠ｅｘａｍｐｌｅ．ｃｏｍ"), "foo@example.com")

    def test_nfkc_normalizes_full_width_digits(self):
        self.assertEqual(normalize_customer_email("foo１２３@example.com"), "foo123@example.com")

    def test_combination_of_full_width_space_case_and_full_width_at(self):
        self.assertEqual(
            normalize_customer_email("　Ｆｏｏ＠example.COM　"),
            "foo@example.com",
        )

    def test_whitespace_only_input_normalizes_to_empty_string(self):
        self.assertEqual(normalize_customer_email("   　  "), "")

    def test_empty_string_normalizes_to_empty_string(self):
        self.assertEqual(normalize_customer_email(""), "")


class CustomerEmailsMatchTest(unittest.TestCase):
    def test_identical_addresses_match(self):
        self.assertTrue(customer_emails_match("foo@example.com", "foo@example.com"))

    def test_case_difference_still_matches(self):
        self.assertTrue(customer_emails_match("Foo@Example.com", "foo@example.com"))

    def test_full_width_input_matches_half_width_input(self):
        self.assertTrue(customer_emails_match("ｆｏｏ＠ｅｘａｍｐｌｅ．ｃｏｍ", "foo@example.com"))

    def test_surrounding_whitespace_does_not_affect_match(self):
        self.assertTrue(customer_emails_match("  foo@example.com", "foo@example.com  "))

    def test_different_addresses_do_not_match(self):
        self.assertFalse(customer_emails_match("foo@example.com", "bar@example.com"))

    def test_both_empty_after_normalization_do_not_match(self):
        self.assertFalse(customer_emails_match("   ", "　"))

    def test_one_side_empty_after_normalization_does_not_match(self):
        self.assertFalse(customer_emails_match("", "foo@example.com"))


if __name__ == "__main__":
    unittest.main()
