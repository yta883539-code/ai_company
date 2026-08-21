#!/usr/bin/env python3
"""
schema/output.schema.json(2026-08-09 15:00 UTC作成)に対する期待JSON出力サンプルを
机上検証するスクリプト。course-set-pasha/schema/validate_test_cases.py・
line-reservation-ai/schema/validate_test_cases.pyと同じ位置づけ・同じ簡易バリデータ方式
(draft-07のサブセットのみ解釈)を踏襲した。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- output.schema.jsonのstatus分岐(generated/out_of_scope/insufficient_input)が、
  実際のサンプル出力に対して機械的に検証可能かを確認する。
- 2026-08-21 14:00 UTC改訂: 同一訪問先で2台以上を同時に分解洗浄するケースが業界で一般的と
  判明したため(market-research.md参照)、history_rowを単一オブジェクトから配列
  (history_rows)に変更した。course-set-pasha/schema/validate_test_cases.pyと同じ
  items(配列要素)対応を追加した。
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

    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(validate_against_schema(item, schema["items"], path=f"{path}[{i}]"))

    if "enum" in schema and instance is not None and instance not in schema["enum"]:
        errors.append(f"{path}: enum不一致 (期待={schema['enum']}, 実際={instance!r})")

    return errors


def validate_cross_field_rules(instance, path="$"):
    """JSON Schema単体では表現しきれない、status値に応じたnull/非nullの依存関係、および
    next_recommended_date_is_estimateとhistory_rows[*].next_recommended_dateの整合性ルールを
    チェックする(output.schema.jsonの各fieldのdescriptionに記載の方針に対応)。"""
    errors = []
    status = instance.get("status")

    generated_fields = ["completion_report", "care_guide", "history_rows"]

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

    cancellation_statuses = ("cancellation_intent", "downgrade_intent", "cancellation_unclear")
    if status in cancellation_statuses:
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status={status}のときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status={status}のときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status={status}のとき{f}はnullである必要があります")
        notice = instance.get("subscription_procedure_notice")
        if notice is None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeは非nullである必要があります")
        else:
            if notice.get("kind") != status:
                errors.append(f"{path}.subscription_procedure_notice.kind: statusと一致する必要があります(期待={status}, 実際={notice.get('kind')!r})")
            expected_link = status in ("cancellation_intent", "downgrade_intent")
            if notice.get("includes_portal_link") is not expected_link:
                errors.append(
                    f"{path}.subscription_procedure_notice.includes_portal_link: "
                    f"厳守事項6a(iv)によりstatus={status}のときは{expected_link}である必要があります"
                )
    else:
        if instance.get("subscription_procedure_notice") is not None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeはnullである必要があります")

    completion_report = instance.get("completion_report")
    if completion_report is not None:
        m = completion_report.get("mentions_refrigerant_or_electrical")
        if m is not True and m is not False:
            errors.append(f"{path}.completion_report.mentions_refrigerant_or_electrical: booleanである必要があります(null不可)")
        if m is True:
            errors.append(f"{path}.completion_report: 厳守事項1違反(冷媒・電気系統への専門的助言に言及)の疑いがあるサンプルです")

    care_guide = instance.get("care_guide")
    history_rows = instance.get("history_rows")
    if status == "generated" and isinstance(history_rows, list) and len(history_rows) == 0:
        errors.append(f"{path}.history_rows: status=generatedのとき空配列は不可です(1件以上必要)")
    if care_guide is not None:
        is_estimate = care_guide.get("next_recommended_date_is_estimate")
        if is_estimate is not True and is_estimate is not False:
            errors.append(f"{path}.care_guide.next_recommended_date_is_estimate: booleanである必要があります(null不可)")
        if is_estimate is False and isinstance(history_rows, list):
            for i, row in enumerate(history_rows):
                if row.get("next_recommended_date") is None:
                    errors.append(
                        f"{path}.history_rows[{i}]: next_recommended_date_is_estimate=falseの場合、"
                        "next_recommended_dateはnullであってはなりません(入力メモ由来の値が必須)"
                    )

    return errors


# mvp-flow-draft.md・llm-system-prompt-draft.mdで検討してきた入力パターンを踏まえ、
# 期待される構造化出力を机上で書き起こしたフィクスチャ。
TEST_CASES = {
    "G1_basic": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "completion_report": {
            "body": "壁掛け型2.2kWのエアコンについて、フィルター・熱交換器・送風ファンまで分解洗浄いたしました。"
                    "カビ・ホコリの汚れは中程度でしたが、洗浄後はきれいな状態になっております。防カビコートも施工いたしました。",
            "mentions_refrigerant_or_electrical": False,
        },
        "care_guide": {
            "body": "フィルターは月1回程度を目安に、掃除機やご自身で水洗いいただくと効果的です。"
                    "次回の分解洗浄は来年同時期を目安にご検討ください。自己分解洗浄は内部の破損・感電等のリスクがあるため、"
                    "分解を伴う清掃は専門業者へのご依頼をおすすめします。",
            "next_recommended_date_is_estimate": False,
        },
        "history_rows": [
            {
                "work_date": "2026-08-09",
                "model_type_and_capacity": "壁掛け型2.2kW",
                "dirt_condition": "カビ・ホコリ汚れ中程度",
                "additional_treatment": "防カビコートあり",
                "next_recommended_date": "来年同時期",
            },
        ],
        "subscription_procedure_notice": None,
    },
    "G2_estimate_next_date": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "completion_report": {
            "body": "壁掛け型(お掃除機能付き)のエアコンについて、フィルター・熱交換器まで分解洗浄いたしました。"
                    "汚れは軽度でした。",
            "mentions_refrigerant_or_electrical": False,
        },
        "care_guide": {
            "body": "フィルターは2週間に1回程度の目安でお手入れください。次回の分解洗浄の時期については、"
                    "使用状況やご家庭の環境により差がありますが、一般的な目安として1〜2年に1回程度のご検討をおすすめします"
                    "(今回のメモに次回推奨時期の記載が無いため、あくまで一般的な目安です)。自己分解洗浄は内部の破損・"
                    "感電等のリスクがあるため、分解を伴う清掃は専門業者へのご依頼をおすすめします。",
            "next_recommended_date_is_estimate": True,
        },
        "history_rows": [
            {
                "work_date": "2026-08-09",
                "model_type_and_capacity": "壁掛け型(お掃除機能付き)",
                "dirt_condition": "軽度",
                "additional_treatment": "なし",
                "next_recommended_date": None,
            },
        ],
        "subscription_procedure_notice": None,
    },
    "G3_model_and_date_unextractable": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "completion_report": {
            "body": "エアコンの分解洗浄を実施いたしました。フィルター・熱交換器の汚れがひどい状態でしたが、"
                    "洗浄後はきれいな状態になっております。",
            "mentions_refrigerant_or_electrical": False,
        },
        "care_guide": {
            "body": "フィルターは月1回程度を目安にお手入れください。次回の分解洗浄は1〜2年に1回程度が一般的な目安です"
                    "(今回のメモに次回推奨時期の記載が無いため、あくまで一般的な目安です)。自己分解洗浄は内部の破損・"
                    "感電等のリスクがあるため、分解を伴う清掃は専門業者へのご依頼をおすすめします。",
            "next_recommended_date_is_estimate": True,
        },
        "history_rows": [
            {
                "work_date": None,
                "model_type_and_capacity": None,
                "dirt_condition": "ひどい状態",
                "additional_treatment": "なし",
                "next_recommended_date": None,
            },
        ],
        "subscription_procedure_notice": None,
    },
    "G4_multiple_units_same_visit": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "completion_report": {
            "body": "リビングの壁掛け型2.8kW・寝室の壁掛け型2.2kWの2台について、フィルター・熱交換器・"
                    "送風ファンまで分解洗浄いたしました。リビングは汚れが中程度、寝室は軽度でした。"
                    "2台とも洗浄後はきれいな状態になっております。",
            "mentions_refrigerant_or_electrical": False,
        },
        "care_guide": {
            "body": "フィルターは月1回程度を目安に、掃除機やご自身で水洗いいただくと効果的です。"
                    "次回の分解洗浄はいずれも来年同時期を目安にご検討ください。自己分解洗浄は内部の破損・感電等の"
                    "リスクがあるため、分解を伴う清掃は専門業者へのご依頼をおすすめします。",
            "next_recommended_date_is_estimate": False,
        },
        "history_rows": [
            {
                "work_date": "2026-08-21",
                "model_type_and_capacity": "リビングの壁掛け型2.8kW",
                "dirt_condition": "中程度",
                "additional_treatment": "なし",
                "next_recommended_date": "来年同時期",
            },
            {
                "work_date": "2026-08-21",
                "model_type_and_capacity": "寝室の壁掛け型2.2kW",
                "dirt_condition": "軽度",
                "additional_treatment": "なし",
                "next_recommended_date": "来年同時期",
            },
        ],
        "subscription_procedure_notice": None,
    },
    "OOS1_reservation_question": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは作業完了報告・お手入れ案内文の下書き作成支援のみを行っており、"
                                 "会員管理・予約受付・決済のご案内はできません。",
        "missing_fields_request": None,
        "completion_report": None,
        "care_guide": None,
        "history_rows": None,
        "subscription_procedure_notice": None,
    },
    "II1_no_work_content": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "分解洗浄を実施したことが読み取れる記述が見当たりません。"
                                   "機種系統・号数、洗浄範囲(フィルター・熱交換器等)、汚れ状況を教えてください。",
        "completion_report": None,
        "care_guide": None,
        "history_rows": None,
        "subscription_procedure_notice": None,
    },
    "CI1_cancellation_intent_clear": {
        "status": "cancellation_intent",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "completion_report": None,
        "care_guide": None,
        "history_rows": None,
        "subscription_procedure_notice": {
            "kind": "cancellation_intent",
            "body": (
                "解約をご希望とのことで承知しました。現在のご契約はスタンダードプラン"
                "(月90回まで/月額5,980円)です。解約手続き完了後も今回のご請求サイクルの"
                "終了日まではサービスを引き続きご利用いただけます。日割りでの返金は行って"
                "おりません。下記リンクから解約手続きにお進みください。"
                "▼ {Stripeカスタマーポータル URL}"
            ),
            "includes_portal_link": True,
        },
    },
    "CI2_downgrade_intent": {
        "status": "downgrade_intent",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "completion_report": None,
        "care_guide": None,
        "history_rows": None,
        "subscription_procedure_notice": {
            "kind": "downgrade_intent",
            "body": (
                "プラン変更をご希望とのことで承知しました。解約ではなくサービス継続の"
                "お手続きです。下記リンクのStripeカスタマーポータルから変更後のプランを"
                "お選びください。差額は日割りで精算されます。"
                "▼ {Stripeカスタマーポータル URL}"
            ),
            "includes_portal_link": True,
        },
    },
    "CI3_cancellation_unclear": {
        "status": "cancellation_unclear",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "completion_report": None,
        "care_guide": None,
        "history_rows": None,
        "subscription_procedure_notice": {
            "kind": "cancellation_unclear",
            "body": "解約(またはプラン変更)をご希望でしょうか?よろしければ改めてその旨お知らせください。",
            "includes_portal_link": False,
        },
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
