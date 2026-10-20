#!/usr/bin/env python3
"""form_submission_intake.pyの机上テスト(実LLM・実クラウド接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import unittest

from form_submission_intake import (
    EventMemoInput,
    build_insufficient_input_response,
    build_llm_request_payload,
    find_missing_required_fields,
    handle_form_submission,
    parse_form_payload,
)


class ParseFormPayloadTest(unittest.TestCase):
    def test_strips_and_treats_blank_as_missing(self):
        memo = parse_form_payload(
            {
                "capacity": "  800人  ",
                "entry_exit_points": "",
                "admission_type": "   ",
                "staffing": None,
                "outdoor_queue": "屋内に収まる",
            }
        )
        self.assertEqual(memo.capacity, "800人")
        self.assertIsNone(memo.entry_exit_points)
        self.assertIsNone(memo.admission_type)
        self.assertIsNone(memo.staffing)
        self.assertEqual(memo.outdoor_queue, "屋内に収まる")

    def test_non_string_values_are_treated_as_missing(self):
        memo = parse_form_payload({"capacity": 800})
        self.assertIsNone(memo.capacity)


class FindMissingRequiredFieldsTest(unittest.TestCase):
    def test_all_present_returns_empty(self):
        memo = EventMemoInput(
            capacity="800人",
            entry_exit_points="入場口2箇所・退場口1箇所",
            admission_type="自由入場",
        )
        self.assertEqual(find_missing_required_fields(memo), [])

    def test_missing_single_field(self):
        memo = EventMemoInput(entry_exit_points="入場口2箇所", admission_type="自由入場")
        self.assertEqual(find_missing_required_fields(memo), ["capacity"])

    def test_missing_multiple_fields_keeps_required_fields_order(self):
        memo = EventMemoInput(admission_type="自由入場")
        self.assertEqual(
            find_missing_required_fields(memo), ["capacity", "entry_exit_points"]
        )


class BuildInsufficientInputResponseTest(unittest.TestCase):
    def test_lists_missing_field_labels_and_nulls_other_outputs(self):
        response = build_insufficient_input_response(["capacity", "admission_type"])
        self.assertEqual(response["status"], "insufficient_input")
        self.assertIn("会場キャパシティ", response["missing_fields_request"])
        self.assertIn("入場方式", response["missing_fields_request"])
        for field in (
            "out_of_scope_message",
            "checklist",
            "staffing_plan",
            "notice_board_text",
            "near_miss_record_template",
            "fee_inquiry_note",
        ):
            self.assertIsNone(response[field])

    def test_raises_when_nothing_is_missing(self):
        with self.assertRaises(ValueError):
            build_insufficient_input_response([])


class BuildLlmRequestPayloadTest(unittest.TestCase):
    def test_builds_payload_when_required_fields_present(self):
        memo = EventMemoInput(
            capacity="300人",
            entry_exit_points="入退場共用1箇所",
            admission_type="全席指定",
            staffing="外部委託3名+自社2名",
            outdoor_queue=None,
        )
        payload = build_llm_request_payload(memo)
        self.assertEqual(payload["system_prompt_ref"], "llm-system-prompt-draft.md")
        self.assertEqual(payload["user_memo_fields"]["capacity"], "300人")
        self.assertIsNone(payload["user_memo_fields"]["outdoor_queue"])

    def test_raises_when_required_field_missing(self):
        memo = EventMemoInput(entry_exit_points="1箇所", admission_type="自由入場")
        with self.assertRaises(ValueError):
            build_llm_request_payload(memo)


class HandleFormSubmissionTest(unittest.TestCase):
    def test_returns_insufficient_input_response_without_building_llm_payload(self):
        result = handle_form_submission({"admission_type": "自由入場"})
        self.assertEqual(result["status"], "insufficient_input")

    def test_returns_llm_request_payload_when_sufficient(self):
        result = handle_form_submission(
            {
                "capacity": "800人",
                "entry_exit_points": "入場口2箇所・退場口1箇所",
                "admission_type": "自由入場(整理番号なし)",
                "staffing": "会場スタッフ4名のみ",
                "outdoor_queue": "過去にヒヤリハット無し",
            }
        )
        self.assertEqual(result["system_prompt_ref"], "llm-system-prompt-draft.md")
        self.assertNotIn("status", result)


if __name__ == "__main__":
    unittest.main()
