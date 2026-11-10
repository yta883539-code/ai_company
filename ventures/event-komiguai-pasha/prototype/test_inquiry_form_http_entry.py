#!/usr/bin/env python3
"""inquiry_form_http_entry.pyの机上テスト(実Firestore接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import json
import unittest
from datetime import datetime, timezone

from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore
from inquiry_collection_store import InMemoryInquiryCollection
from inquiry_form_http_entry import receive_inquiry_form_submission

FIXED_NOW = datetime(2026, 11, 10, 6, 0, 0, tzinfo=timezone.utc)

VALID_BODY = json.dumps(
    {
        "draft_id": "draft-abc123",
        "customer_email": "customer@example.com",
        "category": "メール未着",
        "detail": "確認メールが届きません",
    }
).encode("utf-8")


class ReceiveInquiryFormSubmissionTest(unittest.TestCase):
    def test_invalid_json_returns_400(self):
        result = receive_inquiry_form_submission(
            b"not json", collection=InMemoryInquiryCollection(), now=FIXED_NOW
        )
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.ok)
        self.assertIsNone(result.inquiry_id)

    def test_non_object_json_returns_400(self):
        result = receive_inquiry_form_submission(
            b"[1, 2, 3]", collection=InMemoryInquiryCollection(), now=FIXED_NOW
        )
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.ok)

    def test_missing_required_fields_returns_400_without_writing(self):
        collection = InMemoryInquiryCollection()
        body = json.dumps({"draft_id": "draft-1"}).encode("utf-8")
        result = receive_inquiry_form_submission(body, collection=collection, now=FIXED_NOW)
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertEqual(collection._documents, {})

    def test_valid_submission_writes_document_and_returns_200(self):
        collection = InMemoryInquiryCollection()
        result = receive_inquiry_form_submission(
            VALID_BODY, collection=collection, now=FIXED_NOW
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.inquiry_id)
        written = collection.get(result.inquiry_id)
        self.assertIsNotNone(written)
        self.assertEqual(written["draft_id"], "draft-abc123")
        self.assertEqual(written["customer_email"], "customer@example.com")
        self.assertEqual(written["created_at"], FIXED_NOW.isoformat())

    def test_duplicate_idempotency_key_does_not_rewrite_document(self):
        collection = InMemoryInquiryCollection()
        idempotency_store = InMemoryIdempotencyKeyIndexStore()
        body = json.dumps(
            {
                "draft_id": "draft-abc123",
                "customer_email": "customer@example.com",
                "category": "メール未着",
                "idempotency_key": "retry-key-1",
            }
        ).encode("utf-8")

        first = receive_inquiry_form_submission(
            body, collection=collection, idempotency_store=idempotency_store, now=FIXED_NOW
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(collection._documents), 1)

        second = receive_inquiry_form_submission(
            body, collection=collection, idempotency_store=idempotency_store, now=FIXED_NOW
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.inquiry_id, first.inquiry_id)
        # 再送時はcollection.add()が再度呼ばれない(document=None検知のため件数は変化しない)。
        self.assertEqual(len(collection._documents), 1)

    def test_to_json_body_shape(self):
        result = receive_inquiry_form_submission(
            VALID_BODY, collection=InMemoryInquiryCollection(), now=FIXED_NOW
        )
        parsed = json.loads(result.to_json_body())
        self.assertEqual(set(parsed.keys()), {"ok", "inquiry_id", "error"})
        self.assertTrue(parsed["ok"])
        self.assertIsNone(parsed["error"])


if __name__ == "__main__":
    unittest.main()
