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
import re
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

        # 厳守事項4: focus=bothの場合、どちらがより集中するかは主催者自身の判断に委ねる旨を
        # body内に明示する必要がある(機械的なキーワードチェック、完全な自然言語一致ではない)。
        if staffing_plan.get("focus") == "both":
            if "主催者" not in (staffing_plan.get("body") or ""):
                errors.append(
                    f"{path}.staffing_plan.body: focus=bothなのに主催者自身への判断委任の"
                    "記載が見当たりません(厳守事項4)"
                )

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

        # 厳守事項7(フェーズ25追加): status=generatedでもfee_inquiry_noteが非nullの場合
        # (会場情報と料金問い合わせが混在する入力)、out_of_scope_message側のチェックと同様に
        # 具体的な料金額(数字+「円」)を案内してしまっていないかを機械的に確認する。
        fee_inquiry_note = instance.get("fee_inquiry_note")
        if fee_inquiry_note is not None and re.search(r"\d+\s*円", fee_inquiry_note):
            errors.append(
                f"{path}.fee_inquiry_note: 具体的な料金額への言及が含まれています"
                f"(厳守事項7、本文={fee_inquiry_note!r})"
            )
    elif status == "out_of_scope":
        if instance.get("out_of_scope_message") is None:
            errors.append(f"{path}: status=out_of_scopeのときout_of_scope_messageは非nullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=out_of_scopeのときmissing_fields_requestはnullである必要があります")
        if instance.get("fee_inquiry_note") is not None:
            errors.append(f"{path}: status=out_of_scopeのときfee_inquiry_noteはnullである必要があります(厳守事項7、フェーズ25)")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status=out_of_scopeのとき{f}はnullである必要があります")

        # 厳守事項7(フェーズ24追加): 料金プラン・契約・支払い関連の問い合わせがout_of_scopeに
        # 振られた場合でも、out_of_scope_message自体が具体的な料金額(数字+「円」)を案内して
        # しまっていないかを機械的に確認する(「具体的な料金案内は一切行わない」の違反検出)。
        out_of_scope_message = instance.get("out_of_scope_message") or ""
        if re.search(r"\d+\s*円", out_of_scope_message):
            errors.append(
                f"{path}.out_of_scope_message: 具体的な料金額への言及が含まれています"
                f"(厳守事項7、本文={out_of_scope_message!r})"
            )
    elif status == "insufficient_input":
        if instance.get("missing_fields_request") is None:
            errors.append(f"{path}: status=insufficient_inputのときmissing_fields_requestは非nullである必要があります")
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=insufficient_inputのときout_of_scope_messageはnullである必要があります")
        if instance.get("fee_inquiry_note") is not None:
            errors.append(f"{path}: status=insufficient_inputのときfee_inquiry_noteはnullである必要があります(厳守事項7、フェーズ25)")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status=insufficient_inputのとき{f}はnullである必要があります")

    return errors


def check_personal_name_leakage(instance, forbidden_terms, path="$"):
    """厳守事項10(フェーズ24追加): 入力メモに含まれていた氏名・ニックネーム等が、
    出力のどこかの文字列フィールドにそのまま転記されていないかを再帰的に確認する。
    forbidden_termsは、そのテストケースが想定する入力に含まれていた(が出力には
    転記されてはならない)氏名・ニックネーム等の文字列リスト。near_miss_record_templateは
    固定5項目(厳守事項6)で自由記述の本文欄を持たないため、本チェックの対象から除外する
    (llm-system-prompt-draft.md厳守事項10の記載通り)。"""
    errors = []

    def walk(value, p):
        if isinstance(value, str):
            for term in forbidden_terms:
                if term in value:
                    errors.append(
                        f"{p}: 個人を特定できる記述『{term}』がそのまま転記されています(厳守事項10)"
                    )
        elif isinstance(value, dict):
            for k, v in value.items():
                walk(v, f"{p}.{k}")
        elif isinstance(value, list):
            for i, v in enumerate(value):
                walk(v, f"{p}[{i}]")

    for key, value in instance.items():
        if key == "near_miss_record_template":
            continue
        walk(value, f"{path}.{key}")

    return errors


