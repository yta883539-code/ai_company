#!/usr/bin/env python3
"""
schema/output.schema.jsonのhistory_rows(出力3)を、mvp-flow-draft.mdが前提とする
「スプレッドシート等へ手動転記」の運用に沿ったCSVテキストへ変換するモジュール。

位置づけ:
- line-reservation-aiのprototype/engine.pyと同様、実LLM呼び出しは行わず(APIキー・課金が
  必要なためオーナー承認待ち)、構造化出力(history_rows)を受け取った後の決定的な変換処理
  のみを実装する。
- history_rowsのrevision_date/countはnullを許容する設計(schema/output.schema.json参照)の
  ため、null時の表示文言をここで統一し、手動転記時にどの項目が未確認かを一目で分かるようにする。
"""

import csv
import io

HISTORY_CSV_HEADER = ["改訂日", "エリア", "テープ色・グレード帯", "本数", "特徴キーワード"]

_NULL_DATE_PLACEHOLDER = "未記入"
_NULL_COUNT_PLACEHOLDER = "不明"


def history_row_to_csv_fields(row):
    """history_rows内の1要素をCSV出力用の文字列フィールド5つに変換する。"""
    revision_date = row.get("revision_date")
    count = row.get("count")
    feature_keywords = row.get("feature_keywords") or []
    return [
        revision_date if revision_date is not None else _NULL_DATE_PLACEHOLDER,
        row.get("area", ""),
        row.get("tape_color_or_grade_band", ""),
        str(count) if count is not None else _NULL_COUNT_PLACEHOLDER,
        "、".join(feature_keywords),
    ]


def history_rows_to_csv_text(history_rows):
    """history_rows(配列)をヘッダー付きCSVテキストに変換する。history_rowsがNone/空の
    場合は空文字を返す(status!=generatedのケース、または呼び出し側の取り違えを想定した
    安全側の扱い)。"""
    if not history_rows:
        return ""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HISTORY_CSV_HEADER)
    for row in history_rows:
        writer.writerow(history_row_to_csv_fields(row))
    return buf.getvalue()
