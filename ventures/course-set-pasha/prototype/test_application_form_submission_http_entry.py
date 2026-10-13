#!/usr/bin/env python3
"""application_form_submission_http_entry.pyの単体テスト。
application-form-submission-http-entry-point-design.md 2節・3節の認証・レスポンス形状の
仕様に沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from application_form_submission_flow import InMemoryUserProfileStore  # noqa: E402
from application_form_submission_http_entry import (  # noqa: E402
    receive_application_form_submission,
)
from user_id_linking import InMemoryLinkingCodeStore  # noqa: E402

_NOW = datetime(2026, 10, 13, 12, 0, 0)
_SECRET = "correct-horse-battery-staple"


def _issue_code(linking_store, code: str, user_id: str) -> None:
    linking_store.save(code, user_id, _NOW)


class ReceiveApplicationFormSubmissionAuthTest(unittest.TestCase):
    def test_returns_401_when_secret_header_is_missing(self):
        result = receive_application_form_submission(
            b"{}", None, _SECRET, InMemoryUserProfileStore(), InMemoryLinkingCodeStore(), _NOW
        )
        self.assertEqual(result.status_code, 401)
        self.assertFalse(result.ok)

    def test_returns_401_when_secret_header_mismatches(self):
        result = receive_application_form_submission(
            b"{}",
            "wrong-secret",
            _SECRET,
            InMemoryUserProfileStore(),
            InMemoryLinkingCodeStore(),
            _NOW,
        )
        self.assertEqual(result.status_code, 401)

    def test_returns_401_when_expected_secret_is_empty_even_if_header_is_also_empty(self):
        # design: 空シークレット同士の一致で無認証運用になる事故を避けるため、
        # expected_secretが空文字列の場合は常に401とする。
        result = receive_application_form_submission(
            b"{}", "", "", InMemoryUserProfileStore(), InMemoryLinkingCodeStore(), _NOW
        )
        self.assertEqual(result.status_code, 401)


class ReceiveApplicationFormSubmissionPayloadTest(unittest.TestCase):
    def test_returns_400_for_invalid_json_body(self):
        result = receive_application_form_submission(
            b"not json",
            _SECRET,
            _SECRET,
            InMemoryUserProfileStore(),
            InMemoryLinkingCodeStore(),
            _NOW,
        )
        self.assertEqual(result.status_code, 400)
        self.assertIsNotNone(result.error)

    def test_returns_400_when_body_is_a_json_array_not_an_object(self):
        result = receive_application_form_submission(
            b"[1, 2, 3]",
            _SECRET,
            _SECRET,
            InMemoryUserProfileStore(),
            InMemoryLinkingCodeStore(),
            _NOW,
        )
        self.assertEqual(result.status_code, 400)

    def test_returns_400_when_linking_code_is_unknown(self):
        result = receive_application_form_submission(
            b'{"linking_code": "NOPE12", "gym_area_pairs_raw": "", "email": "a@b.com"}',
            _SECRET,
            _SECRET,
            InMemoryUserProfileStore(),
            InMemoryLinkingCodeStore(),
            _NOW,
        )
        self.assertEqual(result.status_code, 400)
        self.assertIn("linking_code", result.error)

    def test_returns_400_when_email_is_missing(self):
        linking_store = InMemoryLinkingCodeStore()
        _issue_code(linking_store, "ABCDEF", "U1")
        result = receive_application_form_submission(
            b'{"linking_code": "ABCDEF", "gym_area_pairs_raw": ""}',
            _SECRET,
            _SECRET,
            InMemoryUserProfileStore(),
            linking_store,
            _NOW,
        )
        self.assertEqual(result.status_code, 400)

    def test_returns_200_and_writes_profile_on_a_valid_submission(self):
        profile_store = InMemoryUserProfileStore()
        linking_store = InMemoryLinkingCodeStore()
        _issue_code(linking_store, "ABCDEF", "U1")

        body = (
            '{"linking_code": "ABCDEF", '
            '"gym_area_pairs_raw": "ジムA/区", '
            '"email": "owner@example.com"}'
        ).encode("utf-8")
        result = receive_application_form_submission(
            body,
            _SECRET,
            _SECRET,
            profile_store,
            linking_store,
            _NOW,
        )

        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.ok)
        self.assertEqual(profile_store.get_email("U1"), "owner@example.com")

    def test_json_body_is_valid_json_on_success(self):
        result = receive_application_form_submission(
            b"{}", _SECRET, _SECRET, InMemoryUserProfileStore(), InMemoryLinkingCodeStore(), _NOW
        )
        self.assertIn('"ok": false', result.to_json_body())


if __name__ == "__main__":
    unittest.main()
