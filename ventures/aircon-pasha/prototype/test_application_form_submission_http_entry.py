#!/usr/bin/env python3
"""application_form_submission_http_entry.pyの単体テスト。
application-form-submission-http-entry-point-design.md 3節・4節の認証・レスポンス形状の
仕様に沿った挙動を確認する。"""

import random
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from application_form_submission_http_entry import (  # noqa: E402
    receive_application_form_submission,
)
from user_id_linking import InMemoryLinkingCodeStore  # noqa: E402

_NOW = datetime(2026, 10, 15, 12, 0, 0)
_SECRET = "correct-horse-battery-staple"

_VALID_BODY = (
    '{"form_submission_id": "form-1", "business_name": "テストクリーニング", '
    '"business_type": "独立系", "email": "owner@example.com"}'
).encode("utf-8")


class ReceiveApplicationFormSubmissionAuthTest(unittest.TestCase):
    def test_returns_401_when_secret_header_is_missing(self):
        result = receive_application_form_submission(
            b"{}", None, _SECRET, InMemoryLinkingCodeStore(), _NOW, random.Random(1)
        )
        self.assertEqual(result.status_code, 401)
        self.assertFalse(result.ok)
        self.assertIsNone(result.linking_code)

    def test_returns_401_when_secret_header_mismatches(self):
        result = receive_application_form_submission(
            b"{}",
            "wrong-secret",
            _SECRET,
            InMemoryLinkingCodeStore(),
            _NOW,
            random.Random(1),
        )
        self.assertEqual(result.status_code, 401)

    def test_returns_401_when_expected_secret_is_empty_even_if_header_is_also_empty(self):
        # design: 空シークレット同士の一致で無認証運用になる事故を避けるため、
        # expected_secretが空文字列の場合は常に401とする。
        result = receive_application_form_submission(
            b"{}", "", "", InMemoryLinkingCodeStore(), _NOW, random.Random(1)
        )
        self.assertEqual(result.status_code, 401)

    def test_auth_failure_does_not_issue_a_linking_code(self):
        store = InMemoryLinkingCodeStore()
        receive_application_form_submission(
            _VALID_BODY, "wrong-secret", _SECRET, store, _NOW, random.Random(1)
        )
        self.assertEqual(list(store.items()), [])


class ReceiveApplicationFormSubmissionPayloadTest(unittest.TestCase):
    def test_returns_400_for_invalid_json_body(self):
        result = receive_application_form_submission(
            b"not json", _SECRET, _SECRET, InMemoryLinkingCodeStore(), _NOW, random.Random(1)
        )
        self.assertEqual(result.status_code, 400)
        self.assertIsNotNone(result.error)
        self.assertIsNone(result.linking_code)

    def test_returns_400_when_body_is_a_json_array_not_an_object(self):
        result = receive_application_form_submission(
            b"[1, 2, 3]", _SECRET, _SECRET, InMemoryLinkingCodeStore(), _NOW, random.Random(1)
        )
        self.assertEqual(result.status_code, 400)

    def test_returns_400_when_a_required_field_is_missing(self):
        body = (
            '{"business_name": "テストクリーニング", "business_type": "独立系", '
            '"email": "owner@example.com"}'
        ).encode("utf-8")
        result = receive_application_form_submission(
            body, _SECRET, _SECRET, InMemoryLinkingCodeStore(), _NOW, random.Random(1)
        )
        self.assertEqual(result.status_code, 400)
        self.assertIn("form_submission_id", result.error)

    def test_rejection_does_not_save_any_pending_link(self):
        body = '{"business_name": "テストクリーニング"}'.encode("utf-8")
        store = InMemoryLinkingCodeStore()
        receive_application_form_submission(body, _SECRET, _SECRET, store, _NOW, random.Random(1))
        self.assertEqual(list(store.items()), [])

    def test_returns_200_and_linking_code_on_a_valid_submission(self):
        store = InMemoryLinkingCodeStore()
        result = receive_application_form_submission(
            _VALID_BODY, _SECRET, _SECRET, store, _NOW, random.Random(1)
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.ok)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.linking_code), 6)

        entry = store.get(result.linking_code)
        self.assertEqual(entry.form_submission_id, "form-1")
        self.assertEqual(entry.business_name, "テストクリーニング")
        self.assertEqual(entry.business_type, "独立系")
        self.assertEqual(entry.email, "owner@example.com")
        self.assertEqual(entry.issued_at, _NOW)

    def test_two_submissions_issue_two_distinct_codes(self):
        store = InMemoryLinkingCodeStore()
        first = receive_application_form_submission(
            _VALID_BODY, _SECRET, _SECRET, store, _NOW, random.Random(1)
        )
        second = receive_application_form_submission(
            _VALID_BODY, _SECRET, _SECRET, store, _NOW, random.Random(2)
        )
        self.assertNotEqual(first.linking_code, second.linking_code)

    def test_json_body_is_valid_json_on_success(self):
        result = receive_application_form_submission(
            _VALID_BODY, _SECRET, _SECRET, InMemoryLinkingCodeStore(), _NOW, random.Random(1)
        )
        body = result.to_json_body()
        self.assertIn('"ok": true', body)
        self.assertIn(result.linking_code, body)

    def test_json_body_is_valid_json_on_failure(self):
        result = receive_application_form_submission(
            b"{}", _SECRET, _SECRET, InMemoryLinkingCodeStore(), _NOW, random.Random(1)
        )
        self.assertIn('"ok": false', result.to_json_body())
        self.assertIn('"linking_code": null', result.to_json_body())


if __name__ == "__main__":
    unittest.main()
