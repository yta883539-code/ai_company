#!/usr/bin/env python3
"""
schema/output.schema.json(2026-08-15 08:00 UTC改訂版・フェーズ54)に対する期待JSON出力サンプルを
机上検証するスクリプト。line-reservation-aiのschema/validate_test_cases.pyと同じ位置づけ・
同じ簡易バリデータ方式(draft-07のサブセットのみ解釈)を踏襲した。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- schema-structured-output-compat-check.md(2026-08-07 15:00 UTC)の改訂方針
  (allOf/if-then撤去、全プロパティrequired化+null許容、statusに応じたnull/非nullの
  依存関係はコード側検証で担保)が、実際にサンプル出力に対して機械的に検証可能かを確認する。
- フェーズ11(2026-08-07 20:00 UTC)で`history_row`(単一オブジェクト)を`history_rows`(配列)に
  変更したことに伴い、G4として複数エリア同時更新ケースを追加した。
- フェーズ54(2026-08-15 08:00 UTC)で厳守事項7a(解約意図検知)対応のstatus3値
  (cancellation_intent/downgrade_intent/cancellation_unclear)と`subscription_procedure_notice`
  フィールドを追加したことに伴い、CI1〜CI3として各分岐のケースを追加した。
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

    generated_fields = ["sns_post", "line_web_notice", "history_rows"]

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
                    f"厳守事項7a(iv)によりstatus={status}のときは{expected_link}である必要があります"
                )
    else:
        if instance.get("subscription_procedure_notice") is not None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeはnullである必要があります")

    sns_post = instance.get("sns_post")
    if sns_post and sns_post.get("mentions_photo") is not True and sns_post.get("mentions_photo") is not False:
        errors.append(f"{path}.sns_post.mentions_photo: booleanである必要があります(null不可)")

    history_rows = instance.get("history_rows")
    if status == "generated" and isinstance(history_rows, list) and len(history_rows) == 0:
        errors.append(f"{path}.history_rows: status=generatedのとき空配列は不可です(1件以上必要)")

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
        "history_rows": [
            {
                "revision_date": "2026-08-07",
                "area": "エリアA",
                "tape_color_or_grade_band": "黄テープ",
                "count": 8,
                "feature_keywords": ["ダイナミック", "ムーブ重視"],
            },
        ],
        "unchanged_areas": [],
        "subscription_procedure_notice": None,
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
        "history_rows": [
            {
                "revision_date": "2026-08-07",
                "area": "エリアB",
                "tape_color_or_grade_band": "赤テープ〜黒テープ",
                "count": 5,
                "feature_keywords": ["パワー系", "ランジ"],
            },
        ],
        "unchanged_areas": ["エリアC", "エリアD"],
        "subscription_procedure_notice": None,
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
        "history_rows": [
            {
                "revision_date": None,
                "area": "エリアE",
                "tape_color_or_grade_band": "緑テープ",
                "count": None,
                "feature_keywords": ["バランス系"],
            },
        ],
        "unchanged_areas": [],
        "subscription_procedure_notice": None,
    },
    "G4_multi_area_single_memo": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "sns_post": {
            "body": "【課題入れ替えのお知らせ】エリアF・エリアG・エリアHの3エリアで新着課題を追加しました。エリアF:黄テープ帯6本、エリアG:赤テープ帯4本、エリアH:緑テープ帯3本です。",
            "hashtags": ["#ボルダリング", "#クライミングジム", "#新着課題"],
            "mentions_photo": False,
        },
        "line_web_notice": {
            "body": "エリアF:新着6本(黄テープ帯)、エリアG:新着4本(赤テープ帯)、エリアH:新着3本(緑テープ帯)を追加しました。",
        },
        "history_rows": [
            {
                "revision_date": "2026-08-07",
                "area": "エリアF",
                "tape_color_or_grade_band": "黄テープ",
                "count": 6,
                "feature_keywords": ["テクニカル"],
            },
            {
                "revision_date": "2026-08-07",
                "area": "エリアG",
                "tape_color_or_grade_band": "赤テープ",
                "count": 4,
                "feature_keywords": ["パワー系"],
            },
            {
                "revision_date": "2026-08-07",
                "area": "エリアH",
                "tape_color_or_grade_band": "緑テープ",
                "count": 3,
                "feature_keywords": ["バランス系"],
            },
        ],
        "unchanged_areas": [],
        "subscription_procedure_notice": None,
    },
    "OOS1_membership_question": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは告知文・記録の下書き作成支援のみを行っており、会員管理・予約受付・決済のご案内はできません。",
        "missing_fields_request": None,
        "sns_post": None,
        "line_web_notice": None,
        "history_rows": None,
        "unchanged_areas": [],
        "subscription_procedure_notice": None,
    },
    "II1_no_area_no_count": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "エリア名と本数が不明なため、告知文・記録を作成できません。エリア名(例:エリアA)と入れ替えた本数を教えてください。",
        "sns_post": None,
        "line_web_notice": None,
        "history_rows": None,
        "unchanged_areas": [],
        "subscription_procedure_notice": None,
    },
    "CI1_cancellation_intent_clear": {
        "status": "cancellation_intent",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "sns_post": None,
        "line_web_notice": None,
        "history_rows": None,
        "unchanged_areas": [],
        "subscription_procedure_notice": {
            "kind": "cancellation_intent",
            "body": (
                "解約をご希望とのことで承知しました。現在のご契約はスタンダードプラン"
                "(月15回まで/月額3,480円)です。解約手続き完了後も今回のご請求サイクルの"
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
        "sns_post": None,
        "line_web_notice": None,
        "history_rows": None,
        "unchanged_areas": [],
        "subscription_procedure_notice": {
            "kind": "downgrade_intent",
            "body": (
                "プラン変更(ダウングレード)をご希望とのことで承知しました。解約ではなく"
                "サービス継続のお手続きです。下記リンクのStripeカスタマーポータルから"
                "変更後のプランをお選びください。差額は日割りで精算されます。"
                "▼ {Stripeカスタマーポータル URL}"
            ),
            "includes_portal_link": True,
        },
    },
    "CI3_cancellation_unclear": {
        "status": "cancellation_unclear",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "sns_post": None,
        "line_web_notice": None,
        "history_rows": None,
        "unchanged_areas": [],
        "subscription_procedure_notice": {
            "kind": "cancellation_unclear",
            "body": "解約をご希望でしょうか?よろしければ改めてその旨お知らせください。",
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
