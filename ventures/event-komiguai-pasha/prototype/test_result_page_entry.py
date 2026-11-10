#!/usr/bin/env python3
"""result_page_entry.pyの机上テスト(実Firestore接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import json
import unittest

from result_page_entry import receive_result_page_request
from stripe_webhook import InMemoryOneTimeDraftStore


class ReceiveResultPageRequestTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryOneTimeDraftStore()

    def test_missing_draft_id_returns_400(self):
        result = receive_result_page_request("/result/", draft_store=self.store)
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.body["ok"])

    def test_empty_path_returns_400(self):
        result = receive_result_page_request("", draft_store=self.store)
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.body["ok"])

    def test_unknown_draft_id_returns_ttl_expired_state(self):
        result = receive_result_page_request(
            "/result/draft_never_existed", draft_store=self.store
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.body["ok"])
        self.assertEqual(result.body["page_state"], "ttl_expired_or_invalid")
        self.assertIsNone(result.body["output"])

    def test_awaiting_payment_returns_generating_state(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        result = receive_result_page_request("/result/draft_abc", draft_store=self.store)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.body["page_state"], "generating")
        self.assertIsNone(result.body["output"])

    def test_generated_returns_output(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        output = {"status": "generated", "checklist": [{"item": "確認", "highlighted": False}]}
        self.store.mark_generation_result("draft_abc", status="generated", output=output)

        result = receive_result_page_request("/result/draft_abc", draft_store=self.store)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.body["page_state"], "generated")
        self.assertEqual(result.body["output"], output)

    def test_out_of_scope_returns_output(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        output = {"status": "out_of_scope", "out_of_scope_message": "対応範囲外です"}
        self.store.mark_generation_result("draft_abc", status="out_of_scope", output=output)

        result = receive_result_page_request("/result/draft_abc", draft_store=self.store)
        self.assertEqual(result.body["page_state"], "out_of_scope")
        self.assertEqual(result.body["output"], output)

    def test_insufficient_input_returns_output(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        output = {"status": "insufficient_input", "missing_fields_request": "入退場口が未入力です"}
        self.store.mark_generation_result(
            "draft_abc", status="insufficient_input", output=output
        )

        result = receive_result_page_request("/result/draft_abc", draft_store=self.store)
        self.assertEqual(result.body["page_state"], "insufficient_input")
        self.assertEqual(result.body["output"], output)

    def test_generation_failed_returns_state_without_output(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        self.store.mark_generation_result("draft_abc", status="generation_failed")

        result = receive_result_page_request("/result/draft_abc", draft_store=self.store)
        self.assertEqual(result.body["page_state"], "generation_failed")
        self.assertIsNone(result.body["output"])

    def test_refunded_returns_state(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        self.store.mark_generation_result("draft_abc", status="refunded")

        result = receive_result_page_request("/result/draft_abc", draft_store=self.store)
        self.assertEqual(result.body["page_state"], "refunded")

    def test_expired_after_payment_returns_state(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        self.store.mark_expired_after_payment("draft_abc")

        result = receive_result_page_request("/result/draft_abc", draft_store=self.store)
        self.assertEqual(result.body["page_state"], "expired_after_payment")

    def test_trailing_slash_in_path_is_tolerated(self):
        self.store.create_draft("draft_abc", event_memo={"capacity": "300人"})
        result = receive_result_page_request("/result/draft_abc/", draft_store=self.store)
        self.assertEqual(result.body["page_state"], "generating")

    def test_to_json_body_shape(self):
        result = receive_result_page_request(
            "/result/draft_never_existed", draft_store=self.store
        )
        parsed = json.loads(result.to_json_body())
        self.assertEqual(set(parsed.keys()), {"ok", "page_state", "output"})


if __name__ == "__main__":
    unittest.main()
