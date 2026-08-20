#!/usr/bin/env python3
"""
LLM構造化出力(schema/output.schema.json)を受け取った後に、プログラム側で機械的に
検証する後処理チェック。course-set-pasha/prototype/post_generation_checks.py・
line-reservation-ai/prototype/engine.pyと同じ位置づけ(これまで方針の記述のみだった
llm-system-prompt-draft.md・schema/output.schema.jsonの検証用フィールドを、初めて
実行可能なコードに落とし込んだもの)。

位置づけ:
- completion_report.mentions_refrigerant_or_electrical(厳守事項1)、
  care_guide.next_recommended_date_is_estimate(厳守事項4)について、本文中の
  記述との突き合わせをヒューリスティックに検証する。
- status=generatedのときに会員管理・予約受付・決済の話題(厳守事項6)が本文に
  紛れ込んでいないかを検証する。
- history_row(構造化データ)側の機種系統・号数・追加施工の記載が、本文
  (completion_report.body)側にも反映されているか(厳守事項3)を検証する。
- ここでの検証はあくまでヒューリスティック(キーワード近傍探索)であり、LLMの
  厳守事項違反を確実に検出できるわけではない。実LLM接続後は、ここで拾いきれない
  違反パターンの収集・ルール改善が引き続き必要になる。
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
"""

import re

# 厳守事項1の機械チェック用。冷媒・電気系統というキーワードそのものではなく、
# その技術的当否・安全性を評価する語(専門的助言)が近傍にあるかを検出する。
REFRIGERANT_ELECTRICAL_TOPIC_KEYWORDS = ("冷媒", "電気系統", "感電")
PROFESSIONAL_JUDGEMENT_KEYWORDS = (
    "危険です", "危険な状態", "安全です", "問題ありません", "異常なし", "正常です",
    "交換が必要", "漏れています", "漏れがあります", "故障の恐れ", "修理が必要",
)

# 厳守事項4の機械チェック用。次回推奨時期が一般的目安であることを明示する定型的な
# 打消し文言(llm-system-prompt-draft.md・output-samples-validation.mdの
# G2/G3サンプルで採用された表現)。
ESTIMATE_DISCLAIMER_KEYWORDS = ("記載が無いため", "記載がないため", "記載が無い場合")

# 厳守事項6の機械チェック用。course-set-pashaのOUT_OF_SCOPE_TOPIC_KEYWORDSと同じ
# 位置づけ。本venture(作業完了報告・お手入れ案内文の下書き作成支援)の性質上、
# 生成本文にこれらの語が登場すること自体が想定外(厳守事項6逸脱の疑い)である。
OUT_OF_SCOPE_TOPIC_KEYWORDS = ("会員", "入会", "退会", "予約受付", "決済", "振込", "クレジットカード")

# 厳守事項3の機械チェック用。additional_treatmentの値から「あり」等の付随語を除いた
# キーワードが本文に登場するかを確認する際に取り除く接尾辞。
ADDITIONAL_TREATMENT_SUFFIXES = ("あり", "実施", "施工あり", "済み")

NO_ADDITIONAL_TREATMENT_VALUES = ("なし", "無し", "特になし")


def check_refrigerant_electrical_professional_judgement(instance):
    """厳守事項1準拠チェック。completion_report.bodyに、冷媒・電気系統に関する
    技術的当否・安全性の評価(専門的助言)を示す語が含まれていないかを確認する。
    実施した旨を淡々と記述するだけの表現(例:「冷媒を補充いたしました」)は対象外とし、
    評価語(「異常なし」「危険です」等)が冷媒・電気系統の話題と共起する場合のみ検出する。
    completion_report.mentions_refrigerant_or_electricalの値にかかわらず、
    評価語が見つかればLLM側の逸脱の疑いとして報告する(フィールド値が正しくFalseで
    あっても、本文側に専門的助言が紛れ込んでいれば厳守事項1違反のため)。
    """
    errors = []
    completion_report = instance.get("completion_report")
    if completion_report is None:
        return errors

    body = completion_report.get("body", "")
    has_topic = any(kw in body for kw in REFRIGERANT_ELECTRICAL_TOPIC_KEYWORDS)
    has_judgement = any(kw in body for kw in PROFESSIONAL_JUDGEMENT_KEYWORDS)

    if has_topic and has_judgement:
        errors.append(
            "completion_report: 冷媒・電気系統に関する専門的な評価語が含まれています"
            "(厳守事項1違反の疑い)"
        )

    mentions_flag = completion_report.get("mentions_refrigerant_or_electrical")
    if mentions_flag is True and not has_topic:
        errors.append(
            "completion_report: mentions_refrigerant_or_electrical=trueだが"
            "本文に冷媒・電気系統への言及が見つかりません(フィールド値と本文の不一致の疑い)"
        )

    return errors


