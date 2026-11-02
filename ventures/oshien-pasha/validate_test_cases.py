#!/usr/bin/env python3
"""
input-output-sample-mapping.md に記載された「期待する出力」を
schema/output.schema.json に対して机上検証するスクリプト
(line-reservation-aiのvalidate_test_cases.py相当、llm-quality-verification-plan.md
「検証手順」次回候補(2)に対応)。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- input-output-sample-mapping.mdで人手で積み上げてきた「期待構造化出力」の記述同士に
  矛盾がないか(フィールド抜け・enum値の誤字・statusごとのnull制約違反など)を機械的に
  チェックする、実装フェーズ着手の第一歩。
- 外部ライブラリ(jsonschema等)には依存しない(pure stdlibのみ)。
- N3(複数会場「ハシゴ」対応)は、multi-venue-hashigo-schema-design.md(README.md
  フェーズ58)で`itinerary_draft`・`day_timetable`を会場単位オブジェクトの配列に
  改訂する方針が確定したことを受け、本フェーズでschema/output.schema.json改訂と
  合わせてTEST_CASESに追加した(配列長2)。既存7フィクスチャ(N1・N2・N4 join/skip・
  E1・E2・E3・E4)はいずれも配列長1形式に書き換えた。E4(チケット代等の取り扱い)は
  llm-system-prompt-draft.md厳守事項3a(新設)により方針が確定したため、フェーズ57で
  TEST_CASESに追加した。

実行方法: python3 validate_test_cases.py
"""

import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema" / "output.schema.json"

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

    type_spec = schema.get("type")
    types = type_spec if isinstance(type_spec, list) else [type_spec] if type_spec else []

    if "object" in types and isinstance(instance, dict):
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

    if "array" in types and isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(validate_against_schema(item, schema["items"], path=f"{path}[{i}]"))

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: enum不一致 (期待={schema['enum']}, 実際={instance!r})")

    return errors


# status分岐時の各フィールドのnull制約(schema/output.schema.jsonの各プロパティdescription
# 「status=...の場合のみ非nullとなる」「status!=...のときは必ずnull」に対応するクロス
# フィールドルール)。
_STATUS_NONNULL_FIELDS = {
    "generated": ["itinerary_draft", "day_timetable", "cost_estimate", "hashigo_check"],
    "out_of_scope": ["out_of_scope_message"],
    "insufficient_input": ["missing_fields_request"],
}
_ALL_STATUS_DEPENDENT_FIELDS = [
    "out_of_scope_message", "missing_fields_request",
    "itinerary_draft", "day_timetable", "cost_estimate", "hashigo_check",
]


def validate_cross_field_rules(instance, path="$"):
    """JSON Schema単体では表現しきれない、設計ドキュメント上の依存関係ルールをチェックする。"""
    errors = []

    status = instance.get("status")
    nonnull_fields = _STATUS_NONNULL_FIELDS.get(status, [])
    for field in _ALL_STATUS_DEPENDENT_FIELDS:
        value = instance.get(field)
        if field in nonnull_fields:
            if value is None:
                errors.append(f"{path}: status='{status}'のとき'{field}'はnullであってはなりません")
        else:
            if value is not None:
                errors.append(f"{path}: status='{status}'のとき'{field}'は必ずnullである必要があります")

    hashigo = instance.get("hashigo_check")
    if isinstance(hashigo, dict) and hashigo.get("applicable") is False:
        if hashigo.get("risk_level") is not None:
            errors.append(f"{path}.hashigo_check: applicable=falseのときrisk_levelはnullである必要があります")
        if hashigo.get("note") is not None:
            errors.append(f"{path}.hashigo_check: applicable=falseのときnoteはnullである必要があります")

    return errors


def validate_goods_line_rule(case_id, instance, goods_line_intention):
    """goods-line-participation-input-field-design.md・llm-system-prompt-draft.md厳守事項4a
    のgoods_line_intention(join/skip/未記載)3値分岐がday_timetableに反映されているかを確認する。
    goods_line_intention自体は入力側フィールドであり出力スキーマには含まれないため、
    テストケースのメタデータとして別途保持し、day_timetable配列内の各会場のtimetable行
    (time_label/action)から「グッズ列」関連の行の有無を機械的にチェックする
    (day_timetableは会場単位オブジェクトの配列、multi-venue-hashigo-schema-design.md参照)。"""
    errors = []
    day_timetable = instance.get("day_timetable") or []
    has_goods_line_row = any(
        "グッズ列" in (row.get("time_label", "") + row.get("action", ""))
        for venue_entry in day_timetable
        for row in venue_entry.get("timetable", [])
    )

    if goods_line_intention == "skip" and has_goods_line_row:
        errors.append(
            f"{case_id}.day_timetable: goods_line_intention='skip'のとき"
            f"「グッズ列」関連の行を含めてはなりません(厳守事項4a準拠)"
        )
    elif goods_line_intention == "join" and not has_goods_line_row:
        errors.append(
            f"{case_id}.day_timetable: goods_line_intention='join'のとき"
            f"「グッズ列」目安到着の行が最低1件必要です(厳守事項4a準拠)"
        )
    # 未記載(None)の場合は両論併記の一言に留める方針のみでday_timetable行数の制約はないため
    # 機械チェック対象外(input-output-sample-mapping.md N4ケース参照)。

    return errors


