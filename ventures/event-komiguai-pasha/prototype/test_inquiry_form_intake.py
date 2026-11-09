#!/usr/bin/env python3
"""inquiry_form_intake.pyの机上テスト(実Firestore接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import unittest
from datetime import datetime, timezone

from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore
from inquiry_form_intake import (
    InquiryFormInput,
    build_inquiry_document,
    build_missing_fields_message,
    find_missing_required_fields,
    handle_inquiry_form_submission,
    parse_inquiry_form_payload,
)


class ParseInquiryFormPayloadTest(unittest.TestCase):
    def test_strips_and_treats_blank_as_missing(self):
        form = parse_inquiry_form_payload(
            {
                "draft_id": "  abc123  ",
                "customer_email": "",
                "category": "   ",
                "detail": None,
            }
        )
        self.assertEqual(form.draft_id, "abc123")
        self.assertIsNone(form.customer_email)
        self.assertIsNone(form.category)
        self.assertIsNone(form.detail)

    def test_non_string_values_are_treated_as_missing(self):
        form = parse_inquiry_form_payload({"draft_id": 12345})
        self.assertIsNone(form.draft_id)


class FindMissingRequiredFieldsTest(unittest.TestCase):
    def test_all_present_returns_empty(self):
        form = InquiryFormInput(
            draft_id="abc123", customer_email="a@example.com", category="再送希望"
        )
        self.assertEqual(find_missing_required_fields(form), [])

    def test_missing_multiple_fields_keeps_required_order(self):
        form = InquiryFormInput(category="再送希望")
        self.assertEqual(
            find_missing_required_fields(form), ["draft_id", "customer_email"]
        )


class BuildMissingFieldsMessageTest(unittest.TestCase):
    def test_raises_when_nothing_missing(self):
        with self.assertRaises(ValueError):
            build_missing_fields_message([])

    def test_lists_labels_for_missing_fields(self):
        message = build_missing_fields_message(["draft_id", "category"])
        self.assertIn("受付番号", message)
        self.assertIn("お問い合わせ区分", message)


class BuildInquiryDocumentTest(unittest.TestCase):
    def test_builds_document_with_received_status(self):
        form = InquiryFormInput(
            draft_id="abc123",
            customer_email="a@example.com",
            category="メール未着",
            detail="迷惑メールフォルダにも見当たりません",
        )
        document = build_inquiry_document(form, created_at="2026-11-02T20:00:00Z")
        self.assertEqual(
            document,
            {
                "draft_id": "abc123",
                "customer_email": "a@example.com",
                "category": "メール未着",
                "detail": "迷惑メールフォルダにも見当たりません",
                "status": "received",
                "created_at": "2026-11-02T20:00:00Z",
                "resolvedAt": None,
            },
        )

    def test_detail_may_be_none(self):
        form = InquiryFormInput(
            draft_id="abc123", customer_email="a@example.com", category="その他"
        )
        document = build_inquiry_document(form, created_at="2026-11-02T20:00:00Z")
        self.assertIsNone(document["detail"])

    def test_raises_on_missing_required_field(self):
        form = InquiryFormInput(draft_id="abc123", category="再送希望")
        with self.assertRaises(ValueError):
            build_inquiry_document(form, created_at="2026-11-02T20:00:00Z")

    def test_raises_on_unknown_category(self):
        form = InquiryFormInput(
            draft_id="abc123", customer_email="a@example.com", category="未定義区分"
        )
        with self.assertRaises(ValueError):
            build_inquiry_document(form, created_at="2026-11-02T20:00:00Z")


class HandleInquiryFormSubmissionTest(unittest.TestCase):
    def test_missing_fields_does_not_build_document(self):
        result = handle_inquiry_form_submission(
            {"category": "再送希望"}, created_at="2026-11-02T20:00:00Z"
        )
        self.assertEqual(result["status"], "missing_fields")
        self.assertNotIn("document", result)

    def test_accepted_returns_document(self):
        result = handle_inquiry_form_submission(
            {
                "draft_id": "abc123",
                "customer_email": "a@example.com",
                "category": "返金希望",
                "detail": "出力内容が期待と違いました",
            },
            created_at="2026-11-02T20:00:00Z",
        )
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["document"]["status"], "received")
        self.assertEqual(result["document"]["category"], "返金希望")
        self.assertTrue(result["inquiry_id"])

    def test_accepted_without_idempotency_store_always_issues_new_inquiry_id(self):
        # idempotency_store省略時は後方互換動作(フェーズ107のone_time_draft側と同型)。
        ids = iter(["inquiry-id-1", "inquiry-id-2"])
        payload = {
            "draft_id": "abc123",
            "customer_email": "a@example.com",
            "category": "再送希望",
        }
        first = handle_inquiry_form_submission(
            payload, created_at="2026-11-02T20:00:00Z", inquiry_id_factory=lambda: next(ids)
        )
        second = handle_inquiry_form_submission(
            payload, created_at="2026-11-02T20:00:00Z", inquiry_id_factory=lambda: next(ids)
        )
        self.assertEqual(first["inquiry_id"], "inquiry-id-1")
        self.assertEqual(second["inquiry_id"], "inquiry-id-2")
        self.assertIsNotNone(first["document"])
        self.assertIsNotNone(second["document"])


class HandleInquiryFormSubmissionIdempotencyTest(unittest.TestCase):
    """フェーズ107(checkout_session_creation)と同型の衝突検知をinquiry側に結線したことの確認。"""

    def setUp(self):
        self.idempotency_store = InMemoryIdempotencyKeyIndexStore()
        self.fixed_now = datetime(2026, 11, 9, 23, 0, 0, tzinfo=timezone.utc)
        self.payload = {
            "draft_id": "abc123",
            "customer_email": "a@example.com",
            "category": "再送希望",
            "idempotency_key": "idem-inquiry-1",
        }

    def test_reserves_new_inquiry_id_when_first_seen(self):
        result = handle_inquiry_form_submission(
            self.payload,
            created_at="2026-11-09T23:00:00Z",
            idempotency_store=self.idempotency_store,
            now=self.fixed_now,
            inquiry_id_factory=lambda: "inquiry-id-1",
        )
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(result["inquiry_id"], "inquiry-id-1")
        self.assertIsNotNone(result["document"])

    def test_reuses_existing_inquiry_id_without_document_on_resubmission(self):
        first = handle_inquiry_form_submission(
            self.payload,
            created_at="2026-11-09T23:00:00Z",
            idempotency_store=self.idempotency_store,
            now=self.fixed_now,
            inquiry_id_factory=lambda: "inquiry-id-1",
        )

        # 2回目の送信(同一idempotency_key、二重クリック・再試行を想定)。
        # inquiry_id_factory()が別の値を返しても、既存のinquiry_idが優先されること。
        second = handle_inquiry_form_submission(
            self.payload,
            created_at="2026-11-09T23:05:00Z",
            idempotency_store=self.idempotency_store,
            now=self.fixed_now,
            inquiry_id_factory=lambda: "inquiry-id-2",
        )

        self.assertEqual(second["status"], "accepted")
        self.assertEqual(second["inquiry_id"], first["inquiry_id"])
        # document=Noneとなり、呼び出し側は2回目のadd()を行わないこと
        # (先行リクエストが既に同内容で書き込み済みのため)。
        self.assertIsNone(second["document"])

    def test_missing_idempotency_key_always_issues_new_inquiry_id(self):
        payload_without_key = {
            "draft_id": "abc123",
            "customer_email": "a@example.com",
            "category": "再送希望",
        }
        ids = iter(["inquiry-id-1", "inquiry-id-2"])
        first = handle_inquiry_form_submission(
            payload_without_key,
            created_at="2026-11-09T23:00:00Z",
            idempotency_store=self.idempotency_store,
            now=self.fixed_now,
            inquiry_id_factory=lambda: next(ids),
        )
        second = handle_inquiry_form_submission(
            payload_without_key,
            created_at="2026-11-09T23:05:00Z",
            idempotency_store=self.idempotency_store,
            now=self.fixed_now,
            inquiry_id_factory=lambda: next(ids),
        )
        self.assertEqual(first["inquiry_id"], "inquiry-id-1")
        self.assertEqual(second["inquiry_id"], "inquiry-id-2")


if __name__ == "__main__":
    unittest.main()
