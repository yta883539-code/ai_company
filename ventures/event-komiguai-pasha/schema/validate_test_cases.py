#!/usr/bin/env python3
"""
schema/output.schema.json(フェーズ5作成)に対する期待JSON出力サンプルを机上検証する
スクリプト。kura-pasha/course-set-pasha等のschema/validate_test_cases.pyと同じ位置づけ・
同じ簡易バリデータ方式(draft-07のサブセットのみ解釈)を踏襲した。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- mvp-flow-draft.md(フェーズ2)「出力スキーマ方針」・llm-system-prompt-draft.md(フェーズ3)
  「次回候補」1点目(schema/output.schema.jsonの作成とテストケース設計)に対応したもの。
- status分岐(generated/out_of_scope/insufficient_input)に応じたnull/非null制約(厳守事項1・
  7・8)、notice_board_text.includes_road_use_permit_noteの整合性(厳守事項2)、
  staffing_plan.focusの整合性(厳守事項4)の机上確認を主眼とする。
- 外部ライブラリ(jsonschema等)には依存しない(pure stdlibのみ)。

実行方法: python3 validate_test_cases.py
"""

import json
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

    schema_types = schema["type"] if isinstance(schema.get("type"), list) else [schema.get("type")]

    if "object" in schema_types and isinstance(instance, dict):
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

    if "array" in schema_types and isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: 要素数不足 (期待>={schema['minItems']}, 実際={len(instance)})")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: 要素数過多 (期待<={schema['maxItems']}, 実際={len(instance)})")
        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(instance):
                errors.extend(validate_against_schema(item, items_schema, path=f"{path}[{i}]"))

    if "enum" in schema and instance is not None and instance not in schema["enum"]:
        errors.append(f"{path}: enum不一致 (期待={schema['enum']}, 実際={instance!r})")

    return errors


def validate_cross_field_rules(instance, path="$"):
    """JSON Schema単体では表現しきれない、status値に応じたnull/非nullの依存関係ルールを
    チェックする(llm-system-prompt-draft.md「構造化出力の方針」参照)。"""
    errors = []
    status = instance.get("status")
    generated_fields = ["checklist", "staffing_plan", "notice_board_text", "near_miss_record_template"]

    if status == "generated":
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=generatedのときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=generatedのときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is None:
                errors.append(f"{path}: status=generatedのとき{f}は非nullである必要があります")

        staffing_plan = instance.get("staffing_plan") or {}
        notice = instance.get("notice_board_text") or {}

        # 厳守事項4: admission_typeに対応するfocusが「要すると」される仕様の整合性は
        # LLM入力側の情報であり本テストケースには含まれないため、focusがenum内の値で
        # あることのみをスキーマ側(enum)で確認し、ここでは追加チェックしない。
        if staffing_plan.get("focus") not in ("entry", "exit", "both"):
            errors.append(f"{path}.staffing_plan.focus: 不正な値です(実際={staffing_plan.get('focus')!r})")

        # 厳守事項2: includes_road_use_permit_noteがtrueの場合、本文に注記趣旨の
        # キーワード(「道路使用許可」)が含まれているかを机上確認する(完全な自然言語
        # 一致ではなく簡易キーワードチェック)。
        if notice.get("includes_road_use_permit_note") is True:
            if "道路使用許可" not in (notice.get("body") or ""):
                errors.append(
                    f"{path}.notice_board_text.body: includes_road_use_permit_note=trueなのに"
                    "「道路使用許可」への言及が本文に見当たりません(厳守事項2)"
                )
        elif notice.get("includes_road_use_permit_note") is False:
            if "道路使用許可" in (notice.get("body") or ""):
                errors.append(
                    f"{path}.notice_board_text.body: includes_road_use_permit_note=falseなのに"
                    "本文に「道路使用許可」への言及が含まれています(厳守事項2、冗長な注記)"
                )

        near_miss = instance.get("near_miss_record_template") or {}
        expected_fields = ["発生日時", "場所", "状況", "対応", "再発防止策"]
        actual_fields = [f.get("field_name") for f in near_miss.get("fields", [])]
        if actual_fields != expected_fields:
            errors.append(
                f"{path}.near_miss_record_template.fields: 固定5項目(厳守事項6)と一致しません"
                f"(期待={expected_fields}, 実際={actual_fields})"
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


TEST_CASES = {
    "G1_free_admission_indoor": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "checklist": [
            {"item": "入場口2箇所・退場口1箇所の計3箇所がキャパシティ800人に対し十分な処理能力か", "highlighted": False},
            {"item": "開場16:30〜開演18:00の90分間に導線上の合流・ボトルネックが生じないか", "highlighted": False},
        ],
        "staffing_plan": {
            "focus": "entry",
            "body": (
                "自由入場(整理番号なし)のため、開場直後の入場時集中に重点を置きます。会場スタッフ4名を"
                "入場口2箇所に重点配置してください。外部委託警備員は配置されていないため、区分けは行いません。"
            ),
            "announcement_text": "本日は自由入場となっております。入場口が混み合う場合は係員の案内に従い、分散してお進みください。",
        },
        "notice_board_text": {
            "body": "ご来場の皆様へ。入場口付近が混雑する場合がございます。係員の案内に従い、整列・分散入場にご協力ください。",
            "includes_road_use_permit_note": False,
        },
        "near_miss_record_template": {
            "fields": [
                {"field_name": "発生日時", "description": "発生した日時を記載"},
                {"field_name": "場所", "description": "発生した場所(入場口付近等)を記載"},
                {"field_name": "状況", "description": "発生した状況を記載"},
                {"field_name": "対応", "description": "その場で取った対応を記載"},
                {"field_name": "再発防止策", "description": "今後の再発防止策を記載"},
            ]
        },
    },
    "G2_reserved_seat_with_outdoor_queue": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "checklist": [
            {"item": "入退場共用1箇所がキャパシティ300人に対し十分な処理能力か", "highlighted": True},
        ],
        "staffing_plan": {
            "focus": "exit",
            "body": (
                "全席指定のため、終演直後の一斉退場時の集中に重点を置きます。雑踏警備にあたる入退場口での"
                "流れの調整は外部委託警備員3名の配置案とし、自社スタッフ2名には掲示・誘導アナウンス等の"
                "補助的役割を割り当てます。"
            ),
            "announcement_text": "終演後は係員の案内に従い、順にご退場ください。",
        },
        "notice_board_text": {
            "body": (
                "ご来場の皆様へ。入場口が混み合う場合がございます。待機列が会場外(公道)に及ぶ場合は、"
                "主催者が所轄警察署への道路使用許可の要否をご確認ください。"
            ),
            "includes_road_use_permit_note": True,
        },
        "near_miss_record_template": {
            "fields": [
                {"field_name": "発生日時", "description": "発生した日時を記載"},
                {"field_name": "場所", "description": "発生した場所(入場口付近等)を記載"},
                {"field_name": "状況", "description": "発生した状況を記載"},
                {"field_name": "対応", "description": "その場で取った対応を記載"},
                {"field_name": "再発防止策", "description": "今後の再発防止策を記載"},
            ]
        },
    },
    "OOS1_external_contractor_request": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは一次チェックと文書下書き生成のみを行っております。警備会社への発注契約・所轄警察署への届出代行は主催者・警備責任者自身でご対応ください。",
        "missing_fields_request": None,
        "checklist": None,
        "staffing_plan": None,
        "notice_board_text": None,
        "near_miss_record_template": None,
    },
    "II1_missing_capacity_and_entry_exit": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "会場キャパシティ(capacity)と入退場口数(entry_exit_points)の記載が見当たりません。これらをご入力の上、再度お送りください。",
        "checklist": None,
        "staffing_plan": None,
        "notice_board_text": None,
        "near_miss_record_template": None,
    },
}


