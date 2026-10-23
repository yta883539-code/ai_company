#!/usr/bin/env python3
"""mock_llm_client.pyの机上テスト(実LLM・実クラウド接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import unittest

from mock_llm_client import (
    MockLlmClient,
    MockLlmResponseNotFoundError,
    run_form_submission_pipeline,
    validate_llm_output,
)

SUFFICIENT_PAYLOAD = {
    "capacity": "800人",
    "entry_exit_points": "入場口2箇所・退場口1箇所",
    "admission_type": "自由入場(整理番号なし)",
    "staffing": "会場スタッフ4名のみ",
    "outdoor_queue": "過去にヒヤリハット無し",
}

INSUFFICIENT_PAYLOAD = {"admission_type": "自由入場"}


class MockLlmClientTest(unittest.TestCase):
    def test_returns_known_scenario_as_a_copy(self):
        client = MockLlmClient()
        output = client.generate({"dummy": True}, scenario="G1_free_admission_indoor")
        self.assertEqual(output["status"], "generated")
        # 浅いコピーであることの確認(台帳側を書き換えても影響しない)。
        output["status"] = "mutated"
        output2 = client.generate({"dummy": True}, scenario="G1_free_admission_indoor")
        self.assertEqual(output2["status"], "generated")

    def test_records_calls(self):
        client = MockLlmClient()
        client.generate({"a": 1}, scenario="OOS1_external_contractor_request")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0], ({"a": 1}, "OOS1_external_contractor_request"))

    def test_unknown_scenario_raises(self):
        client = MockLlmClient()
        with self.assertRaises(MockLlmResponseNotFoundError):
            client.generate({}, scenario="NOT_A_REAL_SCENARIO")

    def test_insufficient_input_scenarios_are_excluded_from_registry(self):
        # insufficient_input系はintake層で完結しLLMを呼ばないため、モックの
        # シナリオ台帳にも含めない(MOCK_LLM_SCENARIOSのフィルタ条件の確認)。
        client = MockLlmClient()
        with self.assertRaises(MockLlmResponseNotFoundError):
            client.generate({}, scenario="II1_missing_capacity_and_entry_exit")


class ValidateLlmOutputTest(unittest.TestCase):
    def test_known_good_scenario_has_no_errors(self):
        client = MockLlmClient()
        output = client.generate({}, scenario="G6_generated_with_incidental_fee_mention")
        self.assertEqual(validate_llm_output(output), [])

    def test_detects_cross_field_violation(self):
        # 厳守事項2違反(includes_road_use_permit_note=trueなのに本文に注記が無い)を
        # 意図的に混入させ、validate_llm_outputが検出することを確認する
        # (schema/validate_test_cases.pyのNEGATIVE_CASE_ROAD_USE_NOTE_MISSINGと同趣旨)。
        client = MockLlmClient()
        output = client.generate({}, scenario="G1_free_admission_indoor")
        output["notice_board_text"] = {
            "body": "ご来場の皆様へ。入場口付近が混雑する場合がございます。",
            "includes_road_use_permit_note": True,
        }
        errors = validate_llm_output(output)
        self.assertTrue(any("道路使用許可" in e for e in errors))

    def test_detects_emoji_via_post_generation_checks(self):
        # schema/クロスフィールド検証だけでは拾えない、本文テキストへの絵文字混入
        # (厳守事項9違反)をpost_generation_checks.run_all_checks経由で検出できることを
        # 確認する(validate_llm_outputへの統合確認)。MockLlmClient.generateが返すのは
        # 浅いコピーのため、ネストした辞書は再代入(新しい辞書への差し替え)で変更し、
        # TEST_CASES台帳側のネストした辞書を直接書き換えないようにする。
        client = MockLlmClient()
        output = client.generate({}, scenario="G1_free_admission_indoor")
        output["staffing_plan"] = {
            **output["staffing_plan"],
            "announcement_text": output["staffing_plan"]["announcement_text"] + "🙂",
        }
        errors = validate_llm_output(output)
        self.assertTrue(any("絵文字" in e for e in errors))

    def test_detects_out_of_scope_topic_via_post_generation_checks(self):
        # 厳守事項7違反(checklist本文への料金プラン言及の紛れ込み)を
        # post_generation_checks.run_all_checks経由で検出できることを確認する。上記と同じ
        # 理由で、checklistは新しいリスト・新しい要素辞書への差し替えで変更する。
        client = MockLlmClient()
        output = client.generate({}, scenario="G1_free_admission_indoor")
        first_item = output["checklist"][0]
        output["checklist"] = [
            {**first_item, "item": first_item["item"] + "なお月額の料金プランは別途ご確認ください。"},
            *output["checklist"][1:],
        ]
        errors = validate_llm_output(output)
        self.assertTrue(any("料金プラン" in e for e in errors))


class RunFormSubmissionPipelineTest(unittest.TestCase):
    def test_insufficient_input_short_circuits_without_calling_llm(self):
        client = MockLlmClient()
        output, errors = run_form_submission_pipeline(INSUFFICIENT_PAYLOAD, client)
        self.assertEqual(output["status"], "insufficient_input")
        self.assertEqual(errors, [])
        self.assertEqual(client.calls, [])  # LLMは一度も呼ばれない

    def test_sufficient_input_calls_llm_and_validates_generated_output(self):
        client = MockLlmClient()
        output, errors = run_form_submission_pipeline(
            SUFFICIENT_PAYLOAD, client, llm_scenario="G1_free_admission_indoor"
        )
        self.assertEqual(output["status"], "generated")
        self.assertEqual(errors, [])
        self.assertEqual(len(client.calls), 1)

    def test_sufficient_input_calls_llm_and_validates_out_of_scope_output(self):
        client = MockLlmClient()
        output, errors = run_form_submission_pipeline(
            SUFFICIENT_PAYLOAD, client, llm_scenario="OOS2_fee_and_payment_inquiry"
        )
        self.assertEqual(output["status"], "out_of_scope")
        self.assertEqual(errors, [])

    def test_sufficient_input_without_scenario_raises(self):
        client = MockLlmClient()
        with self.assertRaises(ValueError):
            run_form_submission_pipeline(SUFFICIENT_PAYLOAD, client)

    def test_llm_scenario_ignored_when_input_is_insufficient(self):
        client = MockLlmClient()
        output, errors = run_form_submission_pipeline(
            INSUFFICIENT_PAYLOAD, client, llm_scenario="G1_free_admission_indoor"
        )
        self.assertEqual(output["status"], "insufficient_input")
        self.assertEqual(client.calls, [])


if __name__ == "__main__":
    unittest.main()
