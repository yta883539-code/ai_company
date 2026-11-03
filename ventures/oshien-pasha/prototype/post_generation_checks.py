#!/usr/bin/env python3
"""LLM構造化出力(schema/output.schema.json)を受け取った後に、プログラム側で機械的に
検証する後処理チェック(course-set-pasha・aircon-pasha・kura-pasha・forklift-pasha・
event-komiguai-pashaのpost_generation_checks.py相当)。

位置づけ:
- tone-and-manner-guideline.md基本方針1「全出力フィールドでですます調・絵文字不使用を
  既定とする」(llm-system-prompt-draft.md厳守事項8。他venture(course-set-pasha厳守事項9等)
  がSNS投稿文のみに許容する絵文字1〜2個の例外は本ventureには適用しない)の機械チェックを
  初めて実行可能なコードに落とし込んだ。tone-and-manner-guideline.md「発見した不整合・
  ギャップ」節では、本チェックの適用対象(自由文メッセージ)がprototype側のPython定数として
  まだ存在しないことを理由に新設を見送っていたが、validate_test_cases.pyのTEST_CASES
  (机上で書き起こした期待JSON出力サンプル)自体がLLM構造化出力のインスタンスと同じ形を
  持つため、Python定数の有無に関わらずインスタンス単位のチェックとして適用できる
  (実LLM接続後は実際の生成結果instanceに対してそのまま適用する想定)。
- 他venture(course-set-pasha等)はsns_post.body等、個別フィールドを指名してチェックするが、
  本ventureは絵文字が許容されるフィールドが一切存在しない(例外なし)ため、instance全体を
  再帰的に走査して文字列値をすべて対象とする汎用実装とした(個別フィールド指名方式より
  フィールド追加時の追従漏れが起きない)。
- ここでの検証はあくまでヒューリスティック(絵文字の文字コード範囲判定)であり、LLMの
  厳守事項違反を確実に検出できるわけではない。実LLM接続後は、ここで拾いきれない
  違反パターンの収集・ルール改善が引き続き必要になる。
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
"""

import re

# course-set-pasha等のpost_generation_checks.pyと同じ判定範囲(主要な絵文字ブロック)。
# 本venture固有の絵文字許容例外は無いため、SNS_POST_MAX_EMOJIのような上限値は持たず
# 1個でも検出すれば違反とする。
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # 各種絵文字・記号(顔・乗り物・アクティビティ等)
    "☀-➿"  # その他の記号・装飾記号(☀☕✨➿等)
    "⬀-⯿"  # 矢印・星等の追加記号(⭐⬛等)
    "\U0001F100-\U0001F1E5"  # 囲み英数字補助のうち地域指示記号と重複しない範囲(🅰🅱🅾🆚等)
    "\U0001F1E6-\U0001F1FF"  # 地域指示記号(組み合わせで国旗絵文字になる)
    "\U0001F200-\U0001F2FF"  # 囲みCJK文字・月間補助記号(🈚🈵🈲等、SNS投稿で使われうる)
    "️"  # 異体字セレクタ(絵文字表示指定)
    "‍"  # ゼロ幅接合子(複合絵文字)
    "]"
)


def _iter_string_leaves(value, path="$"):
    """instance(dict/list/文字列等の入れ子構造)を再帰的に走査し、(path, 文字列値)の
    タプルを列挙する。venue_name_input等の入力エコー項目も含め、出力中の全文字列値を
    対象とする(tone-and-manner-guideline.md基本方針1「全出力フィールド」に対応)。"""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, sub_value in value.items():
            yield from _iter_string_leaves(sub_value, path=f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _iter_string_leaves(item, path=f"{path}[{i}]")


def check_no_emoji_anywhere(instance):
    """tone-and-manner-guideline.md基本方針1・llm-system-prompt-draft.md厳守事項8準拠
    チェック。instance内の全文字列フィールドに絵文字が1個でも含まれていないかを確認する
    (本ventureには絵文字許容の例外フィールドが存在しないため、個別フィールドの除外は
    設けない)。"""
    errors = []
    for path, text in _iter_string_leaves(instance):
        matches = EMOJI_PATTERN.findall(text)
        if matches:
            errors.append(
                f"{path}: 絵文字が{len(matches)}個含まれています"
                f"(tone-and-manner-guideline.md基本方針1違反の疑い、本ventureは絵文字不使用"
                f"に例外なし): {text!r}"
            )
    return errors


def run_all_checks(instance):
    """後処理チェックをまとめて実行し、エラーメッセージのリストを返す。"""
    errors = []
    errors += check_no_emoji_anywhere(instance)
    return errors
