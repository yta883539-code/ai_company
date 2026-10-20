#!/usr/bin/env python3
"""
README.mdフェーズ26の次回候補(2)「fee_inquiry_note・out_of_scope等LLM側の構造化出力
そのものをスタブ化したモッククライアントを用意し、handle_form_submission()が返すLLM
リクエストペイロードから4出力の机上検証まで一本のフローとして繋げる」に対応するモジュール。

位置づけ:
- 実LLM API呼び出しは行わない(APIキー取得・実運用はオーナー承認待ち、
  pending-approval.md参照)。aircon-pasha/course-set-pasha/kura-pashaの
  cloud_function_webhook.py内LlmCallClient Protocol・InMemory系スタブと同じ考え方で、
  構造化出力の形(schema/output.schema.json準拠)を固定のシナリオ別キャンド出力として
  差し替え可能にしたもの。
- キャンド出力はschema/validate_test_cases.pyのTEST_CASES(フェーズ18〜25で積み上げた
  机上テストケース)をそのまま再利用する。insufficient_input系のケースはそもそもLLMを
  呼ばずに完結する(form_submission_intake.pyのbuild_insufficient_input_response)ため、
  本クライアントの対象シナリオからは除外する。
- 本モジュールが提供するrun_form_submission_pipeline()は、(a)Webフォーム生ペイロードを
  form_submission_intake.handle_form_submission()に渡し、(b)insufficient_input応答で
  完結する場合はLLMを呼ばずそのまま返し、(c)LLM呼び出しが必要な場合は本モック
  クライアントにシナリオ名を指定して呼び出し、(d)いずれの経路でもschema/
  validate_test_cases.pyのvalidate_against_schema・validate_cross_field_rulesで
  机上検証する、という一本のフローをテスト可能にする(実クラウド接続なし)。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from form_submission_intake import handle_form_submission  # noqa: E402
from validate_test_cases import (  # noqa: E402
    SCHEMA,
    TEST_CASES,
    validate_against_schema,
    validate_cross_field_rules,
)

# insufficient_input系のテストケースはLLM呼び出し前にintake層(form_submission_intake.py)
# が完結させるため、LLMが実際に返しうるシナリオ(generated/out_of_scope)のみを
# モッククライアントのシナリオ台帳とする。
MOCK_LLM_SCENARIOS = {
    name: case for name, case in TEST_CASES.items() if case["status"] != "insufficient_input"
}


class MockLlmResponseNotFoundError(KeyError):
    """指定されたシナリオ名がMOCK_LLM_SCENARIOSに存在しない場合に送出する。"""


class LlmCallClient(Protocol):
    def generate(self, payload: dict, *, scenario: str) -> dict:
        """schema/output.schema.jsonに準拠した構造化出力(dict)を返す想定。
        実クライアント(APIキー取得後)はscenario引数を持たず入力のみから生成する契約に
        差し替わる想定だが、本モックは机上検証のため呼び出し側がどのキャンド出力を
        受け取るかを明示的に指定する。"""
        ...


class MockLlmClient:
    """schema/validate_test_cases.pyのTEST_CASES(generated/out_of_scope系)をそのまま
    返すだけのスタブ。呼び出しごとの引数を記録し、テストから呼び出し回数・渡された
    payloadを検証できるようにする。"""

    def __init__(self) -> None:
        self.calls: list[tuple[dict, str]] = []

    def generate(self, payload: dict, *, scenario: str) -> dict:
        self.calls.append((payload, scenario))
        if scenario not in MOCK_LLM_SCENARIOS:
            raise MockLlmResponseNotFoundError(
                f"未知のシナリオ名です: {scenario!r}(MOCK_LLM_SCENARIOSのキーから指定してください)"
            )
        # TEST_CASESの辞書そのものへの参照を返すと呼び出し元の変更が台帳側に漏れるため、
        # 1階層コピーして返す(浅いコピーで十分、各フィールドは再代入のみ想定)。
        return dict(MOCK_LLM_SCENARIOS[scenario])


def validate_llm_output(instance: dict) -> list[str]:
    """schema適合性・クロスフィールドルールの2段階検証をまとめて行う
    (aircon-pasha/course-set-pasha/kura-pashaのcloud_function_webhook.py内
    validate_llm_outputと同じ位置づけ。本venture未着手のpost_generation_checks.py
    〈絵文字・対象外トピックのヒューリスティック検証〉は次回以降の課題とする)。"""
    errors = validate_against_schema(instance, SCHEMA)
    if errors:
        # スキーマ自体に適合しない場合、cross-fieldチェックはstatus等の前提が崩れている
        # ため実行しない(他venture共通の考え方)。
        return errors
    errors += validate_cross_field_rules(instance)
    return errors


def run_form_submission_pipeline(
    raw_payload: dict,
    llm_client: LlmCallClient,
    *,
    llm_scenario: Optional[str] = None,
) -> tuple[dict, list[str]]:
    """Webフォーム生ペイロード受信からLLM呼び出し(必要な場合のみ)・机上検証までを
    一本のフローとして繋げる。戻り値は(構造化出力dict, 検証エラーのリスト)。
    エラーリストが空ならschema/クロスフィールドルールいずれも違反なし。

    llm_scenarioは、必須項目が充足しLLM呼び出しが必要な場合にのみ必須(本モックは
    入力内容から自動でシナリオを選ばず、呼び出し側が机上検証したいキャンド出力を
    明示的に指定する契約のため)。insufficient_input応答で完結する場合は無視される。
    """
    intake_result = handle_form_submission(raw_payload)

    if "status" in intake_result:
        # intake層で完結済み(status=insufficient_input)。LLMは呼ばない
        # (厳守事項8: 不明な項目を推測で埋めて生成しない)。
        output = intake_result
    else:
        if llm_scenario is None:
            raise ValueError(
                "必須項目が充足しLLM呼び出しが必要なため、llm_scenarioの指定が必要です"
            )
        output = llm_client.generate(intake_result, scenario=llm_scenario)

    return output, validate_llm_output(output)