def check_next_recommended_date_estimate_consistency(instance):
    """厳守事項4準拠チェック。care_guide.next_recommended_date_is_estimateがtrueの
    場合は、本文に「入力メモに記載が無いための一般的な目安」である旨の打消し文言が
    含まれているかを確認する。falseの場合は、逆にこの打消し文言が含まれていないかを
    確認する(入力メモ由来の値であるにもかかわらず一般論扱いする文言が混入していれば
    矛盾の疑い)。
    """
    errors = []
    care_guide = instance.get("care_guide")
    if care_guide is None:
        return errors

    body = care_guide.get("body", "")
    is_estimate = care_guide.get("next_recommended_date_is_estimate")
    has_disclaimer = any(kw in body for kw in ESTIMATE_DISCLAIMER_KEYWORDS)

    if is_estimate is True and not has_disclaimer:
        errors.append(
            "care_guide: next_recommended_date_is_estimate=trueだが、本文に"
            "「メモに記載が無いための一般的な目安」である旨の打消し文言が"
            "見つかりません(厳守事項4違反の疑い)"
        )
    if is_estimate is False and has_disclaimer:
        errors.append(
            "care_guide: next_recommended_date_is_estimate=falseだが、本文に"
            "一般的な目安扱いを示す打消し文言が含まれています"
            "(フィールド値と本文の不一致の疑い)"
        )

    return errors


def check_no_out_of_scope_topics_in_generated_output(instance):
    """厳守事項6準拠チェック。status=generatedのとき、completion_report.body・
    care_guide.bodyに会員管理・予約受付・決済に関する話題への言及が紛れ込んでいないかを
    確認する(course-set-pashaの同名チェックと同じ位置づけ)。
    """
    errors = []
    if instance.get("status") != "generated":
        return errors

    texts = []
    completion_report = instance.get("completion_report")
    if completion_report:
        texts.append(("completion_report.body", completion_report.get("body", "")))
    care_guide = instance.get("care_guide")
    if care_guide:
        texts.append(("care_guide.body", care_guide.get("body", "")))

    for field_name, text in texts:
        for kw in OUT_OF_SCOPE_TOPIC_KEYWORDS:
            if kw in text:
                errors.append(
                    f"{field_name}: 会員管理・予約・決済に関する話題と疑われる語「{kw}」が"
                    "含まれています(厳守事項6違反の疑い)"
                )
    return errors


def _strip_additional_treatment_suffix(value):
    for suffix in ADDITIONAL_TREATMENT_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value


def check_model_type_mentioned_in_text(instance):
    """厳守事項3準拠チェック(機種系統・号数の明示)。history_row.model_type_and_capacity
    が入力メモから抽出できている場合(非null)、completion_report.bodyにも同じ記述が
    登場しているかを確認する。抽出できていない(null)場合はチェック対象外。
    """
    errors = []
    history_row = instance.get("history_row")
    completion_report = instance.get("completion_report")
    if history_row is None or completion_report is None:
        return errors

    model_type = history_row.get("model_type_and_capacity")
    if not model_type:
        return errors

    body = completion_report.get("body", "")
    if model_type not in body:
        errors.append(
            f"history_row: 機種系統・号数「{model_type}」がcompletion_report.bodyに"
            "見つかりません(厳守事項3違反の疑い)"
        )
    return errors


def check_additional_treatment_mentioned_in_text(instance):
    """厳守事項3準拠チェック(追加施工の明示)。history_row.additional_treatmentが
    「なし」系の値でない場合、completion_report.bodyにその施工内容への言及があるかを
    確認する。"""
    errors = []
    history_row = instance.get("history_row")
    completion_report = instance.get("completion_report")
    if history_row is None or completion_report is None:
        return errors

    additional_treatment = history_row.get("additional_treatment")
    if not additional_treatment or additional_treatment in NO_ADDITIONAL_TREATMENT_VALUES:
        return errors

    body = completion_report.get("body", "")
    keyword = _strip_additional_treatment_suffix(additional_treatment)
    if keyword not in body:
        errors.append(
            f"history_row: 追加施工「{additional_treatment}」がcompletion_report.bodyに"
            "見つかりません(厳守事項3違反の疑い)"
        )
    return errors


def check_next_recommended_date_history_care_guide_consistency(instance):
    """厳守事項4関連の追加チェック(構造化データと打消し文言の整合)。
    care_guide.next_recommended_date_is_estimate=false(=入力メモ由来の具体的な
    次回目安)を主張しているにもかかわらず、history_row.next_recommended_dateが
    null/空であれば、「メモ由来の日付」と自称しながら構造化フィールドが空という
    不整合の疑いとして報告する。逆にis_estimate=trueの場合は一般的な目安であり、
    history_row側が空でも矛盾ではないためチェック対象外。
    check_next_recommended_date_estimate_consistencyが本文(打消し文言)側との
    整合を見るのに対し、こちらは構造化データ(history_row)側との整合を見る。
    """
    errors = []
    care_guide = instance.get("care_guide")
    history_row = instance.get("history_row")
    if care_guide is None or history_row is None:
        return errors

    is_estimate = care_guide.get("next_recommended_date_is_estimate")
    hist_date = history_row.get("next_recommended_date")
    if is_estimate is False and not hist_date:
        errors.append(
            "care_guide/history_row: next_recommended_date_is_estimate=false"
            "(メモ由来の具体的な次回目安)にもかかわらずhistory_row."
            "next_recommended_dateが空です(構造化データとの不整合の疑い)"
        )
    return errors


def run_all_checks(instance):
    """後処理チェックをまとめて実行し、エラーメッセージのリストを返す。"""
    errors = []
    errors += check_refrigerant_electrical_professional_judgement(instance)
    errors += check_next_recommended_date_estimate_consistency(instance)
    errors += check_no_out_of_scope_topics_in_generated_output(instance)
    errors += check_model_type_mentioned_in_text(instance)
    errors += check_additional_treatment_mentioned_in_text(instance)
    errors += check_next_recommended_date_history_care_guide_consistency(instance)
    return errors
