#!/usr/bin/env python3
"""
フェーズ27のtest_due_date_integration.pyで保留とした、should_remind()
(リマインド要否判定)の統合テスト(フェーズ28、フェーズ27「次回候補」(1)に対応)。

位置づけ:
- schema/validate_test_cases.pyのG2/G3/G4フィクスチャにはreminder_notice
  (生成済みの固定文面)はあるが、それがどの「今日」の日付で生成されたかの情報は
  含まれていない。そのためG2/G3/G4のreminder_notice有無とshould_remind()の
  結果を直接比較することはできない(フェーズ27で明記した制約)。
- 本テストでは、フェーズ27で突き合わせ済みのG2/G3/G4のnext_due_date
  (2026-11-01・2025-12-05・2027-09-15)を起点に、「今日」の日付を明示した新規
  境界値ケースを追加し、should_remind()がREMINDER_THRESHOLD_DAYS(7日)の
  境界を正しく判定することを検証する。last_dateはG2/G3/G4フィクスチャと同じ値を
  使うことで、next_due_date算出からリマインド要否判定までの一連の流れを
  通して確認する(真の意味での統合テスト)。

実行方法: python3 prototype/test_should_remind_integration.py
"""

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "schema"))

from due_date_logic import compute_next_due_date, should_remind  # noqa: E402
from validate_test_cases import (  # noqa: E402
    CASE_G1_DAILY,
    CASE_G2_MONTHLY_NO_REMINDER,
    CASE_G3_MONTHLY_WITH_REMINDER,
    CASE_G4_ANNUAL_WITH_COMPANY,
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # G2(monthly, last_date=2026-10-01 -> due=2026-11-01、フェーズ27で確認済み)
    g2_last = date.fromisoformat(CASE_G2_MONTHLY_NO_REMINDER["inspection_record"]["date"])
    g2_due = compute_next_due_date("monthly", g2_last)
    results.append(_check(
        "G2: due-today=7日(境界、ちょうど7日前) -> should_remind=True",
        should_remind("monthly", g2_last, g2_due - timedelta(days=7)), True,
    ))
    results.append(_check(
        "G2: due-today=8日(7日しきい値の外) -> should_remind=False",
        should_remind("monthly", g2_last, g2_due - timedelta(days=8)), False,
    ))
    results.append(_check(
        "G2: today=due当日 -> should_remind=True",
        should_remind("monthly", g2_last, g2_due), True,
    ))
    results.append(_check(
        "G2: today=due翌日(1日超過) -> should_remind=True",
        should_remind("monthly", g2_last, g2_due + timedelta(days=1)), True,
    ))

    # G3(monthly, last_date=2025-11-05 -> due=2025-12-05、フェーズ27で確認済み)
    g3_last = date.fromisoformat(CASE_G3_MONTHLY_WITH_REMINDER["inspection_record"]["date"])
    g3_due = compute_next_due_date("monthly", g3_last)
    results.append(_check(
        "G3: due-today=7日(境界) -> should_remind=True",
        should_remind("monthly", g3_last, g3_due - timedelta(days=7)), True,
    ))
    results.append(_check(
        "G3: due-today=8日 -> should_remind=False",
        should_remind("monthly", g3_last, g3_due - timedelta(days=8)), False,
    ))

    # G4(annual, last_date=2026-09-15 -> due=2027-09-15、フェーズ27で確認済み)
    g4_last = date.fromisoformat(CASE_G4_ANNUAL_WITH_COMPANY["inspection_record"]["date"])
    g4_due = compute_next_due_date("annual", g4_last)
    results.append(_check(
        "G4: due-today=7日(境界) -> should_remind=True",
        should_remind("annual", g4_last, g4_due - timedelta(days=7)), True,
    ))
    results.append(_check(
        "G4: due-today=8日 -> should_remind=False",
        should_remind("annual", g4_last, g4_due - timedelta(days=8)), False,
    ))

    # G1(daily, 次回期限の概念が無い) -> 常にFalse
    g1_last = date.fromisoformat(CASE_G1_DAILY["inspection_record"]["date"])
    results.append(_check(
        "G1(daily): 次回期限が無いためtoday=last_dateでもshould_remind=False",
        should_remind("daily", g1_last, g1_last), False,
    ))

    total = len(results)
    failed = total - sum(results)
    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
