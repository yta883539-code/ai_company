#!/usr/bin/env python3
"""inquiry_intake.pyの机上テスト(実LLM・実Firestore接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import unittest

from inquiry_intake import InquiryRecord, build_inquiry_response
from operational_message_templates import TEMPLATES


class BuildInquiryResponseResendTest(unittest.TestCase):
    def test_mail_not_received_before_ttl_uses_fixed_template_with_url(self):
        inquiry = InquiryRecord(draft_id="d1", category="メール未着", detail="メールが届きません")
        result = build_inquiry_response(
            inquiry, draft_exists=True, result_page_url="https://example.com/result/d1"
        )
        self.assertEqual(result["response_type"], "resend_before_ttl")
        self.assertEqual(
            result["customer_reply"],
            TEMPLATES["inquiry_reply_resend_before_ttl"].format(
                result_page_url="https://example.com/result/d1"
            ),
        )
        self.assertIsNone(result["owner_summary"])
        self.assertEqual(result["requires_owner_action"], "send_after_confirmation")

    def test_resend_request_after_ttl_uses_fixed_template_without_placeholder(self):
        inquiry = InquiryRecord(draft_id="d2", category="再送希望")
        result = build_inquiry_response(inquiry, draft_exists=False)
        self.assertEqual(result["response_type"], "resend_after_ttl")
        self.assertEqual(
            result["customer_reply"], TEMPLATES["inquiry_reply_resend_after_ttl"]
        )
        self.assertIsNone(result["owner_summary"])

    def test_missing_result_page_url_before_ttl_raises(self):
        inquiry = InquiryRecord(draft_id="d3", category="メール未着")
        with self.assertRaises(ValueError):
            build_inquiry_response(inquiry, draft_exists=True, result_page_url=None)


class BuildInquiryResponseRefundTest(unittest.TestCase):
    def test_quality_refund_request_has_no_customer_reply(self):
        inquiry = InquiryRecord(
            draft_id="d4", category="返金希望", detail="内容が期待と違いました"
        )
        result = build_inquiry_response(inquiry, draft_exists=True)
        self.assertEqual(result["response_type"], "quality_refund_request")
        self.assertIsNone(result["customer_reply"])
        self.assertIn("d4", result["owner_summary"])
        self.assertIn("内容が期待と違いました", result["owner_summary"])
        self.assertEqual(result["requires_owner_action"], "owner_judgment_required")

    def test_quality_refund_request_includes_generation_result_when_provided(self):
        inquiry = InquiryRecord(draft_id="d5", category="返金希望")
        result = build_inquiry_response(
            inquiry, draft_exists=True, generation_result_text="チェックリスト: ..."
        )
        self.assertIn("チェックリスト: ...", result["owner_summary"])

    def test_quality_refund_request_without_generation_result_notes_unavailable(self):
        inquiry = InquiryRecord(draft_id="d6", category="返金希望")
        result = build_inquiry_response(inquiry, draft_exists=True)
        self.assertIn("未取得", result["owner_summary"])


class BuildInquiryResponseUncategorizedTest(unittest.TestCase):
    def test_other_category_requires_manual_review_with_no_auto_reply(self):
        inquiry = InquiryRecord(draft_id="d7", category="その他", detail="日程変更したい")
        result = build_inquiry_response(inquiry, draft_exists=True)
        self.assertEqual(result["response_type"], "uncategorized")
        self.assertIsNone(result["customer_reply"])
        self.assertEqual(result["requires_owner_action"], "manual_review_required")
        self.assertIn("日程変更したい", result["owner_summary"])

    def test_unknown_category_raises(self):
        inquiry = InquiryRecord(draft_id="d8", category="不明区分")
        with self.assertRaises(ValueError):
            build_inquiry_response(inquiry, draft_exists=True)


if __name__ == "__main__":
    unittest.main()
