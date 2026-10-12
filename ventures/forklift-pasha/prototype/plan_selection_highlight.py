#!/usr/bin/env python3
"""plan-selection-current-plan-highlight-design.md(フェーズ140)の表示切り替えルールを
実装する純粋関数。`main(request)`(Webフォームバックエンドのルーティング未確定のため
本venture未実装)がテンプレート変数`current_plan_id`を解決した後、
`web-form-mockup/plan-selection.html`の文字列にこの関数を適用する想定。

design 4節の方針(未知のplan_idは安全側に倒しNoneとして扱う)により、
`current_plan_id`の正当性チェックは`plan_id_resolution.KNOWN_PLAN_IDS`を正とする。
"""

import re

from plan_id_resolution import KNOWN_PLAN_IDS

DEFAULT_BUTTON_LABEL = "このプランで申し込む"
CURRENT_BUTTON_LABEL = "現在のプラン"

_PLAN_CARD_PATTERN = re.compile(
    r'<section class="plan-card" data-plan-id="(?P<plan_id>[a-z]+)">.*?</section>',
    re.DOTALL,
)


def apply_current_plan_highlight(html: str, current_plan_id) -> str:
    """design 3節の表示切り替えルールをHTML文字列に適用する。

    `current_plan_id`が`KNOWN_PLAN_IDS`("light"/"standard"/"fleet")のいずれかと
    一致するカードのみ、`class`に`plan-card--current`を追加しボタン文言を
    「現在のプラン」に変える(disabledのまま維持、ボタンのdisabled属性自体はHTML側で
    既に付与済みのため本関数では変更しない)。一致しない他のカード・
    `current_plan_id`が`KNOWN_PLAN_IDS`に含まれない場合(Noneや未知の値)は
    入力HTMLをそのまま返す。
    """
    if current_plan_id not in KNOWN_PLAN_IDS:
        return html

    def replace_section(match: "re.Match[str]") -> str:
        section = match.group(0)
        if match.group("plan_id") != current_plan_id:
            return section
        section = section.replace(
            'class="plan-card" data-plan-id="%s"' % current_plan_id,
            'class="plan-card plan-card--current" data-plan-id="%s"' % current_plan_id,
            1,
        )
        return section.replace(DEFAULT_BUTTON_LABEL, CURRENT_BUTTON_LABEL, 1)

    return _PLAN_CARD_PATTERN.sub(replace_section, html)
