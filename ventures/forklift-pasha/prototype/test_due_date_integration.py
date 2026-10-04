#!/usr/bin/env python3
"""
schema/validate_test_cases.pyのG2/G3/G4フィクスチャの body/reminder_notice に
手動計算値として埋め込まれた次回実施期限と、prototype/due_date_logic.pyの
compute_next_due_date()の計算結果を突き合わせる統合テスト(フェーズ27、
due_date_logic.py作成〈フェーズ26〉時の次回候補(1)に対応)。

位置づけ:
- G2/G3/G4フィクスチャの日付(次回期限2026-11-01・2025-12-05・2027-09-15)は、
  due_date_logic.py実装前(フェーズ3でのフィクスチャ作成時点)に人手で計算した
  固定値であり、実装後の計算ロジックと一度も突き合わせていなかった。本テストは
  その整合性を機械的に検証する。
- reminder_notice有無そのものの判定(should_remind、「今日」の情報が必要)は、
  フィクスチャに「今日」の日付が含まれておらず対象外とする。次回実施期限の値自体の
  整合のみを扱う。

実行方法: python3 prototype/test_due_date_integration.py
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "schema"))

from due_date_logic import compute_next_due_date  # noqa: E402
from validate_test_cases import (  # noqa: E402
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

    g2 = CASE_G2_MONTHLY_NO_REMINDER["inspection_record"]
    computed_g2 = compute_next_due_date("monthly", date.fromisoformat(g2["date"]))
    results.append(_check(
        "G2(monthly, 2026-10-01実施): compute_next_due_date -> 2026-11-01",
        computed_g2, date(2026, 11, 1),
    ))

    g3 = CASE_G3_MONTHLY_WITH_REMINDER["inspection_record"]
    computed_g3 = compute_next_due_date("monthly", date.fromisoformat(g3["date"]))
    results.append(_check(
        "G3(monthly, 2025-11-05実施): compute_next_due_date -> 2025-12-05",
        computed_g3, date(2025, 12, 5),
    ))
    results.append(_check(
        "G3: reminder_notice本文に記載の期限文字列がcompute_next_due_date()の結果と一致",
        computed_g3.isoformat() in g3["reminder_notice"], True,
    ))

    g4 = CASE_G4_ANNUAL_WITH_COMPANY["inspection_record"]
    computed_g4 = compute_next_due_date("annual", date.fromisoformat(g4["date"]))
    results.append(_check(
        "G4(annual, 2026-09-15実施): compute_next_due_date -> 2027-09-15",
        computed_g4, date(2027, 9, 15),
    ))

    total = len(results)
    failed = total - sum(results)
    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
