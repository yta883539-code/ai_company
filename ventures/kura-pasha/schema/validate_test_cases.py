#!/usr/bin/env python3
"""
schema/output.schema.json(2026-09-06 05:00 UTC作成)に対する期待JSON出力サンプルを
机上検証するスクリプト。course-set-pasha/line-reservation-aiのschema/validate_test_cases.pyと
同じ位置づけ・同じ簡易バリデータ方式(draft-07のサブセットのみ解釈)を踏襲した。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- llm-system-prompt-draft.md「次の課題」3点目(status分岐(generated/out_of_scope/
  insufficient_input)とcategory(new/repair)整合性検証用テストケース作成)に対応したもの。
- order_summary.categoryとdelivery_notice.categoryが一致することの検証(厳守事項4)、
  categoryがnew/repairの場合それぞれでdelivery_notice.bodyの分岐内容が反映されているかの
  机上確認を主眼とする。
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
    """output.schema.json のサブセット(type/enum/required/additionalProperties)
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

    if "enum" in schema and instance is not None and instance not in schema["enum"]:
        errors.append(f"{path}: enum不一致 (期待={schema['enum']}, 実際={instance!r})")

    return errors


def validate_cross_field_rules(instance, path="$"):
    """JSON Schema単体では表現しきれない、status値・category値に応じたnull/非nullの
    依存関係ルールをチェックする(llm-system-prompt-draft.md「構造化出力の方針」参照)。"""
    errors = []
    status = instance.get("status")

    generated_fields = ["order_summary", "delivery_notice", "care_notice"]

    if status == "generated":
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=generatedのときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=generatedのときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is None:
                errors.append(f"{path}: status=generatedのとき{f}は非nullである必要があります")

        order_summary = instance.get("order_summary") or {}
        delivery_notice = instance.get("delivery_notice") or {}
        os_category = order_summary.get("category")
        dn_category = delivery_notice.get("category")
        if os_category is None:
            errors.append(f"{path}.order_summary.category: status=generatedのとき非nullである必要があります(厳守事項3)")
        if os_category != dn_category:
            errors.append(
                f"{path}: order_summary.category({os_category!r})とdelivery_notice.category"
                f"({dn_category!r})が一致していません(厳守事項4)"
            )
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

    return errors


# mvp-flow-draft.md・llm-system-prompt-draft.mdで検討してきた入力パターンを踏まえ、
# 期待される構造化出力を机上で書き起こしたフィクスチャ。
TEST_CASES = {
    "G1_new_basic": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": {
            "category": "new",
            "saddle_type": "ブリティッシュ",
            "leather_type": "牛革",
            "hardware_spec": None,
            "usage": "競技用",
            "due_date": "3ヶ月",
            "remarks": None,
            "body": "区分:新規制作/鞍の型:ブリティッシュ/革の種類:牛革/用途:競技用/納期:3ヶ月",
        },
        "delivery_notice": {
            "category": "new",
            "body": (
                "新しい鞍をお届けします。装着直後は革が体に馴染むまで時間がかかりますので、"
                "最初は短時間の騎乗から始め、徐々に締め具合を調整してください。雨天時は"
                "使用後に乾いた布で水分を拭き取ってください。"
            ),
        },
        "care_notice": (
            "定期的にオイル・クリームで革に保湿を与えてください。高温多湿・直射日光を避けた"
            "場所で保管し、カビ・ひび割れを防いでください。金具部分は使用後に乾拭きしさびを防いでください。"
        ),
    },
    "G2_repair_with_remarks": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": {
            "category": "repair",
            "saddle_type": "ウエスタン",
            "leather_type": "馬革",
            "hardware_spec": "ステンレス金具",
            "usage": "日常騎乗用",
            "due_date": "2週間",
            "remarks": "鐙革の縫い目がほつれている、金具のさびが目立つ",
            "body": (
                "区分:修理/鞍の型:ウエスタン/革の種類:馬革/金具仕様:ステンレス金具/"
                "用途:日常騎乗用/納期:2週間/症状:鐙革の縫い目がほつれている、金具のさびが目立つ"
            ),
        },
        "delivery_notice": {
            "category": "repair",
            "body": (
                "修理箇所(鐙革の縫い目、金具のさび)の補修が完了しました。修理直後は新規制作時ほど"
                "長期の慣らしは不要ですが、初回騎乗時は締め具合に違和感が無いかご確認ください。"
            ),
        },
        "care_notice": (
            "定期的にオイル・クリームで革に保湿を与えてください。高温多湿・直射日光を避けた"
            "場所で保管し、カビ・ひび割れを防いでください。金具部分は使用後に乾拭きしさびを防いでください。"
        ),
    },
    "OOS1_membership_question": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは受注整理・納品案内・お手入れ案内の下書き作成支援のみを行っております。",
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
    },
    "II1_no_category": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "区分(新規制作/修理)が不明なため下書きを作成できません。区分を教えてください。",
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
    },
    "II2_no_saddle_type": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "鞍の型が不明なため下書きを作成できません。鞍の型(ブリティッシュ/ウエスタン等)を教えてください。",
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
    },
}

# 厳守事項4違反(categoryの不一致)を意図的に仕込んだ不正フィクスチャ。
# validate_cross_field_rulesが実際にこの不整合を検出できることを確認するための
# ネガティブテストであり、TEST_CASESには含めずmain()内で単体に検証する。
NEGATIVE_CASE_CATEGORY_MISMATCH = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": {
        "category": "new",
        "saddle_type": "ブリティッシュ",
        "leather_type": "牛革",
        "hardware_spec": None,
        "usage": "競技用",
        "due_date": "3ヶ月",
        "remarks": None,
        "body": "区分:新規制作/...",
    },
    "delivery_notice": {
        "category": "repair",
        "body": "修理箇所の説明...",
    },
    "care_notice": "定期的な保湿・保管環境・さび防止手入れ...",
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

    # ネガティブテスト: category不一致がちゃんと検出されることを確認する
    total += 1
    neg_errors = validate_against_schema(NEGATIVE_CASE_CATEGORY_MISMATCH, SCHEMA)
    neg_errors += validate_cross_field_rules(NEGATIVE_CASE_CATEGORY_MISMATCH)
    if neg_errors:
        print("[OK] NEG1_category_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG1_category_mismatch_is_detected: category不一致を検出できませんでした(バリデータの不備)")

    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
