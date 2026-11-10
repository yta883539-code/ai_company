#!/usr/bin/env python3
"""cloud_function_submit_event_form.pyの机上テスト(実Cloud Functions環境・実クラウド
接続なし)。python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype
-p "test_*.py"から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import json
import unittest

from cloud_function_submit_event_form import main


class _StubRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def get_data(self) -> bytes:
        return self._body


class MainTest(unittest.TestCase):
    def test_valid_submission_returns_200_with_checkout_url(self):
        body_bytes = json.dumps(
            {
                "capacity": "300人",
                "entry_exit_points": "入場口2・退場口1",
                "admission_type": "自由入場",
            }
        ).encode("utf-8")
        body, status_code = main(_StubRequest(body_bytes))
        self.assertEqual(status_code, 200)
        parsed = json.loads(body)
        self.assertTrue(parsed["ok"])
        self.assertIsNotNone(parsed["checkout_url"])

    def test_missing_fields_returns_200_insufficient_input(self):
        body_bytes = json.dumps({"capacity": "300人"}).encode("utf-8")
        body, status_code = main(_StubRequest(body_bytes))
        self.assertEqual(status_code, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["status"], "insufficient_input")

    def test_invalid_json_returns_400(self):
        body, status_code = main(_StubRequest(b"not json"))
        self.assertEqual(status_code, 400)


if __name__ == "__main__":
    unittest.main()
