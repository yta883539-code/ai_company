#!/usr/bin/env python3
"""daily_form_render.pyの境界値テスト(フェーズ263)。pure stdlibのみで実行する
(trial_management.py等と同じ方針)。

実行方法: python3 prototype/test_daily_form_render.py
"""

import sys
from datetime import datetime, timedelta, timezone

from daily_form_render import render_daily_form_html, today_jst_date_str

_SAMPLE_TEMPLATE = (
    '<input type="text" class="prefill-input" name="inspector_name" value="山田 太郎">\n'
    '<input type="date" class="prefill-input" name="date" value="2026-10-06">'
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- render_daily_form_html: 通常値の置換 ---
    rendered = render_daily_form_html(_SAMPLE_TEMPLATE, date="2026-11-24", inspector_name="鈴木 一郎")
    results.append(_check(
        "render_daily_form_html: inspector_nameのダミー値〈山田 太郎〉が置換される",
        'name="inspector_name" value="鈴木 一郎"' in rendered,
        True,
    ))
    results.append(_check(
        "render_daily_form_html: dateのダミー値〈2026-10-06〉が置換される",
        'name="date" value="2026-11-24"' in rendered,
        True,
    ))
    results.append(_check(
        "render_daily_form_html: 置換対象外の文言〈山田 太郎〉はテンプレートに残らない",
        "山田 太郎" not in rendered,
        True,
    ))

    # --- render_daily_form_html: inspector_name空文字列(初回アクセス)は空欄になる ---
    rendered_empty = render_daily_form_html(_SAMPLE_TEMPLATE, date="2026-11-24", inspector_name="")
    results.append(_check(
        "render_daily_form_html: inspector_name空文字列はvalue=\"\"(空欄)になる",
        'name="inspector_name" value="">' in rendered_empty,
        True,
    ))

    # --- render_daily_form_html: inspector_nameにHTML特殊文字が含まれる場合はエスケープされる ---
    rendered_escaped = render_daily_form_html(
        _SAMPLE_TEMPLATE, date="2026-11-24", inspector_name='山田"太郎<script>'
    )
    results.append(_check(
        "render_daily_form_html: inspector_nameの二重引用符・<script>タグはエスケープされ、"
        "属性値の外に出てHTMLを破壊しない",
        '<script>' not in rendered_escaped and "&lt;script&gt;" in rendered_escaped,
        True,
    ))

    # --- render_daily_form_html: inspector_nameのvalue属性が無いテンプレートはValueError ---
    try:
        render_daily_form_html(
            '<input type="date" class="prefill-input" name="date" value="2026-10-06">',
            date="2026-11-24",
            inspector_name="鈴木 一郎",
        )
        results.append(_check(
            "render_daily_form_html: inspector_nameのvalue属性が無いテンプレートはValueError",
            "例外が発生しなかった",
            "ValueError",
        ))
    except ValueError:
        results.append(_check(
            "render_daily_form_html: inspector_nameのvalue属性が無いテンプレートはValueError",
            True,
            True,
        ))

    # --- today_jst_date_str: JSTで日付を算出する(UTCとJSTで日付が異なる時刻での確認) ---
    # UTC 2026-11-23 15:30はJST 2026-11-24 00:30(日付が繰り上がる境界)
    utc_moment = datetime(2026, 11, 23, 15, 30, 0, tzinfo=timezone.utc)
    results.append(_check(
        "today_jst_date_str: UTC 23日15:30(JST 24日00:30)はJST基準で24日と算出される",
        today_jst_date_str(utc_moment),
        "2026-11-24",
    ))

    # --- today_jst_date_str: tzinfo無しのnaive datetimeはJSTとみなす ---
    naive_moment = datetime(2026, 11, 24, 9, 0, 0)
    results.append(_check(
        "today_jst_date_str: tzinfo無しのnaive datetimeはそのままJSTの日付として使う",
        today_jst_date_str(naive_moment),
        "2026-11-24",
    ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
