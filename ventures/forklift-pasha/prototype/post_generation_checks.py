#!/usr/bin/env python3
"""
LLM構造化出力(schema/output.schema.json)を受け取った後に、プログラム側で機械的に
検証する後処理チェック。kura-pasha/course-set-pasha/aircon-pashaのprototype/
post_generation_checks.pyと同じ位置づけ(schema/validate_test_cases.pyの
validate_cross_field_rulesが担う「status・type値に応じたnull/非null依存関係」の
検証だけでは拾えない、本文テキストの内容自体が厳守事項を守っているかのヒューリスティック
検証)。llm-quality-verification-plan.md(フェーズ7)が「本venture未実装」として次の課題に
挙げていた絵文字不使用チェックを、本ファイル(フェーズ8)で実装する。

本venture固有の差分として、kura-pasha/course-set-pashaのように継続課金・解約フロー・
招待コード等の追加フィールドは存在せず、検証対象はinspection_record.body・
reminder_noticeの2箇所のみである点が異なる。

- ここでの検証はあくまでヒューリスティック(キーワード一致・正規表現によるパターン判定)
  であり、LLMの厳守事項違反を確実に検出できるわけではない。実LLM接続後は、ここで拾いきれない
  違反パターンの収集・ルール改善が引き続き必要になる(他venture共通の限界)。
- 実LLM呼び出しは行わない(APIキー取得はオーナー承認待ち、pending-approval.md参照)。
"""

import re

# 厳守事項7(文体は「ですます調」を既定とし、絵文字は使用しない)の機械チェック用。
# kura-pasha/post_generation_checks.pyのEMOJI_PATTERNと同じ文字コード範囲を踏襲する
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

# 厳守事項6(点検記録整形・期限管理以外の要求には一切応答しない)の機械チェック用。
# status=generatedの出力本文に、修理の実施・部品調達・費用見積り等、対象外の話題への
# 言及が紛れ込んでいないかをヒューリスティックに判定する。
OUT_OF_SCOPE_TOPIC_KEYWORDS = (
    "修理", "部品", "見積り", "見積もり", "費用は", "代金", "発注", "手配いたします",
)


def _collect_all_body_texts(instance):
    """厳守事項7(絵文字は終始不使用)の対象となる、全出力本文テキストを
    [(フィールド名, テキスト), ...]の形で集める。本venture固有のフィールド構成
    (inspection_record.body・reminder_notice)に合わせたもの。"""
    texts = []

    record = instance.get("inspection_record")
    if record:
        body = record.get("body")
        if body:
            texts.append(("inspection_record.body", body))
        reminder_notice = record.get("reminder_notice")
        if reminder_notice:
            texts.append(("inspection_record.reminder_notice", reminder_notice))

    out_of_scope_message = instance.get("out_of_scope_message")
    if out_of_scope_message:
        texts.append(("out_of_scope_message", out_of_scope_message))

    missing_fields_request = instance.get("missing_fields_request")
    if missing_fields_request:
        texts.append(("missing_fields_request", missing_fields_request))

    return texts


def check_no_emoji_anywhere(instance):
    """厳守事項7準拠チェック。現場の実務記録であるため、statusによらず全出力本文で
    絵文字ゼロを求める(course-set-pashaのSNS投稿文向けルール〈1〜2個まで許容〉とは異なる)。
    """
    errors = []
    for field_name, text in _collect_all_body_texts(instance):
        if EMOJI_PATTERN.search(text):
            errors.append(
                f"{field_name}: 絵文字が含まれています(厳守事項7違反の疑い、本venture全体で絵文字不使用)"
            )
    return errors


def check_no_out_of_scope_topics_in_generated_output(instance):
    """厳守事項6準拠チェック。status=generatedのとき、inspection_record.body・
    reminder_noticeに修理の実施・部品調達・費用見積り等、点検記録整形・期限管理以外の
    話題への言及が紛れ込んでいないかを確認する(kura-pashaの同名関数と同じ設計思想)。
    """
    errors = []
    if instance.get("status") != "generated":
        return errors

    record = instance.get("inspection_record") or {}
    texts = []
    body = record.get("body")
    if body:
        texts.append(("inspection_record.body", body))
    reminder_notice = record.get("reminder_notice")
    if reminder_notice:
        texts.append(("inspection_record.reminder_notice", reminder_notice))

    for field_name, text in texts:
        for kw in OUT_OF_SCOPE_TOPIC_KEYWORDS:
            if kw in text:
                errors.append(
                    f"{field_name}: 修理・部品調達・費用見積り等の対象外の話題と疑われる"
                    f"語「{kw}」が含まれています(厳守事項6違反の疑い)"
                )
    return errors


def run_all_checks(instance):
    """後処理チェックをまとめて実行し、エラーメッセージのリストを返す。"""
    errors = []
    errors += check_no_emoji_anywhere(instance)
    errors += check_no_out_of_scope_topics_in_generated_output(instance)
    return errors