# ネガティブテスト: includes_road_use_permit_note=trueなのに本文に注記が無いケースが
# ちゃんと検出されることを確認する(厳守事項2違反の検出能力チェック)。
NEGATIVE_CASE_ROAD_USE_NOTE_MISSING = {
    **TEST_CASES["G1_free_admission_indoor"],
    "notice_board_text": {
        "body": "ご来場の皆様へ。入場口付近が混雑する場合がございます。",
        "includes_road_use_permit_note": True,
    },
}

# ネガティブテスト: near_miss_record_template.fieldsの項目数・項目名がおかしいケースが
# ちゃんと検出されることを確認する。
NEGATIVE_CASE_NEAR_MISS_FIELDS_WRONG = {
    **TEST_CASES["G1_free_admission_indoor"],
    "near_miss_record_template": {
        "fields": [
            {"field_name": "発生日時", "description": "発生した日時を記載"},
            {"field_name": "場所", "description": "発生した場所を記載"},
        ]
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

    total += 1
    neg_errors = validate_against_schema(NEGATIVE_CASE_ROAD_USE_NOTE_MISSING, SCHEMA)
    neg_errors += validate_cross_field_rules(NEGATIVE_CASE_ROAD_USE_NOTE_MISSING)
    if neg_errors:
        print("[OK] NEG1_road_use_note_missing_is_detected (想定通りエラー検出)")
        for e in neg_errors:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG1_road_use_note_missing_is_detected: 注記の欠落を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors2 = validate_against_schema(NEGATIVE_CASE_NEAR_MISS_FIELDS_WRONG, SCHEMA)
    neg_errors2 += validate_cross_field_rules(NEGATIVE_CASE_NEAR_MISS_FIELDS_WRONG)
    if neg_errors2:
        print("[OK] NEG2_near_miss_fields_wrong_is_detected (想定通りエラー検出)")
        for e in neg_errors2:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG2_near_miss_fields_wrong_is_detected: 項目数不一致を検出できませんでした(バリデータの不備)")

    print(f"\n{total - failed}/{total} 件パス")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
