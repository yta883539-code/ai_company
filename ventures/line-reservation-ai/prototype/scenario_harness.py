#!/usr/bin/env python3
"""
multi-turn-scenario-harness-design.md で設計した、conversation-samples-test-cases.md の
シナリオ(複数ターン)を`ConversationEventProcessor`経由で実行する再利用可能なテストハーネス。

llm-quality-verification-plan.md「複数ターンにまたがる状態遷移の検証」の残課題のうち、
「実LLM出力を各ターンの入力として連鎖させる」部分に対応する。各ターンの`llm_output`は
現状ではconversation-samples-test-cases.md準拠のスタブだが、`process_llm_output()`へ渡す
`llm_call`の中身を実際のClaude API呼び出しに差し替えるだけで実LLM検証にそのまま流用できる
よう、`ScenarioTurn`はメッセージ本文と出力のペアのみを持つ(スタブか実APIかを意識しない)
構造にした。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "schema"))

from cloud_function_process_event import ConversationEventProcessor, DispatchResult  # noqa: E402
from validate_test_cases import SCHEMA, validate_against_schema, validate_cross_field_rules  # noqa: E402


@dataclass
class ScenarioTurn:
    message: str
    llm_output: dict
    expect_action: Optional[str] = None
    expect_stage: Optional[str] = None


@dataclass
class ScenarioStepResult:
    turn: ScenarioTurn
    dispatch: DispatchResult
    schema_errors: list = field(default_factory=list)
    cross_field_errors: list = field(default_factory=list)


def run_scenario(
    processor: ConversationEventProcessor,
    turns: list,
    now: datetime,
    user_id: str = "U1",
) -> list:
    """turnsを順番にprocessor.process()へ流し込み、各ターンの結果をScenarioStepResultの
    リストとして返す。各ターンのllm_outputはprocess_llm_output()に渡す前にbooking_output.
    schema.json・cross-field rulesで机上検証する(schema-validation-report.mdと同じ検証を、
    単発の期待値突合だけでなく複数ターンの連鎖の中でも行う)。expect_action/expect_stageが
    指定されていればその場でAssertionErrorを送出する(unittestのassert*に依存しない汎用
    ヘルパーとするため)。
    """
    results = []
    for turn in turns:
        schema_errors = validate_against_schema(turn.llm_output, SCHEMA)
        cross_field_errors = validate_cross_field_rules(turn.llm_output)

        def _llm_call(output=turn.llm_output):
            return output

        event = {"source": {"userId": user_id}, "message": {"text": turn.message}}
        dispatch = processor.process(event, _llm_call, now)

        if turn.expect_action is not None and dispatch.action != turn.expect_action:
            raise AssertionError(
                f"turn '{turn.message}': expected action={turn.expect_action!r}, "
                f"got {dispatch.action!r} (detail={dispatch.detail!r})"
            )
        if turn.expect_stage is not None:
            actual_stage = processor._flow.stage(user_id)
            if actual_stage != turn.expect_stage:
                raise AssertionError(
                    f"turn '{turn.message}': expected stage={turn.expect_stage!r}, "
                    f"got {actual_stage!r}"
                )

        results.append(
            ScenarioStepResult(
                turn=turn,
                dispatch=dispatch,
                schema_errors=schema_errors,
                cross_field_errors=cross_field_errors,
            )
        )
    return results
