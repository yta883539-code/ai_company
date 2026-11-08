#!/usr/bin/env python3
"""draft_generation_fn.pyの机上テスト(実LLM/実クラウド接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他モジュールと同じ発見方式)。
"""

import unittest

from draft_generation_fn import DraftEventMemoMissingError, build_generation_fn
from generation_retry_and_refund import GenerationError
from mock_llm_client import MOCK_LLM_SCENARIOS, MockLlmClient
from stripe_webhook import InMemoryOneTimeDraftStore, OneTimeDraft

VALID_MEMO = {
    "capacity": "300人",
    "entry_exit_points": "入場口1・退場口1(共用)",
    "admission_type": "自由入場",
}

GENERATED_SCENARIO = next(
    name for name, case in MOCK_LLM_SCENARIOS.items() if case["status"] == "generated"
)
OUT_OF_SCOPE_SCENARIO = next(
    name for name, case in MOCK_LLM_SCENARIOS.items() if case["status"] == "out_of_scope"
)


class BuildGenerationFnTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryOneTimeDraftStore()
        self.llm_client = MockLlmClient()

    def test_missing_draft_raises_event_memo_missing_error(self) -> None:
        generate = build_generation_fn(
            self.store, self.llm_client, lambda draft_id: GENERATED_SCENARIO
        )
        with self.assertRaises(DraftEventMemoMissingError):
            generate("draft_nonexistent")

    def test_draft_without_event_memo_raises_event_memo_missing_error(self) -> None:
        # create_draft()を経由せずseed()で直接投入した想定外の経路(design上は発生しない)。
        self.store.seed(OneTimeDraft(draft_id="draft_legacy", status="awaiting_payment"))
        generate = build_generation_fn(
            self.store, self.llm_client, lambda draft_id: GENERATED_SCENARIO
        )
        with self.assertRaises(DraftEventMemoMissingError):
            generate("draft_legacy")

    def test_valid_memo_returns_llm_output_for_generated_scenario(self) -> None:
        self.store.create_draft("draft_ok", event_memo=VALID_MEMO)
        generate = build_generation_fn(
            self.store, self.llm_client, lambda draft_id: GENERATED_SCENARIO
        )
        output = generate("draft_ok")
        self.assertEqual(output["status"], "generated")
        self.assertEqual(len(self.llm_client.calls), 1)
        called_payload, called_scenario = self.llm_client.calls[0]
        self.assertEqual(called_scenario, GENERATED_SCENARIO)
        self.assertEqual(
            called_payload["user_memo_fields"]["capacity"], VALID_MEMO["capacity"]
        )

    def test_out_of_scope_scenario_does_not_raise(self) -> None:
        self.store.create_draft("draft_oos", event_memo=VALID_MEMO)
        generate = build_generation_fn(
            self.store, self.llm_client, lambda draft_id: OUT_OF_SCOPE_SCENARIO
        )
        output = generate("draft_oos")
        self.assertEqual(output["status"], "out_of_scope")

    def test_insufficient_input_memo_returns_response_without_calling_llm(self) -> None:
        incomplete_memo = {"capacity": "300人"}  # entry_exit_points・admission_type欠落
        self.store.create_draft("draft_incomplete", event_memo=incomplete_memo)
        generate = build_generation_fn(
            self.store, self.llm_client, lambda draft_id: GENERATED_SCENARIO
        )
        output = generate("draft_incomplete")
        self.assertEqual(output["status"], "insufficient_input")
        self.assertEqual(self.llm_client.calls, [])

    def test_scenario_resolved_per_draft_id(self) -> None:
        self.store.create_draft("draft_a", event_memo=VALID_MEMO)
        self.store.create_draft("draft_b", event_memo=VALID_MEMO)
        scenario_map = {"draft_a": GENERATED_SCENARIO, "draft_b": OUT_OF_SCOPE_SCENARIO}
        generate = build_generation_fn(
            self.store, self.llm_client, lambda draft_id: scenario_map[draft_id]
        )
        self.assertEqual(generate("draft_a")["status"], "generated")
        self.assertEqual(generate("draft_b")["status"], "out_of_scope")

    def test_validation_error_raises_generation_error(self) -> None:
        self.store.create_draft("draft_bad_output", event_memo=VALID_MEMO)

        class BrokenLlmClient:
            def generate(self, payload: dict, *, scenario: str) -> dict:
                # schema違反(statusフィールド欠落)を返し、検証エラーを誘発する。
                return {"out_of_scope_message": None}

        generate = build_generation_fn(
            self.store, BrokenLlmClient(), lambda draft_id: GENERATED_SCENARIO
        )
        with self.assertRaises(GenerationError):
            generate("draft_bad_output")


if __name__ == "__main__":
    unittest.main()
