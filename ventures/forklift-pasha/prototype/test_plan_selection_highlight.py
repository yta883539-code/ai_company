#!/usr/bin/env python3
"""plan_selection_highlight.pyの境界値テスト(フェーズ141)。pure stdlibのみで実行する
(plan_id_resolution.py等と同じ方針)。web-form-mockup/plan-selection.htmlを実際に
読み込み、design(plan-selection-current-plan-highlight-design.md)4節のテスト観点
(各plan_idごとに対応する1枚のみ切り替わる・Noneや未知の値では変化しない)を確認する。

実行方法: python3 prototype/test_plan_selection_highlight.py
"""

import sys
from pathlib import Path

from plan_selection_highlight import DEFAULT_BUTTON_LABEL, apply_current_plan_highlight

HTML_PATH = (
    Path(__file__).parent.parent / "web-form-mockup" / "plan-selection.html"
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []
    html = HTML_PATH.read_text(encoding="utf-8")

    # plan-selection.html自体にも、説明コメント・CSSセレクタ定義として
    # "plan-card--current"/「現在のプラン」相当の文字列が元から含まれているため、
    # 単純な存在確認ではなく、無変更時(baseline)との差分件数で検証する。
    baseline_current_class_count = html.count("plan-card--current")
    baseline_current_label_count = html.count("現在のプラン")
    baseline_apply_label_count = html.count(DEFAULT_BUTTON_LABEL)

    # --- current_plan_idが既知の値の場合、対応する1枚のみ切り替わる ---
    for plan_id in ("light", "standard", "fleet"):
        rendered = apply_current_plan_highlight(html, plan_id)
        results.append(_check(
            f"plan_id={plan_id!r}: 対応カードにplan-card--currentクラスが付く",
            rendered.count(
                'class="plan-card plan-card--current" data-plan-id="%s"' % plan_id
            ),
            1,
        ))
        results.append(_check(
            f"plan_id={plan_id!r}: plan-card--current文字列はbaseline+1件のみ"
            "(他の2枚には付かない)",
            rendered.count("plan-card--current"),
            baseline_current_class_count + 1,
        ))
        results.append(_check(
            f"plan_id={plan_id!r}: 「現在のプラン」ボタンがbaseline+1件生成される",
            rendered.count("現在のプラン"),
            baseline_current_label_count + 1,
        ))
        results.append(_check(
            f"plan_id={plan_id!r}: 「このプランで申し込む」ボタンはbaseline-1件",
            rendered.count(DEFAULT_BUTTON_LABEL),
            baseline_apply_label_count - 1,
        ))

    # --- current_plan_idがNoneの場合、いずれのカードも変化しない ---
    rendered_none = apply_current_plan_highlight(html, None)
    results.append(_check(
        "current_plan_id=None: 入力HTMLと完全に一致する(変更なし)",
        rendered_none,
        html,
    ))

    # --- 未知の値(KNOWN_PLAN_IDSに含まれない)は安全側に倒しNone相当で無変化 ---
    for unknown in ("premium", "", "LIGHT", "light "):
        rendered_unknown = apply_current_plan_highlight(html, unknown)
        results.append(_check(
            f"current_plan_id={unknown!r}(未知): 入力HTMLと完全に一致する(変更なし)",
            rendered_unknown,
            html,
        ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
