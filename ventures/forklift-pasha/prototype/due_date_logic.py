#!/usr/bin/env python3
"""
mvp-flow-draft.md「出力」2.・llm-system-prompt-draft.md 24〜25行目で定義された、
次回実施期限の算出とリマインド要否判定を実装する(フェーズ26)。

これまでschema/validate_test_cases.pyのG2/G3フィクスチャでは、次回実施期限
(前回実施日+1ヶ月/+1年)とreminder_noticeの有無を人手で計算した固定値として
用意していたが、実際の期限計算ロジック自体は未実装だった
(output-samples-validation.md「次回候補」: annual区分の次回実施期限の年次計算の
境界値ケース追加、market-research.md/mvp-flow-draft.mdの次回候補とも整合)。

対象:
- monthly(前回実施日+1ヶ月、安衛則第151条の22)
- annual(前回実施日+1年、安衛則第151条の24)
- daily(安衛則第151条の25)は次回期限の概念が無いため、常にリマインド対象外。

実LLM呼び出しは行わない。本モジュールはLLM生成後の機械的な期限算出・検証に使う
想定(post_generation_checks.py・validate_test_cases.pyと同じ「机上実装のみ、
実LLM接続はAPIキー取得がオーナー承認待ち」という位置づけ)。
"""

from datetime import date, timedelta

REMINDER_THRESHOLD_DAYS = 7  # llm-system-prompt-draft.md 25行目「期限が近い(7日前以内)」


def _add_months(d: date, months: int) -> date:
    """dのmonths ヶ月後の日付を返す。月末日の繰り上げで存在しない日付
    (例: 1/31 + 1ヶ月 -> 2/31は存在しない)になる場合は、その月の末日に丸める。"""
    total_month_index = d.month - 1 + months
    year = d.year + total_month_index // 12
    month = total_month_index % 12 + 1
    day = min(d.day, _days_in_month(year, month))
    return date(year, month, day)


def _add_years(d: date, years: int) -> date:
    """dのyears年後の日付を返す。うるう年2/29の加算先が非うるう年の場合は2/28に丸める。"""
    year = d.year + years
    day = min(d.day, _days_in_month(year, d.month))
    return date(year, d.month, day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    return (next_month_first - date(year, month, 1)).days


def compute_next_due_date(inspection_type: str, last_date: date):
    """mvp-flow-draft.md「出力」2.の期限算出ルール。dailyはNoneを返す
    (次回期限の概念が無いためreminder_noticeは常にnull、
    validate_cross_field_rules()の既存ルールと整合)。"""
    if inspection_type == "monthly":
        return _add_months(last_date, 1)
    if inspection_type == "annual":
        return _add_years(last_date, 1)
    if inspection_type == "daily":
        return None
    raise ValueError(f"未知のinspection_type: {inspection_type!r}")


def should_remind(inspection_type: str, last_date: date, today: date,
                   threshold_days: int = REMINDER_THRESHOLD_DAYS) -> bool:
    """next_due_dateがtodayからthreshold_days以内(境界値を含む)に迫っている、
    または既に期限超過している場合にTrueを返す。期限超過時も「近い」の延長として
    リマインド対象とする(安衛則上の記録保存・実施義務の観点で、超過後も通知を
    止める理由が無いため)。"""
    due = compute_next_due_date(inspection_type, last_date)
    if due is None:
        return False
    days_remaining = (due - today).days
    return days_remaining <= threshold_days
