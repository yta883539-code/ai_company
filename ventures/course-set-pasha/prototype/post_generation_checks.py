#!/usr/bin/env python3
"""
LLM構造化出力(schema/output.schema.json)を受け取った後に、プログラム側で機械的に
検証する後処理チェック。

位置づけ:
- schema/output.schema.jsonのフィールド説明で「本文中の言及との突き合わせ検証」を
  意図として記載していた`sns_post.mentions_photo`(厳守事項3)・`unchanged_areas`
  (厳守事項2)の2点について、これまで方針の記述のみだったものを初めて実行可能な
  コードに落とし込んだ(line-reservation-aiのvalidate_test_cases.py・prototype/engine.pyと
  同じ位置づけ)。
- ここでの検証はあくまでヒューリスティック(キーワード近傍探索)であり、LLMの厳守事項
  違反を確実に検出できるわけではない。実LLM接続後は、ここで拾いきれない違反パターンの
  収集・ルール改善が引き続き必要になる。
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
"""

import re

PHOTO_REFERENCE_KEYWORDS = ("写真の課題", "写真")
NEW_CONTENT_KEYWORDS = ("新着", "追加", "入れ替え", "新規")
UNCHANGED_KEYWORDS = ("変更なし", "変更ありません", "変わりません", "変更はありません")

# 「変更なし」エリア名の前後何文字を「近傍」とみなすか。
_PROXIMITY_WINDOW = 15


def check_mentions_photo_consistency(instance):
    """厳守事項3準拠チェック。sns_post.mentions_photoの値と、本文中に実際に写真への
    言及があるかどうかが一致しているかを確認する。

    - mentions_photo=trueなのに本文に写真言及が無い: 「写真の課題」に言及する形で
      文面を組み立てる、という指示が守られていない疑い。
    - mentions_photo=falseなのに本文に写真言及がある: 写真が無いのに言及してしまっている疑い。
    """
    errors = []
    sns_post = instance.get("sns_post")
    if sns_post is None:
        return errors

    body = sns_post.get("body", "")
    mentions_photo = sns_post.get("mentions_photo")
    body_mentions_photo = any(kw in body for kw in PHOTO_REFERENCE_KEYWORDS)

    if mentions_photo is True and not body_mentions_photo:
        errors.append(
            "sns_post: mentions_photo=trueだが本文に写真への言及が見つかりません(厳守事項3違反の疑い)"
        )
    if mentions_photo is False and body_mentions_photo:
        errors.append(
            "sns_post: mentions_photo=falseだが本文に写真への言及が含まれています(厳守事項3違反の疑い)"
        )
    return errors


def _find_suspicious_area_mentions(text, area, window=_PROXIMITY_WINDOW):
    """area名の出現箇所ごとに、前後window文字以内にNEW_CONTENT_KEYWORDSが含まれ、
    かつ同じ範囲内にUNCHANGED_KEYWORDSが含まれない箇所(=新着扱いされている疑いのある
    箇所)を返す。「エリアC・エリアDは変更ありません」のように変更なし文脈で言及される
    のは許容する。"""
    hits = []
    for m in re.finditer(re.escape(area), text):
        start = max(0, m.start() - window)
        end = min(len(text), m.end() + window)
        surrounding = text[start:end]
        has_new = any(kw in surrounding for kw in NEW_CONTENT_KEYWORDS)
        has_unchanged = any(kw in surrounding for kw in UNCHANGED_KEYWORDS)
        if has_new and not has_unchanged:
            hits.append(surrounding)
    return hits


def check_unchanged_areas_not_mentioned_as_new(instance):
    """厳守事項2準拠チェック。unchanged_areasに含まれるエリア名が、sns_post.body /
    line_web_notice.body内で新着課題があるかのような文脈(「新着」「追加」等の近傍)に
    登場していないかを確認する。"""
    errors = []
    unchanged_areas = instance.get("unchanged_areas") or []
    if not unchanged_areas:
        return errors

    texts = []
    sns_post = instance.get("sns_post")
    if sns_post:
        texts.append(("sns_post.body", sns_post.get("body", "")))
    line_web_notice = instance.get("line_web_notice")
    if line_web_notice:
        texts.append(("line_web_notice.body", line_web_notice.get("body", "")))

    for field_name, text in texts:
        for area in unchanged_areas:
            for hit in _find_suspicious_area_mentions(text, area):
                errors.append(
                    f"{field_name}: 変更なしエリア「{area}」が新着を示唆する文脈で"
                    f"言及されている疑いがあります: ...{hit}..."
                )
    return errors


def run_all_checks(instance):
    """後処理チェックをまとめて実行し、エラーメッセージのリストを返す。"""
    errors = []
    errors += check_mentions_photo_consistency(instance)
    errors += check_unchanged_areas_not_mentioned_as_new(instance)
    return errors
