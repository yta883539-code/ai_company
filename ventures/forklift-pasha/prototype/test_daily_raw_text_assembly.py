#!/usr/bin/env python3
"""daily_raw_text_assembly.pyの境界値テスト(フェーズ256)。pure stdlibのみで実行する
(due_date_logic.py等と同じ方針)。

実行方法: python3 prototype/test_daily_raw_text_assembly.py
"""

import sys

from daily_raw_text_assembly import DAILY_CHECKLIST_ITEMS, assemble_daily_raw_text


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- mode="ok": 全項目チェック済み(デフォルト状態) ---
    results.append(_check(
        "ok: 全6項目チェック済み",
        assemble_daily_raw_text(
            vehicle_label="1号車",
            inspector_name="山田太郎",
            date="2026-11-22",
            mode="ok",
            checked_items=list(DAILY_CHECKLIST_ITEMS),
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 1号車\n"
        "点検者: 山田太郎\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常なし\n"
        "点検項目: ブレーキ、警告灯、異音、油圧、タイヤ、フォーク",
    ))

    # --- mode="ok": 一部項目を個別にオフにした場合、オフにした項目は文章に現れない ---
    results.append(_check(
        "ok: 「タイヤ」のみオフにした場合は点検項目から除外される",
        assemble_daily_raw_text(
            vehicle_label="2号車",
            inspector_name="佐藤花子",
            date="2026-11-22",
            mode="ok",
            checked_items=["ブレーキ", "警告灯", "異音", "油圧", "フォーク"],
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 2号車\n"
        "点検者: 佐藤花子\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常なし\n"
        "点検項目: ブレーキ、警告灯、異音、油圧、フォーク",
    ))

    # --- mode="ok": 1件もチェックしなかった場合、点検項目行自体が省略される ---
    results.append(_check(
        "ok: 0件チェックの場合は点検項目行を省略",
        assemble_daily_raw_text(
            vehicle_label="1号車",
            inspector_name="山田太郎",
            date="2026-11-22",
            mode="ok",
            checked_items=[],
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 1号車\n"
        "点検者: 山田太郎\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常なし",
    ))

    # --- mode="ng": チェックした項目のみ、自由記述を付して列挙される ---
    results.append(_check(
        "ng: チェック済み項目+自由記述を結合",
        assemble_daily_raw_text(
            vehicle_label="3号車",
            inspector_name="鈴木一郎",
            date="2026-11-22",
            mode="ng",
            checked_items=["ブレーキ", "異音"],
            item_notes={"ブレーキ": "効きが甘い気がする", "異音": "走行時にカタカタ音がする"},
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 3号車\n"
        "点検者: 鈴木一郎\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常あり\n"
        "点検項目: ブレーキ:効きが甘い気がする、異音:走行時にカタカタ音がする",
    ))

    # --- mode="ng": チェック済みだが自由記述が空欄の項目は、項目名のみで(虚偽の補完をしない) ---
    results.append(_check(
        "ng: 自由記述が空欄の項目は項目名のみそのまま含める",
        assemble_daily_raw_text(
            vehicle_label="1号車",
            inspector_name="山田太郎",
            date="2026-11-22",
            mode="ng",
            checked_items=["油圧"],
            item_notes={"油圧": "   "},
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 1号車\n"
        "点検者: 山田太郎\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常あり\n"
        "点検項目: 油圧",
    ))

    # --- mode="ng": item_notesを渡さなかった場合も例外にならず項目名のみで扱う ---
    results.append(_check(
        "ng: item_notes省略時もKeyErrorにならず項目名のみ",
        assemble_daily_raw_text(
            vehicle_label="1号車",
            inspector_name="山田太郎",
            date="2026-11-22",
            mode="ng",
            checked_items=["フォーク"],
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 1号車\n"
        "点検者: 山田太郎\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常あり\n"
        "点検項目: フォーク",
    ))

    # --- mode="ng": 0件チェックの場合も点検項目行自体が省略される ---
    results.append(_check(
        "ng: 0件チェックの場合は点検項目行を省略",
        assemble_daily_raw_text(
            vehicle_label="1号車",
            inspector_name="山田太郎",
            date="2026-11-22",
            mode="ng",
            checked_items=[],
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 1号車\n"
        "点検者: 山田太郎\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常あり",
    ))

    # --- 新規車両(自由記述枠)で入力されたラベルもそのまま転記される ---
    results.append(_check(
        "ok: 新規車両の自由記述ラベルもそのまま車両欄に転記",
        assemble_daily_raw_text(
            vehicle_label="4号車(新規・北倉庫)",
            inspector_name="山田太郎",
            date="2026-11-22",
            mode="ok",
            checked_items=["ブレーキ"],
        ),
        "点検種別: 日次点検(作業開始前点検)\n"
        "車両: 4号車(新規・北倉庫)\n"
        "点検者: 山田太郎\n"
        "実施日: 2026-11-22\n"
        "点検結果: 異常なし\n"
        "点検項目: ブレーキ",
    ))

    # --- mode不正値はValueErrorとして伝播する(呼び出し元のバグとして扱う契約) ---
    try:
        assemble_daily_raw_text(
            vehicle_label="1号車",
            inspector_name="山田太郎",
            date="2026-11-22",
            mode="unknown",
            checked_items=[],
        )
        results.append(_check(
            "mode不正値はValueError(伝播)", "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check("mode不正値はValueError(伝播)", True, True))

    total = len(results)
    failed = total - sum(results)
    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
