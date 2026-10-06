#!/usr/bin/env python3
"""due_date_logic.pyの境界値テスト(フェーズ26)。pure stdlibのみで実行する
(他venture・本venture共通の方針、kura-pasha等のtest_post_generation_checks.py相当)。

実行方法: python3 prototype/test_due_date_logic.py
"""

import sys
from datetime import date

from due_date_logic import compute_next_due_date, should_remind


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- compute_next_due_date: 月末繰り上げの境界値(monthly) ---
    # 1/31 + 1ヶ月 -> 2月は28日まで(2026年は非うるう年)なので2/28に丸める。
    results.append(_check(
        "monthly: 1/31 + 1ヶ月 -> 2/28(非うるう年、月末繰り上げ)",
        compute_next_due_date("monthly", date(2026, 1, 31)),
        date(2026, 2, 28),
    ))
    # 1/31 + 1ヶ月、うるう年(2028年)は2/29まであるので2/29に丸める。
    results.append(_check(
        "monthly: 1/31 + 1ヶ月 -> 2/29(うるう年、月末繰り上げ)",
        compute_next_due_date("monthly", date(2028, 1, 31)),
        date(2028, 2, 29),
    ))
    # 12月をまたぐ年繰り上げ。
    results.append(_check(
        "monthly: 12/15 + 1ヶ月 -> 翌年1/15(年またぎ)",
        compute_next_due_date("monthly", date(2026, 12, 15)),
        date(2027, 1, 15),
    ))
    # 通常ケース(月末でない)。
    results.append(_check(
        "monthly: 10/3 + 1ヶ月 -> 11/3",
        compute_next_due_date("monthly", date(2026, 10, 3)),
        date(2026, 11, 3),
    ))

    # --- compute_next_due_date: うるう日境界値(annual) ---
    # 2024/2/29(うるう年) + 1年 -> 2025年は非うるう年なので2/28に丸める。
    results.append(_check(
        "annual: 2024-02-29 + 1年 -> 2025-02-28(非うるう年への丸め)",
        compute_next_due_date("annual", date(2024, 2, 29)),
        date(2025, 2, 28),
    ))
    # 通常ケース。
    results.append(_check(
        "annual: 2026-09-15 + 1年 -> 2027-09-15",
        compute_next_due_date("annual", date(2026, 9, 15)),
        date(2027, 9, 15),
    ))

    # --- compute_next_due_date: daily(期限の概念なし) ---
    results.append(_check(
        "daily: 次回期限は常にNone",
        compute_next_due_date("daily", date(2026, 10, 3)),
        None,
    ))

    # --- should_remind: 7日しきい値の境界値(annual、llm-system-prompt-draft.md 25行目) ---
    last_date = date(2025, 10, 1)
    due = date(2026, 10, 1)  # last_date + 1年
    results.append(_check(
        "annual: 期限ちょうど7日前 -> リマインド対象(境界値を含む)",
        should_remind("annual", last_date, due - date.resolution * 7),
        True,
    ))
    results.append(_check(
        "annual: 期限8日前 -> リマインド対象外",
        should_remind("annual", last_date, due - date.resolution * 8),
        False,
    ))
    results.append(_check(
        "annual: 期限6日前 -> リマインド対象",
        should_remind("annual", last_date, due - date.resolution * 6),
        True,
    ))
    results.append(_check(
        "annual: 期限当日 -> リマインド対象",
        should_remind("annual", last_date, due),
        True,
    ))
    results.append(_check(
        "annual: 期限1日超過 -> リマインド対象(超過後も通知を継続)",
        should_remind("annual", last_date, due + date.resolution * 1),
        True,
    ))

    # --- should_remind: monthlyでも同じしきい値ロジックが働くことの確認 ---
    m_last = date(2026, 9, 1)
    m_due = date(2026, 10, 1)  # m_last + 1ヶ月
    results.append(_check(
        "monthly: 期限8日前 -> リマインド対象外",
        should_remind("monthly", m_last, m_due - date.resolution * 8),
        False,
    ))
    results.append(_check(
        "monthly: 期限7日前 -> リマインド対象",
        should_remind("monthly", m_last, m_due - date.resolution * 7),
        True,
    ))

    # --- should_remind: dailyは常にFalse(次回期限の概念が無いため) ---
    results.append(_check(
        "daily: 常にリマインド対象外",
        should_remind("daily", date(2026, 10, 3), date(2026, 10, 3)),
        False,
    ))

    # --- 未知のinspection_typeの異常系(フェーズ84追記) ---
    # compute_next_due_dateのdocstring/raise ValueErrorの行自体は実装済みだが、
    # これまでテストが無く未検証だった(mvp-flow-draft.md定義の3区分
    # daily/monthly/annual以外の値が渡るのはLLM出力側の不整合時のみを想定、
    # schema/output.schema.jsonのenum制約が一次防御)。
    try:
        compute_next_due_date("weekly", date(2026, 10, 3))
        results.append(_check(
            "compute_next_due_date: 未知のinspection_typeでValueError",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "compute_next_due_date: 未知のinspection_typeでValueError",
            True, True,
        ))

    # should_remindも内部でcompute_next_due_dateを呼ぶため、同じ異常系が
    # そのまま伝播する(schema側のenum違反をここで握り潰さないことの確認)。
    try:
        should_remind("weekly", date(2026, 10, 3), date(2026, 10, 3))
        results.append(_check(
            "should_remind: 未知のinspection_typeでValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "should_remind: 未知のinspection_typeでValueError(伝播)",
            True, True,
        ))

    total = len(results)
    failed = total - sum(results)
    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
