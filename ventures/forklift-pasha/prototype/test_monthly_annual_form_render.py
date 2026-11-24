#!/usr/bin/env python3
"""monthly_annual_form_render.pyの境界値テスト(フェーズ265)。pure stdlibのみで実行する
(daily_form_render.py・test_daily_form_render.pyと同じ方針)。

実行方法: python3 prototype/test_monthly_annual_form_render.py
"""

import sys

from monthly_annual_form_render import render_date_only_html

_SAMPLE_TEMPLATE = (
    '<div class="prefill-row">\n'
    '  <span>点検者名</span>\n'
    '  <span><span class="value">山田 太郎</span> <a class="edit-link" href="#">変更</a></span>\n'
    '</div>\n'
    '<div class="prefill-row">\n'
    '  <span>実施日</span>\n'
    '  <span><span class="value">2026-10-06</span> <a class="edit-link" href="#">変更</a></span>\n'
    '</div>'
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- render_date_only_html: 実施日のダミー値だけが置換される ---
    rendered = render_date_only_html(_SAMPLE_TEMPLATE, date="2026-11-24")
    results.append(_check(
        "render_date_only_html: 実施日のダミー値〈2026-10-06〉が置換される",
        '<span>実施日</span>\n  <span><span class="value">2026-11-24</span>' in rendered,
        True,
    ))
    results.append(_check(
        "render_date_only_html: 点検者名行のダミー値〈山田 太郎〉は対象外のまま残る"
        "(decision.md 4節(2)、点検者名キャッシュは次回候補)",
        '<span>点検者名</span>\n  <span><span class="value">山田 太郎</span>' in rendered,
        True,
    ))
    results.append(_check(
        "render_date_only_html: 旧ダミー値〈2026-10-06〉自体はテンプレートに残らない",
        "2026-10-06" not in rendered,
        True,
    ))

    # --- render_date_only_html: HTML特殊文字はエスケープされる(契約上は発生しない想定だが、
    # daily_form_render.render_daily_form_html()と同じ安全側の挙動を確認する) ---
    rendered_escaped = render_date_only_html(_SAMPLE_TEMPLATE, date='2026-11-24"<script>')
    results.append(_check(
        "render_date_only_html: dateに二重引用符・<script>タグが含まれてもエスケープされる",
        "<script>" not in rendered_escaped and "&lt;script&gt;" in rendered_escaped,
        True,
    ))

    # --- render_date_only_html: 「実施日」行自体が無いテンプレートはValueError ---
    try:
        render_date_only_html(
            '<span>点検者名</span>\n'
            '<span><span class="value">山田 太郎</span> <a class="edit-link" href="#">変更</a></span>',
            date="2026-11-24",
        )
        results.append(_check(
            "render_date_only_html: 実施日行が無いテンプレートはValueError",
            "例外が発生しなかった",
            "ValueError",
        ))
    except ValueError:
        results.append(_check(
            "render_date_only_html: 実施日行が無いテンプレートはValueError",
            True,
            True,
        ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
