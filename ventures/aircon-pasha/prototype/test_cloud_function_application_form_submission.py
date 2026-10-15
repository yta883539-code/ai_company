#!/usr/bin/env python3
"""cloud_function_application_form_submission.pyのテスト(README.mdフェーズ316)。

main()固有の配線部分(環境変数・ヘッダ取り出し、依存のデフォルト組み立て)に絞り、
認証・ペイロード検証自体のロジックはtest_application_form_submission_http_entry.pyで
既にカバー済みのため、ここでは重複させない。
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_function_application_form_submission import (  # noqa: E402
    get_application_form_submission_runtime_dependencies,
    main,
)
from user_id_linking import InMemoryLinkingCodeStore  # noqa: E402

_ENV_VAR = "FORM_WEBHOOK_SHARED_SECRET"


class _StubRequest:
    def __init__(self, body: bytes, headers: dict) -> None:
        self._body = body
        self.headers = headers

    def get_data(self) -> bytes:
        return self._body


class GetRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_an_in_memory_store(self):
        deps = get_application_form_submission_runtime_dependencies()

        self.assertIsInstance(deps["store"], InMemoryLinkingCodeStore)

    def test_each_call_returns_a_fresh_store_instance(self):
        deps1 = get_application_form_submission_runtime_dependencies()
        deps2 = get_application_form_submission_runtime_dependencies()

        self.assertIsNot(deps1["store"], deps2["store"])


class MainEntryPointTest(unittest.TestCase):
    def setUp(self):
        self._original_env = os.environ.get(_ENV_VAR)
        os.environ[_ENV_VAR] = "test-secret"

    def tearDown(self):
        if self._original_env is None:
            os.environ.pop(_ENV_VAR, None)
        else:
            os.environ[_ENV_VAR] = self._original_env

    def test_returns_401_when_header_missing(self):
        body, status_code = main(_StubRequest(b"{}", {}))

        self.assertEqual(status_code, 401)

    def test_returns_401_when_env_var_is_unset(self):
        os.environ.pop(_ENV_VAR, None)
        body, status_code = main(
            _StubRequest(b"{}", {"X-Form-Webhook-Secret": "test-secret"})
        )

        self.assertEqual(status_code, 401)

    def test_returns_200_and_a_linking_code_with_correct_secret(self):
        body, status_code = main(
            _StubRequest(
                (
                    '{"form_submission_id": "form-1", "business_name": "テスト", '
                    '"business_type": "独立系", "email": "a@b.com"}'
                ).encode("utf-8"),
                {"X-Form-Webhook-Secret": "test-secret"},
            )
        )

        self.assertEqual(status_code, 200)
        self.assertIn('"ok": true', body)

    def test_returns_400_for_missing_field_with_correct_secret(self):
        body, status_code = main(
            _StubRequest(
                '{"business_name": "テスト"}'.encode("utf-8"),
                {"X-Form-Webhook-Secret": "test-secret"},
            )
        )

        self.assertEqual(status_code, 400)

    def test_does_not_raise_when_called_repeatedly(self):
        for _ in range(3):
            body, status_code = main(_StubRequest(b"not json", {}))
            self.assertEqual(status_code, 401)


if __name__ == "__main__":
    unittest.main()
