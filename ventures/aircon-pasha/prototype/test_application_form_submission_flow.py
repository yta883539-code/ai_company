#!/usr/bin/env python3
"""application_form_submission_flow.pyの単体テスト。
user-account-linking-design.md 2節・5節の「GAS Webhookペイロード検証→連携コード発行への
委譲」フローの仕様に沿った挙動を確認する。"""

import random
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from application_form_submission_flow import handle_form_submission  # noqa: E402
from user_id_linking import InMemoryLinkingCodeStore  # noqa: E402

_NOW = datetime(2026, 8, 23, 12, 0, 0)

_VALID_PAYLOAD = {
    "form_submission_id": "form-1",
    "business_name": "テストクリーニング",
    "business_type": "独立系",
    "email": "owner@example.com",
}


class HandleFormSubmissionSuccessTest(unittest.TestCase):
    def test_issues_a_linking_code_and_returns_ok(self):
        store = InMemoryLinkingCodeStore()
        result = handle_form_submission(_VALID_PAYLOAD, store, _NOW, random.Random(1))
        self.assertTrue(result.ok)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.linking_code), 6)

    def test_saved_pending_link_matches_payload_fields(self):
        store = InMemoryLinkingCodeStore()
        result = handle_form_submission(_VALID_PAYLOAD, store, _NOW, random.Random(2))
        entry = store.get(result.linking_code)
        self.assertEqual(entry.form_submission_id, "form-1")
        self.assertEqual(entry.business_name, "テストクリーニング")
        self.assertEqual(entry.business_type, "独立系")
        self.assertEqual(entry.email, "owner@example.com")
        self.assertEqual(entry.issued_at, _NOW)

    def test_strips_surrounding_whitespace_from_fields(self):
        store = InMemoryLinkingCodeStore()
        payload = {
            "form_submission_id": "  form-3  ",
            "business_name": "  テストクリーニング  ",
            "business_type": " 独立系 ",
            "email": "  owner@example.com  ",
        }
        result = handle_form_submission(payload, store, _NOW, random.Random(3))
        entry = store.get(result.linking_code)
        self.assertEqual(entry.form_submission_id, "form-3")
        self.assertEqual(entry.business_name, "テストクリーニング")
        self.assertEqual(entry.business_type, "独立系")
        self.assertEqual(entry.email, "owner@example.com")

    def test_two_submissions_issue_two_distinct_codes(self):
        store = InMemoryLinkingCodeStore()
        first = handle_form_submission(_VALID_PAYLOAD, store, _NOW, random.Random(4))
        second = handle_form_submission(_VALID_PAYLOAD, store, _NOW, random.Random(5))
        self.assertNotEqual(first.linking_code, second.linking_code)
        self.assertIsNotNone(store.get(first.linking_code))
        self.assertIsNotNone(store.get(second.linking_code))


class HandleFormSubmissionValidationTest(unittest.TestCase):
    def _assert_rejects(self, payload, expected_field):
        store = InMemoryLinkingCodeStore()
        result = handle_form_submission(payload, store, _NOW, random.Random(1))
        self.assertFalse(result.ok)
        self.assertIsNone(result.linking_code)
        self.assertIn(expected_field, result.error)

    def test_missing_form_submission_id_is_rejected(self):
        payload = dict(_VALID_PAYLOAD)
        del payload["form_submission_id"]
        self._assert_rejects(payload, "form_submission_id")

    def test_blank_business_name_is_rejected(self):
        payload = dict(_VALID_PAYLOAD, business_name="   ")
        self._assert_rejects(payload, "business_name")

    def test_missing_business_type_is_rejected(self):
        payload = dict(_VALID_PAYLOAD)
        del payload["business_type"]
        self._assert_rejects(payload, "business_type")

    def test_non_string_email_is_rejected(self):
        payload = dict(_VALID_PAYLOAD, email=12345)
        self._assert_rejects(payload, "email")

    def test_blank_email_is_rejected(self):
        payload = dict(_VALID_PAYLOAD, email="")
        self._assert_rejects(payload, "email")

    def test_rejection_does_not_save_any_pending_link(self):
        store = InMemoryLinkingCodeStore()
        payload = dict(_VALID_PAYLOAD, business_name="")
        handle_form_submission(payload, store, _NOW, random.Random(1))
        self.assertEqual(list(store.items()), [])


if __name__ == "__main__":
    unittest.main()
