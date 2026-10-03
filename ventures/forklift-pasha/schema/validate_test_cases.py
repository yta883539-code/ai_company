#!/usr/bin/env python3
"""
schema/output.schema.json(フェーズ3・2026-10-03 01:00 UTC作成)に対する期待JSON出力
サンプルを机上検証するスクリプト。kura-pasha/course-set-pasha/aircon-pashaの
schema/validate_test_cases.pyと同じ位置づけ・同じ簡易バリデータ方式(draft-07の
サブセットのみ解釈)を踏襲した(フェーズ6・2026-10-03 05:00 UTC、pricing-plan.md/
llm-api-cost-estimate.mdの「次のステップ候補」だったfixtureファイル作成に対応)。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- llm-system-prompt-draft.md厳守事項2・3・5(点検種別欠落・annualでの検査業者名欠落・
  著しい入力不足でinsufficient_input)、厳守事項6(対象外要求でout_of_scope)、
  type=dailyでreminder_noticeが常にnullであること(mvp-flow-draft.md)の机上確認を
  主眼とする。
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
    """JSON Schema単体では表現しきれない、status値・type値に応じたnull/非nullの
    依存関係ルールをチェックする(llm-system-prompt-draft.md厳守事項参照)。"""
    errors = []
    status = instance.get("status")

    if status == "generated":
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=generatedのときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=generatedのときmissing_fields_requestはnullである必要があります")
        record = instance.get("inspection_record")
        if record is None:
            errors.append(f"{path}: status=generatedのときinspection_recordは非nullである必要があります")
        else:
            rtype = record.get("type")
            if rtype not in ("daily", "monthly", "annual"):
                errors.append(f"{path}.inspection_record.type: generated時はdaily/monthly/annualのいずれかである必要があります(実際={rtype!r})")
            if rtype == "annual" and record.get("inspector_company") is None:
                errors.append(f"{path}.inspection_record: type=annualのときinspector_companyは非nullである必要があります(厳守事項3)")
            if rtype in ("daily", "monthly") and record.get("inspector_company") is not None:
                errors.append(f"{path}.inspection_record: type={rtype}のときinspector_companyはnullである必要があります")
            if rtype == "daily" and record.get("reminder_notice") is not None:
                errors.append(f"{path}.inspection_record: type=dailyのときreminder_noticeは常にnullである必要があります(mvp-flow-draft.md)")
    elif status == "out_of_scope":
        if instance.get("out_of_scope_message") is None:
            errors.append(f"{path}: status=out_of_scopeのときout_of_scope_messageは非nullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=out_of_scopeのときmissing_fields_requestはnullである必要があります")
        if instance.get("inspection_record") is not None:
            errors.append(f"{path}: status=out_of_scopeのときinspection_recordはnullである必要があります")
    elif status == "insufficient_input":
        if instance.get("missing_fields_request") is None:
            errors.append(f"{path}: status=insufficient_inputのときmissing_fields_requestは非nullである必要があります")
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=insufficient_inputのときout_of_scope_messageはnullである必要があります")
        if instance.get("inspection_record") is not None:
            errors.append(f"{path}: status=insufficient_inputのときinspection_recordはnullである必要があります")

    return errors


def _base_record(**overrides):
    record = {
        "vehicle_id": "2号機",
        "type": "daily",
        "date": "2026-10-03",
        "items": "ブレーキ○、警告灯○、異音なし",
        "result": "異常なし",
        "inspector_name": "山田太郎",
        "inspector_company": None,
        "body": "2026-10-03 2号機 始業前点検 山田太郎 ブレーキ○、警告灯○、異音なし 異常なし",
        "reminder_notice": None,
    }
    record.update(overrides)
    return record


CASE_G1_DAILY = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "inspection_record": _base_record(),
}

CASE_G2_MONTHLY_NO_REMINDER = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "inspection_record": _base_record(
        type="monthly",
        date="2026-10-01",
        body="2026-10-01 2号機 月次自主検査 山田太郎 油圧系統○、フォーク変形なし 異常なし",
        reminder_notice=None,
    ),
}

CASE_G3_MONTHLY_WITH_REMINDER = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "inspection_record": _base_record(
        type="monthly",
        date="2025-11-05",
        body="2025-11-05 2号機 月次自主検査 山田太郎 油圧系統○、フォーク変形なし 異常なし",
        reminder_notice="2号機の月次自主検査の次回実施期限(2025-12-05)が近づいています。",
    ),
}

CASE_G4_ANNUAL_WITH_COMPANY = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "inspection_record": _base_record(
        type="annual",
        date="2026-09-15",
        inspector_name=None,
        inspector_company="株式会社フォーク検査センター",
        body="2026-09-15 2号機 特定自主検査(実施:株式会社フォーク検査センター) 異常なし",
        reminder_notice=None,
    ),
}

CASE_OOS1_UNRELATED_REQUEST = {
    "status": "out_of_scope",
    "out_of_scope_message": "本サービスは点検記録の整形と実施期限の管理支援のみを行っております。",
    "missing_fields_request": None,
    "inspection_record": None,
}

CASE_II1_NO_VEHICLE_ID = {
    "status": "insufficient_input",
    "out_of_scope_message": None,
    "missing_fields_request": "車両番号が読み取れませんでした。どの車両の点検か教えてください。",
    "inspection_record": None,
}

CASE_II2_NO_TYPE = {
    "status": "insufficient_input",
    "out_of_scope_message": None,
    "missing_fields_request": "点検種別(始業前点検・月次自主検査・特定自主検査のいずれか)が読み取れませんでした。",
    "inspection_record": None,
}

CASE_II3_ANNUAL_NO_COMPANY = {
    "status": "insufficient_input",
    "out_of_scope_message": None,
    "missing_fields_request": "特定自主検査の記録には検査業者名が必要です。検査を実施した業者名を教えてください。",
    "inspection_record": None,
}

POSITIVE_CASES = {
    "G1_daily": CASE_G1_DAILY,
    "G2_monthly_no_reminder": CASE_G2_MONTHLY_NO_REMINDER,
    "G3_monthly_with_reminder": CASE_G3_MONTHLY_WITH_REMINDER,
    "G4_annual_with_company": CASE_G4_ANNUAL_WITH_COMPANY,
    "OOS1_unrelated_request": CASE_OOS1_UNRELATED_REQUEST,
    "II1_no_vehicle_id": CASE_II1_NO_VEHICLE_ID,
    "II2_no_type": CASE_II2_NO_TYPE,
    "II3_annual_no_company": CASE_II3_ANNUAL_NO_COMPANY,
}

# ネガティブテスト(バリデータ自体が違反を検出できることの確認用)
NEGATIVE_CASE_ANNUAL_MISSING_COMPANY = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "inspection_record": _base_record(
        type="annual",
        inspector_name=None,
        inspector_company=None,  # 厳守事項3違反: annualなのに検査業者名が無い
        body="2026-09-15 2号機 特定自主検査 異常なし",
    ),
}

NEGATIVE_CASE_DAILY_WITH_REMINDER = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "inspection_record": _base_record(
        reminder_notice="次回期限が近づいています。",  # daily違反: reminder_noticeは常にnull
    ),
}

NEGATIVE_CASE_OOS_WITH_RECORD = {
    "status": "out_of_scope",
    "out_of_scope_message": "本サービスは点検記録の整形と実施期限の管理支援のみを行っております。",
    "missing_fields_request": None,
    "inspection_record": _base_record(),  # 排他性違反: out_of_scopeなのにinspection_recordが非null
}


def _run_case(name, instance, *, expect_errors):
    errors = validate_against_schema(instance, SCHEMA)
    errors += validate_cross_field_rules(instance)
    if expect_errors:
        if errors:
            print(f"[OK] {name} (想定通りエラー検出)")
            for e in errors:
                print(f"      - {e}")
            return True
        print(f"[NG] {name}: 想定した違反を検出できませんでした(バリデータの不備)")
        return False
    else:
        if not errors:
            print(f"[OK] {name}")
            return True
        print(f"[NG] {name}:")
        for e in errors:
            print(f"      - {e}")
        return False


def main():
    total = 0
    failed = 0

    for name, case in POSITIVE_CASES.items():
        total += 1
        if not _run_case(name, case, expect_errors=False):
            failed += 1

    for name, case in {
        "NEG1_annual_missing_company_is_detected": NEGATIVE_CASE_ANNUAL_MISSING_COMPANY,
        "NEG2_daily_with_reminder_is_detected": NEGATIVE_CASE_DAILY_WITH_REMINDER,
        "NEG3_out_of_scope_with_record_is_detected": NEGATIVE_CASE_OOS_WITH_RECORD,
    }.items():
        total += 1
        if not _run_case(name, case, expect_errors=True):
            failed += 1

    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
