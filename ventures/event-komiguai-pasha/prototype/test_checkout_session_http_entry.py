#!/usr/bin/env python3
"""checkout_session_http_entry.pyの机上テスト(実Stripe/実Firestore接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import json
import unittest
from datetime import datetime, timezone

from checkout_session_creation import InMemoryCheckoutSessionClient
from checkout_session_http_entry import receive_event_form_submission
from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore
from stripe_webhook import InMemoryOneTimeDraftStore

FIXED_NOW = datetime(2026, 11, 10, 7, 0, 0, tzinfo=timezone.utc)
BASE_URL = "https://example.invalid"

VALID_BODY = json.dumps(
    {
        "capacity": "300人",
        "entry_exit_points": "入場口2・退場口1(分離)",
        "admission_type": "自由入場",
    }
).encode("utf-8")


class ReceiveEventFormSubmissionTest(unittest.TestCase):
    def test_invalid_json_returns_400(self):
        result = receive_event_form_submission(
            b"not json",
            draft_store=InMemoryOneTimeDraftStore(),
            checkout_client=InMemoryCheckoutSessionClient(),
            base_url=BASE_URL,
            now=FIXED_NOW,
        )
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.body["ok"])

    def test_non_object_json_returns_400(self):
        result = receive_event_form_submission(
            b"[1, 2, 3]",
            draft_store=InMemoryOneTimeDraftStore(),
            checkout_client=InMemoryCheckoutSessionClient(),
            base_url=BASE_URL,
            now=FIXED_NOW,
        )
        self.assertEqual(result.status_code, 400)
        self.assertFalse(result.body["ok"])

    def test_missing_required_fields_returns_200_insufficient_input(self):
        draft_store = InMemoryOneTimeDraftStore()
        body = json.dumps({"capacity": "300人"}).encode("utf-8")
        result = receive_event_form_submission(
            body,
            draft_store=draft_store,
            checkout_client=InMemoryCheckoutSessionClient(),
            base_url=BASE_URL,
            now=FIXED_NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.body["status"], "insufficient_input")
        self.assertIsNotNone(result.body["missing_fields_request"])
        # design 2節: 必須項目欠落時はdraftを作成しない。
        self.assertEqual(draft_store._drafts, {})

    def test_valid_submission_creates_draft_and_returns_checkout_url(self):
        draft_store = InMemoryOneTimeDraftStore()
        result = receive_event_form_submission(
            VALID_BODY,
            draft_store=draft_store,
            checkout_client=InMemoryCheckoutSessionClient(),
            base_url=BASE_URL,
            now=FIXED_NOW,
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.body["ok"])
        self.assertIsNotNone(result.body["draft_id"])
        self.assertTrue(result.body["checkout_url"].startswith("https://"))
        self.assertIn(result.body["draft_id"], draft_store._drafts)

    def test_duplicate_idempotency_key_reuses_draft_id(self):
        draft_store = InMemoryOneTimeDraftStore()
        idempotency_store = InMemoryIdempotencyKeyIndexStore()
        body = json.dumps(
            {
                "capacity": "300人",
                "entry_exit_points": "入場口2・退場口1",
                "admission_type": "自由入場",
                "idempotency_key": "retry-key-1",
            }
        ).encode("utf-8")

        first = receive_event_form_submission(
            body,
            draft_store=draft_store,
            checkout_client=InMemoryCheckoutSessionClient(),
            base_url=BASE_URL,
            idempotency_store=idempotency_store,
            now=FIXED_NOW,
        )
        second = receive_event_form_submission(
            body,
            draft_store=draft_store,
            checkout_client=InMemoryCheckoutSessionClient(),
            base_url=BASE_URL,
            idempotency_store=idempotency_store,
            now=FIXED_NOW,
        )
        self.assertEqual(first.body["draft_id"], second.body["draft_id"])
        self.assertEqual(len(draft_store._drafts), 1)

    def test_to_json_body_shape(self):
        result = receive_event_form_submission(
            VALID_BODY,
            draft_store=InMemoryOneTimeDraftStore(),
            checkout_client=InMemoryCheckoutSessionClient(),
            base_url=BASE_URL,
            now=FIXED_NOW,
        )
        parsed = json.loads(result.to_json_body())
        self.assertEqual(set(parsed.keys()), {"ok", "draft_id", "checkout_url"})


if __name__ == "__main__":
    unittest.main()