# input-output-sample-mapping.md に明記された「期待する主な分岐・根拠」をそのまま
# 構造化出力として書き起こしたフィクスチャ。具体的な数値(交通費・滞在候補地名等)は
# 「当たりの概算」の一例であり、実際の金額・地名確認はvenue-master-draft.md整備後の
# 次回課題として残る。
TEST_CASES = {
    "N1": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "itinerary_draft": [
            {
                "venue_name_input": "東京ドーム",
                "venue_matched": True,
                "nearest_station_note": "水道橋駅・後楽園駅から徒歩5分前後",
                "lodging_area_candidates": ["水道橋駅周辺", "後楽園駅周辺"],
                "transport_note": "最寄り駅までの交通手段・乗換を確認のうえ移動してください(実際の経路確認は本人が行う)",
            },
        ],
        "day_timetable": [
            {
                "venue_name_input": "東京ドーム",
                "timetable": [
                    {"time_label": "開場目安", "action": "開場時刻を確認し会場入り"},
                    {"time_label": "グッズ列目安到着", "action": "缶バッジ購入希望のため開場前の到着を検討"},
                ],
            },
        ],
        "cost_estimate": {
            "transport_yen": 2000,
            "lodging_yen": None,
            "goods_yen": 800,
            "note": "予算総額(交通込み3万円想定)の目安内訳。缶バッジの実際の価格は会場・時期により異なるため現地確認が必要。",
        },
        "hashigo_check": {"applicable": False, "risk_level": None, "note": None},
    },
    "N2": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "itinerary_draft": [
            {
                "venue_name_input": "○○市民会館",
                "venue_matched": False,
                "nearest_station_note": "会場名を確認できなかったため、公式サイト・地図アプリでの最寄り駅確認を案内",
                "lodging_area_candidates": [],
                "transport_note": "最寄り駅が未確認のため、公式サイト等でアクセス方法を確認してください",
            },
        ],
        "day_timetable": [
            {
                "venue_name_input": "○○市民会館",
                "timetable": [
                    {"time_label": "開場目安", "action": "開場時刻を公式サイトで確認し会場入り"},
                ],
            },
        ],
        "cost_estimate": {
            "transport_yen": None,
            "lodging_yen": None,
            "goods_yen": None,
            "note": "予算未定のため概算不可。会場・交通手段確定後に再入力を推奨。",
        },
        "hashigo_check": {"applicable": False, "risk_level": None, "note": None},
    },
    "N3": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "itinerary_draft": [
            {
                "venue_name_input": "京セラドーム大阪",
                "venue_matched": True,
                "nearest_station_note": "JRおおさか東線・地下鉄ドーム前千代崎駅から徒歩2分前後",
                "lodging_area_candidates": ["難波・心斎橋エリア"],
                "transport_note": "最寄り駅までの交通手段・乗換を確認のうえ移動してください(実際の経路確認は本人が行う)",
            },
            {
                "venue_name_input": "大阪城ホール",
                "venue_matched": True,
                "nearest_station_note": "JR大阪城公園駅から徒歩約3分",
                "lodging_area_candidates": ["難波・心斎橋エリア"],
                "transport_note": "前日と同エリアに宿泊する場合、最寄り駅までの交通手段・乗換を確認のうえ移動してください(実際の経路確認は本人が行う)",
            },
        ],
        "day_timetable": [
            {
                "venue_name_input": "京セラドーム大阪",
                "timetable": [
                    {"time_label": "開場目安(1日目)", "action": "昼公演のため開場時刻を確認し会場入り"},
                ],
            },
            {
                "venue_name_input": "大阪城ホール",
                "timetable": [
                    {"time_label": "開場目安(2日目)", "action": "前日の移動・宿泊を踏まえ開場時刻を確認し会場入り"},
                ],
            },
        ],
        "cost_estimate": {
            "transport_yen": 4000,
            "lodging_yen": 8000,
            "goods_yen": None,
            "note": "2会場間の移動費(京セラドーム大阪⇔大阪城ホール)・1泊分の宿泊費を含む目安。連日参加のため複数区間の移動費が交通費に含まれる。",
        },
        "hashigo_check": {
            "applicable": True,
            "risk_level": "low",
            "note": "連日・別会場のため移動自体に無理は小さいが、1日目公演終了から2日目開場までの移動・宿泊の時間配分は本人側での確認を推奨する一般的な目安。",
        },
    },
    "N4_skip": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "itinerary_draft": [
            {
                "venue_name_input": "有明アリーナ",
                "venue_matched": True,
                "nearest_station_note": "りんかい線国際展示場駅・ゆりかもめ有明駅から徒歩圏",
                "lodging_area_candidates": ["有明・豊洲エリア"],
                "transport_note": "最寄り駅までの交通手段・乗換を確認のうえ移動してください(実際の経路確認は本人が行う)",
            },
        ],
        "day_timetable": [
            {
                "venue_name_input": "有明アリーナ",
                "timetable": [
                    {"time_label": "開場30分前目安", "action": "会場入り"},
                ],
            },
        ],
        "cost_estimate": {
            "transport_yen": 1500,
            "lodging_yen": None,
            "goods_yen": None,
            "note": "グッズ列不参加のため物販予算は概算対象外。チケットは当選済みのため券面代は含めない。",
        },
        "hashigo_check": {"applicable": False, "risk_level": None, "note": None},
        "_goods_line_intention": "skip",
    },
    "N4_join": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "itinerary_draft": [
            {
                "venue_name_input": "有明アリーナ",
                "venue_matched": True,
                "nearest_station_note": "りんかい線国際展示場駅・ゆりかもめ有明駅から徒歩圏",
                "lodging_area_candidates": ["有明・豊洲エリア"],
                "transport_note": "最寄り駅までの交通手段・乗換を確認のうえ移動してください(実際の経路確認は本人が行う)",
            },
        ],
        "day_timetable": [
            {
                "venue_name_input": "有明アリーナ",
                "timetable": [
                    {"time_label": "グッズ列目安到着", "action": "開場時刻より前到着を検討"},
                    {"time_label": "開場30分前目安", "action": "会場入り"},
                ],
            },
        ],
        "cost_estimate": {
            "transport_yen": 1500,
            "lodging_yen": None,
            "goods_yen": None,
            "note": "グッズ列参加希望のため早め到着を前提とした目安。チケットは当選済みのため券面代は含めない。",
        },
        "hashigo_check": {"applicable": False, "risk_level": None, "note": None},
        "_goods_line_intention": "join",
    },
    "E1": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "会場名・観戦予定日・枚数が確認できないため、具体的な会場名・日時・枚数をお知らせください(推測では記入しません)。",
        "itinerary_draft": None,
        "day_timetable": None,
        "cost_estimate": None,
        "hashigo_check": None,
    },
    "E2": {
        "status": "out_of_scope",
        "out_of_scope_message": "具体的な空席の在庫確認は本サービスでは行っておりません。公式販売サイト・会場窓口にてご確認ください。",
        "missing_fields_request": None,
        "itinerary_draft": None,
        "day_timetable": None,
        "cost_estimate": None,
        "hashigo_check": None,
    },
    "E3": {
        "status": "out_of_scope",
        "out_of_scope_message": "チケットの予約・決済代行は本サービスでは行っておりません。実際の予約・決済はご本人でお願いいたします。",
        "missing_fields_request": None,
        "itinerary_draft": None,
        "day_timetable": None,
        "cost_estimate": None,
        "hashigo_check": None,
    },
    "E4": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "itinerary_draft": [
            {
                "venue_name_input": "東京ドーム",
                "venue_matched": True,
                "nearest_station_note": "水道橋駅・後楽園駅から徒歩5分前後",
                "lodging_area_candidates": ["水道橋駅周辺", "後楽園駅周辺"],
                "transport_note": "最寄り駅までの交通手段・乗換を確認のうえ移動してください(実際の経路確認は本人が行う)",
            },
        ],
        "day_timetable": [
            {
                "venue_name_input": "東京ドーム",
                "timetable": [
                    {"time_label": "開場目安", "action": "開場時刻を確認し会場入り"},
                ],
            },
        ],
        "cost_estimate": {
            "transport_yen": None,
            "lodging_yen": None,
            "goods_yen": None,
            "note": "チケット代(5万円)は本見積りの対象外(交通・宿泊・物販のみ)のため、各金額には反映していません。交通・宿泊・物販それぞれの予算感の言及が無いため全てnull。",
        },
        "hashigo_check": {"applicable": False, "risk_level": None, "note": None},
    },
}


def main():
    total = 0
    failed = 0
    for case_id, raw_instance in TEST_CASES.items():
        total += 1
        goods_line_intention = raw_instance.get("_goods_line_intention")
        instance = {k: v for k, v in raw_instance.items() if not k.startswith("_")}

        errors = validate_against_schema(instance, SCHEMA)
        errors += validate_cross_field_rules(instance)
        if goods_line_intention is not None:
            errors += validate_goods_line_rule(case_id, instance, goods_line_intention)

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
