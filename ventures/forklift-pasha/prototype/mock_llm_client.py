#!/usr/bin/env python3
"""
event-komiguai-pashaフェーズ26(mock_llm_client.py・run_form_submission_pipeline)と
同型のモジュールを本venture未着手だった部分に横展開する。

これまでschema/validate_test_cases.py(G1〜G4・OOS1・II1〜II3・ネガティブ3件)は
schema適合性・クロスフィールドルールの机上検証にしか使われておらず、
form_submission_flow.process_form_submission()のテスト(test_form_submission_flow.py)
は別途手書きのlambdaでllm_generateをスタブ化していたため、両者がフィクスチャを共有
していなかった(本venture固有のparityギャップ)。本モジュールは、schema側の
POSITIVE_CASESをそのままprocess_form_submission()に注入できるキャンド出力つき
モッククライアントとして提供し、「フィクスチャのschema適合性」と
「process_form_submission()を通した実際の応答文言」を1本のフローで同時に検証できる
ようにする。

位置づけ:
- 実LLM API呼び出しは行わない(APIキー取得・実運用はオーナー承認待ち、
  pending-approval.md参照)。
- キャンド出力はschema/validate_test_cases.pyのPOSITIVE_CASES(G1〜G4・OOS1・
  II1〜II3)をそのまま再利用する。本venture(process_form_submission)は
  insufficient_input・out_of_scopeも含めて全てllm_generate経由で判定する設計
  (event-komiguai-pashaのような別立てintake層は無い)ため、II系もモックの対象
  シナリオに含める。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from post_generation_checks import run_all_checks  # noqa: E402
from validate_test_cases import (  # noqa: E402
    POSITIVE_CASES,
    SCHEMA,
    validate_against_schema,
    validate_cross_field_rules,
)


class MockLlmResponseNotFoundError(KeyError):
    """指定されたシナリオ名がPOSITIVE_CASESに存在しない場合に送出する。"""


class LlmClient(Protocol):
    def generate(self, raw_text: str, *, scenario: str) -> dict:
        """schema/output.schema.jsonに準拠した構造化出力(dict)を返す想定。
        実クライアント(APIキー取得後)はscenario引数を持たず入力のみから生成する契約に
        差し替わる想定だが、本モックは机上検証のため呼び出し側がどのキャンド出力を
        受け取るかを明示的に指定する。"""
        ...


class MockLlmClient:
    """schema/validate_test_cases.pyのPOSITIVE_CASESをそのまま返すだけのスタブ。
    呼び出しごとの引数(raw_text・scenario)を記録し、テストから呼び出し回数・渡された
    raw_textを検証できるようにする。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, raw_text: str, *, scenario: str) -> dict:
        self.calls.append((raw_text, scenario))
        if scenario not in POSITIVE_CASES:
            raise MockLlmResponseNotFoundError(
                f"未知のシナリオ名です: {scenario!r}(POSITIVE_CASESのキーから指定してください)"
            )
        # POSITIVE_CASESの辞書そのものへの参照を返すと呼び出し元の変更が台帳側に漏れるため、
        # 1階層コピーして返す(浅いコピーで十分、各フィールドは再代入のみ想定)。
        return dict(POSITIVE_CASES[scenario])

    def as_llm_generate(self, scenario: str):
        """process_form_submission()が要求する「raw_text一つだけを取る」
        LlmGenerateFn契約に合わせたクロージャを返す(scenarioを固定した1回分)。"""

        def _llm_generate(raw_text: str) -> dict:
            return self.generate(raw_text, scenario=scenario)

        return _llm_generate


def validate_llm_output(instance: dict) -> list[str]:
    """schema適合性・クロスフィールドルール・厳守事項6/7の機械チェック
    (post_generation_checks.run_all_checks)の3段階検証をまとめて行う
    (event-komiguai-pashaのcloud_function_webhook.py内validate_llm_outputと同じ
    位置づけ)。"""
    errors = validate_against_schema(instance, SCHEMA)
    if errors:
        # スキーマ自体に適合しない場合、以降のチェックはstatus等の前提が崩れている
        # ため実行しない(他venture共通の考え方)。
        return errors
    errors += validate_cross_field_rules(instance)
    errors += run_all_checks(instance)
    return errors
