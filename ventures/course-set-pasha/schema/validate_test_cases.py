#!/usr/bin/env python3
"""
schema/output.schema.json(2026-08-07 15:00 UTC改訂版)に対する期待JSON出力サンプルを
机上検証するスクリプト。line-reservation-aiのschema/validate_test_cases.pyと同じ位置づけ・
同じ簡易バリデータ方式(draft-07のサブセットのみ解釈)を踏襲した。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- schema-structured-output-compat-check.md(2026-08-07 15:00 UTC)の改訂方針
  (allOf/if-then撤去、全プロパティrequired化+null許容、statusに応じたnull/非nullの
  依存関係はコード側検証で担保)が、実際にサンプル出力に対して機械的に検証可能かを確認する。
- 外部ライブラリ(jsonschema等)には依存しない(pure stdlibのみ)。

実行方法: python3 validate_test_cases.py
"""

import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "output.schema.json"

with open(SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)


def validate_against_schema(instance, schema, path="$"):
    """output.schema.json のサブセット(type/enum/required/additionalProperties/items)
    のみを解釈する簡易バリデータ。draft-07全体には対応しない。"""
    errors = []

    def type_ok(value, type_spec):
        types = type_spec if isinstance(type_spec, list) else [type_spec]
        for t in types:
            if t == "null" and value is None:
                return True
            if t == "string" and isinstance(value, str):
                return True
            if t == "boolean" and isinstance(value, bool):
                return True
            if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
                return True
            if t == "array" and isinstance(value, list):
                return True
            if t == "object" and isinstance(value, dict):
                return True
        return False

    if "type" in schema and not type_ok(instance, schema["type"]):
        errors.append(f"{path}: 型不一致 (期待={schema['type']}, 実際={type(instance).__name__}: {instance!r})")
        return errors  # 型が違えば以降のチェックは無意味

    if isinstance(schema.get("type"), (str, list)) and "object" in (
        schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    ) and isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: 必須フィールド '{key}' が欠けています")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            for key in instance:
                if key not in allowed:
                    errors.append(f"{path}: 未定義フィールド '{key}' が含まれています")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                errors.extend(validate_against_schema(value, props[key], path=f"{path}.{key}"))

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(validate_against_schema(item, schema["items"], path=f"{path}[{i}]"))

    if "enum" in schema and instance is not None and instance not in schema["enum"]:
        errors.append(f"{path}: enum不一致 (期待={schema['enum']}, 実際={instance!r})")

    return errors


def validate_cross_field_rules(instance, path="$"):
    """JSON Schema単体では表現しきれない、status値に応じたnull/非nullの依存関係ルールを
    チェックする(schema-structured-output-compat-check.mdの改訂方針に対応)。"""
    errors = []
    status = instance.get("status")

    generated_fields = ["sns_post", "line_web_notice", "history_row"]

    if status == "generated":
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=generatedのときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=generatedのときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is None:
                errors.append(f"{path}: status=generatedのとき{f}は非nullである必要があります")
    elif status == "out_of_scope":
        if instance.get("out_of_scope_message") is None:
            errors.append(f"{path}: status=out_of_scopeのときout_of_scope_messageは非nullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=out_of_scopeのときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status=out_of_scopeのとき{f}はnullである必要があります")
    elif status == "insufficient_input":
        if instance.get("missing_fields_request") is None:
            errors.append(f"{path}: status=insufficient_inputのときmissing_fields_requestは非nullである必要があります")
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=insufficient_inputのときout_of_scope_messageはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status=insufficient_inputのとき{f}はnullである必要があります")

    sns_post = instance.get("sns_post")
    if sns_post and sns_post.get("mentions_photo") is not True and sns_post.get("mentions_photo") is not False:
        errors.append(f"{path}.sns_post.mentions_photo: booleanである必要があります(null不可)")

    return errors


# mvp-flow-draft.md・llm-system-prompt-draft.mdで検討してきた入力パターンを踏まえ、
# 期待される構造化出力を机上で書き起こしたフィクスチャ。
TEST_CASES = {
    "G1_basic": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "sns_post": {
            "body": "【課題入れ替えのお知らせ】エリアAに新着課題8本追加しました。ダイナミックなムーブが特徴です。",
            "hashtags": ["#ボルダリング", "#クライミングジム", "#新着課題"],
            "mentions_photo": False,
        },
        "line_web_notice": {
            "body": "エリアA:新着8本(黄テープ帯)を追加しました。ぜひチャレンジしてください。",
        },
        "history_row": {
            "revision_date": "2026-08-07",
            "area": "エリアA",
            "tape_color_or_grade_band": "黄テープ",
            "count": 8,
            "feature_keywords": ["ダイナミック", "ムーブ重視"],
        },
        "unchanged_areas": [],
    },
    "G2_with_photo_and_unchanged_areas": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "sns_post": {
            "body": "エリアBの新着課題を写真の課題を中心にご紹介します。",
            "hashtags": ["#ボルダリング", "#新着課題", "#〇〇ジム"],
            "mentions_photo": True,
        },
        "line_web_notice": {
            "body": "エリアB:新着5本を追加。エリアC・エリアDは変更ありません。",
        },
        "history_row": {
            "revision_date": "2026-08-07",
            "area": "エリアB",
            "tape_color_or_grade_band": "赤テープ〜黒テープ",
            "count": 5,
            "feature_keywords": ["パワー系", "ランジ"],
        },
        "unchanged_areas": ["エリアC", "エリアD"],
    },
    "G3_count_and_date_unextractable": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "sns_post": {
            "body": "エリアEに新着課題を追加しました。",
            "hashtags": ["#ボルダリング", "#新着課題"],
            "mentions_photo": False,
        },
        "line_web_notice": {
            "body": "エリアEに新着課題を追加しました。詳細は店頭でご確認ください。",
        },
        "history_row": {
            "revision_date": None,
            "area": "エリアE",
            "tape_color_or_grade_band": "緑テープ",
            "count": None,
            "feature_keywords": ["バランス系"],
        },
        "unchanged_areas": [],
    },
    "OOS1_membership_question": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは告知文・記録の下書き作成支援のみを行っており、会員管理・予約受付・決済のご案内はできません。",
        "missing_fields_request": None,
        "sns_post": None,
        "line_web_notice": None,
        "history_row": None,
        "unchanged_areas": [],
    },
    "II1_no_area_no_count": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "エリア名と本数が不明なため、告知文・記録を作成できません。エリア名(例:エリアA)と入れ替えた本数を教えてください。",
        "sns_post": None,
        "line_web_notice": None,
        "history_row": None,
        "unchanged_areas": [],
    },
}


def main():
    total = 0
    failed = 0
    for case_id, instance in TEST_CASES.items():
        total += 1
        errors = validate_against_schema(instance, SCHEMA)
        errors += validate_cross_field_rules(instance)
        if errors:
            failed += 1
            print(f"[NG] {case_id}")
            for e in errors:
                print(f"      - {e}")
        else:
            print(f"[OK] {case_id}")

    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