def check_capacity_multiple_values_reference_note(instance, path="$"):
    """mvp-flow-draft.md「capacityの定義方針」(フェーズ42)の机上チェックをコード化したもの。
    入力メモに複数の収容人数が異なる名目で併記されている場合、checklistの冒頭項目で
    (1)比率算出に用いた数値を明示し、(2)他の数値も参考値として併記する旨が読み取れるかを
    機械的に確認する(簡易キーワードチェック、完全な自然言語一致ではない)。"""
    errors = []
    checklist = instance.get("checklist") or []
    if not checklist:
        errors.append(f"{path}.checklist: 複数収容人数併記ケースなのにchecklistが空です")
        return errors
    first_item = checklist[0].get("item") or ""
    if "参考" not in first_item:
        errors.append(
            f"{path}.checklist[0].item: 複数の収容人数が併記された入力なのに、他の数値を"
            "参考値として扱う旨の記載が見当たりません(mvp-flow-draft.md「capacityの定義方針」)"
        )
    return errors


TEST_CASES = {
    "G1_free_admission_indoor": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": None,
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
        "fee_inquiry_note": None,
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
    "G3_mixed_admission_type": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": [
            {"item": "1階自由入場エリアと2階指定席エリアで入退場口を分離できているか", "highlighted": False},
        ],
        "staffing_plan": {
            "focus": "both",
            "body": (
                "自由入場エリアと指定席エリアが混在するため、どちらの入退場時間帯により人が集中するかは"
                "会場導線・開演時間帯によって異なります。最終的な重点配置の判断は主催者・警備責任者自身で"
                "行ってください。雑踏警備にあたる入退場口での流れの調整は外部委託警備員2名の配置案とし、"
                "自社スタッフ3名には掲示・誘導アナウンス等の補助的役割を割り当てます。"
            ),
            "announcement_text": "自由入場エリア・指定席エリアそれぞれの入口が分かれております。係員の案内に従ってお進みください。",
        },
        "notice_board_text": {
            "body": "ご来場の皆様へ。エリアにより入場口が異なります。係員の案内に従い、整列・分散入場にご協力ください。",
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
    "G4_advance_reservation_admission_type": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": [
            {"item": "予約枠ごとの来場時間帯が入退場口2箇所の処理能力に対し集中しないか", "highlighted": False},
        ],
        "staffing_plan": {
            "focus": "both",
            "body": (
                "事前予約制(先着/抽選)のため、予約枠が単一か複数の時間帯に分かれているかによって"
                "入場時・退場時のどちらがより集中するかは入力のみからは一意に決まりません。最終的な"
                "重点配置の判断は主催者・警備責任者自身で行ってください。雑踏警備にあたる入退場口での"
                "流れの調整は外部委託警備員2名の配置案とし、自社スタッフ2名には掲示・誘導アナウンス等の"
                "補助的役割を割り当てます。"
            ),
            "announcement_text": "ご予約の時間枠に応じて順にご案内しております。係員の案内に従ってお進みください。",
        },
        "notice_board_text": {
            "body": "ご来場の皆様へ。ご予約の時間枠に応じて入場をご案内しております。係員の案内に従い、整列・分散入場にご協力ください。",
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
    "OOS1_external_contractor_request": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは一次チェックと文書下書き生成のみを行っております。警備会社への発注契約・所轄警察署への届出代行は主催者・警備責任者自身でご対応ください。",
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": None,
        "staffing_plan": None,
        "notice_board_text": None,
        "near_miss_record_template": None,
    },
    # 厳守事項7(フェーズ24追加): 入力メモが料金プラン・契約・支払いに関する問い合わせのみで
    # 占められている場合、具体的な料金案内は一切行わず一言のみを返す(llm-quality-verification-plan.md
    # フェーズ23「新規追加が必要」とした料金言及混入ケースに対応)。
    "OOS2_fee_and_payment_inquiry": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは一次チェックと文書下書き生成のみを行っております。料金プランについてのご案内は現時点では行っておりません。入退場時混雑確認等のご相談であれば、会場キャパシティ・入退場口数等をお送りください。",
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": None,
        "staffing_plan": None,
        "notice_board_text": None,
        "near_miss_record_template": None,
    },
    # 厳守事項10(フェーズ24追加): 入力メモ(staffingの記述)に委託警備員の氏名が含まれていても、
    # 出力では個人を特定しない一般化した表現(「委託警備員」)に置き換える
    # (llm-quality-verification-plan.mdフェーズ23「新規追加が必要」とした氏名混入ケースに対応)。
    # 想定入力例: 「警備員は外部委託の田中さん1名と自社スタッフ2名です」。
    "G5_staffing_memo_with_personal_name_generalized": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": [
            {"item": "入退場口1箇所がキャパシティ400人に対し十分な処理能力か", "highlighted": True},
        ],
        "staffing_plan": {
            "focus": "entry",
            "body": (
                "自由入場(整理番号なし)のため、開場直後の入場時集中に重点を置きます。雑踏警備にあたる"
                "入退場口での流れの調整は委託警備員1名の配置案とし、自社スタッフ2名には掲示・誘導"
                "アナウンス等の補助的役割を割り当てます。"
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
    # 厳守事項7(フェーズ25追加): 会場情報(capacity・entry_exit_points・admission_type)が
    # 十分に入力されており通常の4出力が生成できる一方、入力メモに料金プラン・契約に関する
    # 問い合わせが混在しているケース。OOS2(料金問い合わせのみ)とは異なり、必須項目が
    # 充足しているためstatus=out_of_scopeではなくgeneratedのまま4出力を生成し、
    # fee_inquiry_noteにのみ料金への不応答を明示する(llm-system-prompt-draft.md
    # 厳守事項7のフェーズ25追記、line-reservation-aiのfaq_segments分離設計を参考にした)。
    # 想定入力例: 「会場キャパ800人、入場口2箇所・退場口1箇所、開場16:30/開演18:00、
    # 自由入場(整理番号なし)、警備員は会場スタッフ4名のみ。ところで利用料金はいくらですか」。
    "G6_generated_with_incidental_fee_mention": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": (
            "本サービスは一次チェックと文書下書き生成のみを行っております。料金プランについての"
            "ご案内は現時点では行っておりません。"
        ),
        "checklist": [
            {"item": "入場口2箇所・退場口1箇所の計3箇所がキャパシティ800人に対し十分な処理能力か", "highlighted": False},
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
    "G7_exit_focus_staggered_block_announcement": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": [
            {"item": "退場口3箇所がキャパシティ1,200人の全席指定会場の終演直後一斉退場に対し十分な処理能力か", "highlighted": False},
        ],
        "staffing_plan": {
            "focus": "exit",
            "body": (
                "全席指定のため、終演直後の一斉退場時の集中に重点を置きます。退場口が3箇所に分かれブロック分け"
                "自体が可能な会場のため、ブロック・エリア別に時間差を設けて段階的に退場を案内する分散退場を"
                "選択肢の一つとして提示します。雑踏警備にあたる退場口での流れの調整は外部委託警備員4名の"
                "配置案とし、自社スタッフ2名には分散退場のアナウンス・誘導等の補助的役割を割り当てます。"
            ),
            "announcement_text": (
                "終演後は係員の案内に従い、お座席のブロックごとに時間差でご退場いただきます。ご自身のブロックの"
                "ご案内があるまで、しばらくお座席でお待ちください。"
            ),
        },
        "notice_board_text": {
            "body": (
                "ご来場の皆様へ。終演後はブロック・エリア別に時間差を設けて段階的にご退場いただきます"
                "(分散退場)。係員の案内に従い、ご自身のブロックの順番までお待ちください。"
            ),
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
    "G8_exit_focus_capped_block_count": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": [
            {"item": "退場口6箇所がキャパシティ3,000人の全席指定会場の終演直後一斉退場に対し十分な処理能力か", "highlighted": False},
        ],
        "staffing_plan": {
            "focus": "exit",
            "body": (
                "全席指定のため、終演直後の一斉退場時の集中に重点を置きます。退場口が6箇所あり"
                "ブロック分け自体は可能な会場ですが、退場口の数のままブロック化すると案内が煩雑に"
                "なるため、隣接する退場口を組にして4ブロックにまとめ、ブロック・エリア別に時間差を"
                "設けて段階的に退場を案内する分散退場を選択肢の一つとして提示します。雑踏警備にあたる"
                "各ブロックの退場口での流れの調整は外部委託警備員6名の配置案とし、自社スタッフ3名には"
                "分散退場のアナウンス・誘導等の補助的役割を割り当てます。"
            ),
            "announcement_text": (
                "終演後は係員の案内に従い、4つのブロックに分かれて時間差でご退場いただきます。ご自身の"
                "ブロックのご案内があるまで、しばらくお座席でお待ちください。"
            ),
        },
        "notice_board_text": {
            "body": (
                "ご来場の皆様へ。終演後は4つのブロックに分かれて時間差を設けて段階的にご退場いただきます"
                "(分散退場)。係員の案内に従い、ご自身のブロックの順番までお待ちください。"
            ),
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
    # mvp-flow-draft.md「capacityの定義方針」(フェーズ42)に対応するテストケース。
    # 想定入力例: 「会場キャパ(消防法上の定員300人、直近の実績動員260人)、入退場共用1箇所、
    # 全席指定、警備員は外部委託2名+自社2名」。複数の数値が異なる名目で併記されているため
    # insufficient_inputとはせず、checklist冒頭項目で比率算出に用いた数値(消防法上の定員300人)
    # を明示し、他の数値(実績動員260人)を参考値として併記する。
    "G9_capacity_multiple_values_reference_note": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "fee_inquiry_note": None,
        "checklist": [
            {
                "item": (
                    "入退場共用1箇所がキャパシティ(消防法上の定員300人を基準に算出、"
                    "直近の実績動員260人は参考値)に対し十分な処理能力か"
                ),
                "highlighted": True,
            },
        ],
        "staffing_plan": {
            "focus": "exit",
            "body": (
                "全席指定のため、終演直後の一斉退場時の集中に重点を置きます。雑踏警備にあたる"
                "入退場口での流れの調整は外部委託警備員2名の配置案とし、自社スタッフ2名には"
                "掲示・誘導アナウンス等の補助的役割を割り当てます。"
            ),
            "announcement_text": "終演後は係員の案内に従い、順にご退場ください。",
        },
        "notice_board_text": {
            "body": "ご来場の皆様へ。入場口が混み合う場合がございます。係員の案内に従い、整列・分散入場にご協力ください。",
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
    "II1_missing_capacity_and_entry_exit": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "会場キャパシティ(capacity)と入退場口数(entry_exit_points)の記載が見当たりません。これらをご入力の上、再度お送りください。",
        "fee_inquiry_note": None,
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

# ネガティブテスト: focus=bothなのに主催者自身への判断委任が本文に無いケースが
# ちゃんと検出されることを確認する(厳守事項4違反の検出能力チェック)。
NEGATIVE_CASE_BOTH_FOCUS_NO_DEFERRAL = {
    **TEST_CASES["G3_mixed_admission_type"],
    "staffing_plan": {
        **TEST_CASES["G3_mixed_admission_type"]["staffing_plan"],
        "body": "自由入場エリアと指定席エリアが混在するため、入場時・退場時の両方に警備員を重点配置します。",
    },
}

# ネガティブテスト(フェーズ13追加): includes_road_use_permit_note=falseなのに本文に
# 「道路使用許可」への言及が冗長に含まれているケースが検出されることを確認する
# (厳守事項2の逆方向、cross_field_rulesのelif分岐の検証漏れを補う)。
NEGATIVE_CASE_ROAD_USE_NOTE_FALSE_BUT_PRESENT = {
    **TEST_CASES["G1_free_admission_indoor"],
    "notice_board_text": {
        "body": "ご来場の皆様へ。待機列が公道に及ぶ場合は道路使用許可の要否をご確認ください。",
        "includes_road_use_permit_note": False,
    },
}

# ネガティブテスト(フェーズ13追加): additionalProperties: falseで定義されていない
# トップレベルの未定義フィールドが混入したケースが検出されることを確認する。
NEGATIVE_CASE_UNDEFINED_TOP_LEVEL_FIELD = {
    **TEST_CASES["G1_free_admission_indoor"],
    "venue_name": "テスト会場",
}

# ネガティブテスト(フェーズ13追加): 必須フィールド(status)が欠落しているケースが
# 検出されることを確認する。
NEGATIVE_CASE_MISSING_REQUIRED_STATUS = {
    k: v for k, v in TEST_CASES["G1_free_admission_indoor"].items() if k != "status"
}

# フェーズ24追加: テストケースごとに、入力メモに含まれていた(が出力に転記されては
# ならない)氏名・ニックネーム等のリスト(厳守事項10、check_personal_name_leakage参照)。
PERSONAL_NAME_LEAKAGE_FORBIDDEN_TERMS = {
    "G5_staffing_memo_with_personal_name_generalized": ["田中"],
}

# フェーズ43追加: 入力メモに複数の収容人数が異なる名目で併記されているテストケースのID。
# check_capacity_multiple_values_reference_note参照(mvp-flow-draft.md「capacityの定義方針」)。
CAPACITY_MULTIPLE_VALUES_CASES = {
    "G9_capacity_multiple_values_reference_note": True,
}

# ネガティブテスト(フェーズ24追加): G5の想定入力に含まれる委託警備員の氏名「田中さん」が
# 一般化されずそのまま出力に転記されてしまったケースが検出されることを確認する
# (厳守事項10違反の検出能力チェック)。
NEGATIVE_CASE_PERSONAL_NAME_LEAKED = {
    **TEST_CASES["G5_staffing_memo_with_personal_name_generalized"],
    "staffing_plan": {
        **TEST_CASES["G5_staffing_memo_with_personal_name_generalized"]["staffing_plan"],
        "body": (
            "自由入場(整理番号なし)のため、開場直後の入場時集中に重点を置きます。雑踏警備にあたる"
            "入退場口での流れの調整は委託警備員の田中さん1名の配置案とし、自社スタッフ2名には掲示・"
            "誘導アナウンス等の補助的役割を割り当てます。"
        ),
    },
}

# ネガティブテスト(フェーズ24追加): OOS2の料金問い合わせ応答が、厳守事項7に反して
# 具体的な料金額(例:「500円/回」)を案内してしまったケースが検出されることを確認する。
NEGATIVE_CASE_FEE_PRICE_LEAKED = {
    **TEST_CASES["OOS2_fee_and_payment_inquiry"],
    "out_of_scope_message": "本サービスは一次チェックと文書下書き生成のみを行っております。単発利用プランは500円/回でご利用いただけます。",
}

# ネガティブテスト(フェーズ25追加): G6(会場情報と料金問い合わせの混在ケース)の
# fee_inquiry_noteが、厳守事項7に反して具体的な料金額(例:「500円/回」)を
# 案内してしまったケースが検出されることを確認する(NEG8のgenerated側バリアント)。
NEGATIVE_CASE_FEE_PRICE_LEAKED_IN_GENERATED = {
    **TEST_CASES["G6_generated_with_incidental_fee_mention"],
    "fee_inquiry_note": "本サービスは一次チェックと文書下書き生成のみを行っております。単発利用プランは500円/回でご利用いただけます。",
}

# ネガティブテスト(フェーズ43追加): G9(複数収容人数併記ケース)のchecklist冒頭項目が、
# 比率算出に用いた数値を明示するのみで他の数値を参考値として併記する旨を欠いている
# ケースが検出されることを確認する(mvp-flow-draft.md「capacityの定義方針」違反の検出能力チェック)。
NEGATIVE_CASE_CAPACITY_MULTIPLE_VALUES_NO_REFERENCE_NOTE = {
    **TEST_CASES["G9_capacity_multiple_values_reference_note"],
    "checklist": [
        {
            "item": "入退場共用1箇所がキャパシティ300人に対し十分な処理能力か",
            "highlighted": True,
        },
    ],
}


def main():
    total = 0
    failed = 0
    for case_id, instance in TEST_CASES.items():
        total += 1
        errors = validate_against_schema(instance, SCHEMA)
        errors += validate_cross_field_rules(instance)
        if case_id in PERSONAL_NAME_LEAKAGE_FORBIDDEN_TERMS:
            errors += check_personal_name_leakage(
                instance, PERSONAL_NAME_LEAKAGE_FORBIDDEN_TERMS[case_id]
            )
        if case_id in CAPACITY_MULTIPLE_VALUES_CASES:
            errors += check_capacity_multiple_values_reference_note(instance)
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

    total += 1
    neg_errors3 = validate_against_schema(NEGATIVE_CASE_BOTH_FOCUS_NO_DEFERRAL, SCHEMA)
    neg_errors3 += validate_cross_field_rules(NEGATIVE_CASE_BOTH_FOCUS_NO_DEFERRAL)
    if neg_errors3:
        print("[OK] NEG3_both_focus_no_deferral_is_detected (想定通りエラー検出)")
        for e in neg_errors3:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG3_both_focus_no_deferral_is_detected: 判断委任記載の欠落を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors4 = validate_against_schema(NEGATIVE_CASE_ROAD_USE_NOTE_FALSE_BUT_PRESENT, SCHEMA)
    neg_errors4 += validate_cross_field_rules(NEGATIVE_CASE_ROAD_USE_NOTE_FALSE_BUT_PRESENT)
    if neg_errors4:
        print("[OK] NEG4_road_use_note_false_but_present_is_detected (想定通りエラー検出)")
        for e in neg_errors4:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG4_road_use_note_false_but_present_is_detected: 冗長な注記の混入を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors5 = validate_against_schema(NEGATIVE_CASE_UNDEFINED_TOP_LEVEL_FIELD, SCHEMA)
    if neg_errors5:
        print("[OK] NEG5_undefined_top_level_field_is_detected (想定通りエラー検出)")
        for e in neg_errors5:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG5_undefined_top_level_field_is_detected: 未定義フィールドの混入を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors6 = validate_against_schema(NEGATIVE_CASE_MISSING_REQUIRED_STATUS, SCHEMA)
    if neg_errors6:
        print("[OK] NEG6_missing_required_status_is_detected (想定通りエラー検出)")
        for e in neg_errors6:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG6_missing_required_status_is_detected: 必須フィールド欠落を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors7 = validate_against_schema(NEGATIVE_CASE_PERSONAL_NAME_LEAKED, SCHEMA)
    neg_errors7 += validate_cross_field_rules(NEGATIVE_CASE_PERSONAL_NAME_LEAKED)
    neg_errors7 += check_personal_name_leakage(NEGATIVE_CASE_PERSONAL_NAME_LEAKED, ["田中"])
    if neg_errors7:
        print("[OK] NEG7_personal_name_leaked_is_detected (想定通りエラー検出)")
        for e in neg_errors7:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG7_personal_name_leaked_is_detected: 氏名の転記を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors8 = validate_against_schema(NEGATIVE_CASE_FEE_PRICE_LEAKED, SCHEMA)
    neg_errors8 += validate_cross_field_rules(NEGATIVE_CASE_FEE_PRICE_LEAKED)
    if neg_errors8:
        print("[OK] NEG8_fee_price_leaked_is_detected (想定通りエラー検出)")
        for e in neg_errors8:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG8_fee_price_leaked_is_detected: 具体的な料金額の案内を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors9 = validate_against_schema(NEGATIVE_CASE_FEE_PRICE_LEAKED_IN_GENERATED, SCHEMA)
    neg_errors9 += validate_cross_field_rules(NEGATIVE_CASE_FEE_PRICE_LEAKED_IN_GENERATED)
    if neg_errors9:
        print("[OK] NEG9_fee_price_leaked_in_generated_is_detected (想定通りエラー検出)")
        for e in neg_errors9:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG9_fee_price_leaked_in_generated_is_detected: fee_inquiry_note内の具体的な料金額の案内を検出できませんでした(バリデータの不備)")

    total += 1
    neg_errors10 = validate_against_schema(NEGATIVE_CASE_CAPACITY_MULTIPLE_VALUES_NO_REFERENCE_NOTE, SCHEMA)
    neg_errors10 += validate_cross_field_rules(NEGATIVE_CASE_CAPACITY_MULTIPLE_VALUES_NO_REFERENCE_NOTE)
    neg_errors10 += check_capacity_multiple_values_reference_note(NEGATIVE_CASE_CAPACITY_MULTIPLE_VALUES_NO_REFERENCE_NOTE)
    if neg_errors10:
        print("[OK] NEG10_capacity_multiple_values_no_reference_note_is_detected (想定通りエラー検出)")
        for e in neg_errors10:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG10_capacity_multiple_values_no_reference_note_is_detected: 参考値併記の欠落を検出できませんでした(バリデータの不備)")

    print(f"\n{total - failed}/{total} 件パス")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
