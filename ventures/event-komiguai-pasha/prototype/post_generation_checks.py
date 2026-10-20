#!/usr/bin/env python3
"""
LLM構造化出力(schema/output.schema.json)を受け取った後に、プログラム側で機械的に
検証する後処理チェック。kura-pasha/course-set-pasha/aircon-pasha/forklift-pashaの
prototype/post_generation_checks.pyと同じ位置づけ(schema/validate_test_cases.pyの
validate_cross_field_rulesが担う「status値に応じたnull/非null依存関係」の検証だけでは
拾えない、本文テキストの内容自体が厳守事項を守っているかのヒューリスティック検証)。
README.md(フェーズ27)が次回候補として挙げていた絵文字不使用(厳守事項9)・対象外トピック
混入(厳守事項7)の機械チェックを、本ファイル(フェーズ28)で実装する。

本venture固有の差分として、kura-pasha/course-set-pashaのような継続課金・解約フロー関連の
追加フィールドは存在せず(llm-system-prompt-draft.md記載の通り会員管理・サブスクリプション
課金フローは未設計)、検証対象はchecklist/staffing_plan/notice_board_text/
near_miss_record_template/out_of_scope_message/missing_fields_request/fee_inquiry_noteの
7フィールドである点が異なる。

- ここでの検証はあくまでヒューリスティック(キーワード一致・正規表現によるパターン判定)
  であり、LLMの厳守事項違反を確実に検出できるわけではない。実LLM接続後は、ここで拾いきれない
  違反パターンの収集・ルール改善が引き続き必要になる(他venture共通の限界)。
- 実LLM呼び出しは行わない(APIキー取得・アカウント作成はオーナー承認待ち、
  pending-approval.md参照)。
"""

import re

# 厳守事項9(文体は「ですます調」を既定とし、絵文字は使用しない)の機械チェック用。
# forklift-pasha/kura-pashaのEMOJI_PATTERNと同じ文字コード範囲を踏襲する
# (顔文字・記号・ピクトグラム等が集中する主要ブロックを対象としたヒューリスティック)。
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # 各種絵文字・記号(顔・乗り物・アクティビティ等)
    "☀-➿"  # その他の記号・装飾記号(☀☕✨➿等)
    "⬀-⯿"  # 矢印・星等の追加記号(⭐⬛等)
    "\U0001F100-\U0001F1E5"  # 囲み英数字補助のうち地域指示記号と重複しない範囲(🅰🅱🅾🆚等)
    "\U0001F1E6-\U0001F1FF"  # 地域指示記号(組み合わせで国旗絵文字になる)
    "\U0001F200-\U0001F2FF"  # 囲みCJK文字・月間補助記号(🈚🈵🈲等)
    "️"  # 異体字セレクタ(絵文字表示指定)
    "‍"  # ゼロ幅接合子(複合絵文字)
    "]"
)

# 厳守事項7(入力メモに料金プラン・契約・支払いに関する記述が含まれていても、それらには
# 一切応答しない)の機械チェック用。status=generatedの4出力本文に、これらの話題への言及が
# 紛れ込んでいないかをヒューリスティックに判定する(forklift-pashaの
# OUT_OF_SCOPE_TOPIC_KEYWORDSと同じ位置づけ)。fee_inquiry_note自体はこの検証対象から
# 除外する(厳守事項7の定型文としてこれらの語を含むことが前提のフィールドのため)。
OUT_OF_SCOPE_TOPIC_KEYWORDS = (
    "料金プラン", "契約書", "ご契約", "お支払い", "振込先", "請求書", "月額", "年会費",
)


def _collect_main_output_texts(instance):
    """厳守事項9(絵文字は終始不使用)の対象となる、4出力+定型応答系の全テキストを
    [(フィールド名, テキスト), ...]の形で集める。"""
    texts = []

    for i, item in enumerate(instance.get("checklist") or []):
        value = item.get("item")
        if value:
            texts.append((f"checklist[{i}].item", value))

    staffing_plan = instance.get("staffing_plan")
    if staffing_plan:
        for field in ("body", "announcement_text"):
            value = staffing_plan.get(field)
            if value:
                texts.append((f"staffing_plan.{field}", value))

    notice_board_text = instance.get("notice_board_text")
    if notice_board_text:
        value = notice_board_text.get("body")
        if value:
            texts.append(("notice_board_text.body", value))

    near_miss_record_template = instance.get("near_miss_record_template")
    if near_miss_record_template:
        for i, field in enumerate(near_miss_record_template.get("fields") or []):
            for key in ("field_name", "description"):
                value = field.get(key)
                if value:
                    texts.append((f"near_miss_record_template.fields[{i}].{key}", value))

    for field_name in ("out_of_scope_message", "missing_fields_request", "fee_inquiry_note"):
        value = instance.get(field_name)
        if value:
            texts.append((field_name, value))

    return texts


def check_no_emoji_anywhere(instance):
    """厳守事項9準拠チェック。警備・安全管理という性質上、事務的な文体を優先するため
    statusによらず全出力本文で絵文字ゼロを求める(course-set-pashaのSNS投稿文向けルール
    〈1〜2個まで許容〉とは異なり、forklift-pashaと同じ「全体で絵文字不使用」方針)。
    """
    errors = []
    for field_name, text in _collect_main_output_texts(instance):
        if EMOJI_PATTERN.search(text):
            errors.append(
                f"{field_name}: 絵文字が含まれています"
                "(厳守事項9違反の疑い、本venture全体で絵文字不使用)"
            )
    return errors


def check_no_out_of_scope_topics_in_generated_output(instance):
    """厳守事項7準拠チェック。status=generatedのとき、checklist・staffing_plan・
    notice_board_text・near_miss_record_templateに料金プラン・契約・支払いに関する
    話題への言及が紛れ込んでいないかを確認する(forklift-pashaの同名関数と同じ設計思想)。
    fee_inquiry_note自体はこの検証対象から除外する(厳守事項7の定型応答として
    これらの語を含むことが前提のフィールドのため、ここで検出すると定型応答の文面自体を
    誤検出してしまう)。
    """
    errors = []
    if instance.get("status") != "generated":
        return errors

    texts = [
        (field_name, text)
        for field_name, text in _collect_main_output_texts(instance)
        if field_name not in ("fee_inquiry_note", "out_of_scope_message", "missing_fields_request")
    ]

    for field_name, text in texts:
        for kw in OUT_OF_SCOPE_TOPIC_KEYWORDS:
            if kw in text:
                errors.append(
                    f"{field_name}: 料金プラン・契約・支払いに関する話題と疑われる"
                    f"語「{kw}」が含まれています(厳守事項7違反の疑い)"
                )
    return errors


def run_all_checks(instance):
    """後処理チェックをまとめて実行し、エラーメッセージのリストを返す。"""
    errors = []
    errors += check_no_emoji_anywhere(instance)
    errors += check_no_out_of_scope_topics_in_generated_output(instance)
    return errors
