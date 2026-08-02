#!/usr/bin/env python3
"""
conversation-samples-test-cases.md に記載された「期待される構造化出力」を
booking_output.schema.json に対して机上検証するスクリプト。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- あくまで、これまで人手で積み上げてきた「期待JSON出力」の記述同士に矛盾がないか
  (フィールド抜け・enum値の誤字・faq_segments/escalation_reasonの依存関係違反など)を
  機械的にチェックする、実装フェーズ着手の第一歩。
- 外部ライブラリ(jsonschema等)には依存しない(pure stdlibのみ)。

実行方法: python3 validate_test_cases.py
"""

import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "booking_output.schema.json"

with open(SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)


def validate_against_schema(instance, schema, path="$"):
    """booking_output.schema.json のサブセット(type/enum/required/additionalProperties/items)
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
    """JSON Schema単体では表現しきれない、設計ドキュメント上の依存関係ルールをチェックする。"""
    errors = []

    faq_segments = instance.get("faq_segments")
    if faq_segments:
        any_unresolved = any(seg.get("resolved") is False for seg in faq_segments)
        if any_unresolved and instance.get("needs_owner_check") is not True:
            errors.append(
                f"{path}: faq_segmentsにresolved:falseが含まれる場合、"
                f"needs_owner_checkはtrueである必要があります"
                f"(json-schema-multi-intent-extension.md準拠)"
            )

    if "feature_hint" in instance and instance.get("escalation_reason") != "unimplemented_feature":
        errors.append(
            f"{path}: feature_hintはescalation_reasonが'unimplemented_feature'の"
            f"ときのみ付与できます(notification-log-classification-labels.md準拠)"
        )

    return errors


# conversation-samples-test-cases.md に明記された「期待される構造化出力」を
# そのまま書き起こしたフィクスチャ。文章中で全フィールドが明示されていないケースは、
# 文脈から自明な値(未言及フィールドはnull/false)を補って机上検証用に構成した。
# N3・N4・E1・E3・E4・E7・E8は2026-07-31 14:58 UTC時点で期待構造化出力を新規に明文化し追加。
TEST_CASES = {
    "N1": {
        "intent": "new_booking", "name": "田中", "menu": "カット",
        "datetime_candidate": "来週土曜15時台の候補", "confirmed": False,
        "needs_owner_check": False,
    },
    "N2": {
        "intent": "new_booking", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": False,
    },
    "N3": {
        "intent": "new_booking", "name": "田中", "menu": "カット",
        "datetime_candidate": "来週土曜15時", "confirmed": True,
        "needs_owner_check": False,
    },
    "N4": {
        "intent": "new_booking", "name": "鈴木", "menu": "カラー",
        "datetime_candidate": "土曜10時(顧客DB登録の通常予約枠)", "confirmed": True,
        "needs_owner_check": False,
    },
    "E1": {
        "intent": "new_booking", "name": None, "menu": None,
        "datetime_candidate": "来週平日午後の空き候補(複数)", "confirmed": False,
        "needs_owner_check": False,
    },
    "E2": {
        "intent": "cancel", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": True,
    },
    "E5": {
        "intent": "escalation", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": True,
    },
    "E3": {
        "intent": "new_booking", "name": None, "menu": None,
        "datetime_candidate": "顧客Aが仮押さえ中の枠(確認中のため保留)", "confirmed": False,
        "needs_owner_check": False,
    },
    "E4": {
        "intent": "new_booking", "name": None, "menu": "カット",
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": False,
    },
    "E6": {
        "intent": "faq", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": False,
    },
    "E7": {
        "intent": "escalation", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": True,
    },
    "E8": {
        "intent": "new_booking", "name": "田中", "menu": "カット",
        "datetime_candidate": "来週土曜15時台の候補", "confirmed": False,
        "needs_owner_check": True,
    },
    "E9": {
        "intent": "escalation", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": True,
    },
    "E10": {
        "intent": "faq", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": False,
        "faq_segments": [{"topic": "parking", "resolved": True}],
    },
    "E11": {
        "intent": "escalation", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": True,
    },
    "E12": {
        "intent": "escalation", "name": None, "menu": None,
        "datetime_candidate": None, "confirmed": False,
        "needs_owner_check": True,
    },
    "E13a": {
        "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
        "confirmed": False, "needs_owner_check": False,
        "faq_segments": [
            {"topic": "parking", "resolved": True},
            {"topic": "payment", "resolved": True},
        ],
    },
    "E13b": {
        "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
        "confirmed": False, "needs_owner_check": True,
        "faq_segments": [
            {"topic": "parking", "resolved": True},
            {"topic": "payment", "resolved": False},
        ],
    },
    "E14_faq": {
        "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
        "confirmed": False, "needs_owner_check": False,
        "faq_segments": [{"topic": "payment", "resolved": True}],
    },
    "E14_escalation": {
        "intent": "escalation", "name": None, "menu": None, "datetime_candidate": None,
        "confirmed": False, "needs_owner_check": True,
        "escalation_reason": "unimplemented_feature", "feature_hint": "デポジット決済",
    },
    "E15": {
        "intent": "escalation", "name": None, "menu": None, "datetime_candidate": None,
        "confirmed": False, "needs_owner_check": True,
        "escalation_reason": "unimplemented_feature", "feature_hint": "当日キャンセル料の徴収",
    },
    "E16": {
        "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
        "confirmed": False, "needs_owner_check": True,
        "faq_segments": [
            {"topic": "parking", "resolved": True},
            {"topic": "payment", "resolved": True},
            {"topic": "payment", "resolved": False},
        ],
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
