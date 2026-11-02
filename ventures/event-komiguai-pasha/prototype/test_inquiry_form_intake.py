#!/usr/bin/env python3
"""inquiry_form_intake.pyの机上テスト(実Firestore接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import unittest

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


if __name__ == "__main__":
    unittest.main()
