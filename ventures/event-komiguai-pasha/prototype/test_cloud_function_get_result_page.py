#!/usr/bin/env python3
"""cloud_function_get_result_page.pyの机上テスト(実Cloud Functions環境・実クラウド
接続なし)。python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype
-p "test_*.py"から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import json
import unittest

from cloud_function_get_result_page import main


class _StubRequest:
    def __init__(self, path: str) -> None:
        self.path = path


class MainTest(unittest.TestCase):
    def test_unknown_draft_id_returns_200_ttl_expired_state(self):
        body, status_code = main(_StubRequest("/result/draft_never_existed"))
        self.assertEqual(status_code, 200)
        parsed = json.loads(body)
        self.assertEqual(parsed["page_state"], "ttl_expired_or_invalid")

    def test_missing_draft_id_returns_400(self):
        body, status_code = main(_StubRequest("/result/"))
        self.assertEqual(status_code, 400)
        parsed = json.loads(body)
        self.assertFalse(parsed["ok"])


if __name__ == "__main__":
    unittest.main()
