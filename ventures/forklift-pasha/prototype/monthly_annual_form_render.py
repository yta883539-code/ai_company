#!/usr/bin/env python3
"""monthly-annual-get-rendering-decision.md(フェーズ264)4節(1)(4)の実装。

monthly.html/annual.htmlをGETリクエスト時にサーバー側で動的レンダリングする処理本体。
daily_form_render.render_daily_form_html()とは異なり、本モジュールは「実施日」のみを
注入する(decision.md 4節(2)の決定どおり、点検者名キャッシュは本フェーズでは着手せず、
点検者名欄は静的モックアップのダミー値「山田 太郎」のまま残る。次回候補として持ち越し)。

monthly.html/annual.htmlの「点検者・実施日」ブロックは、点検者名・実施日のいずれも
`<span><span class="value">...</span> <a class="edit-link" href="#">変更</a></span>`という
同一のspan+変更リンク形式で表示されており(daily.htmlの`<input value="...">`形式とは異なる
構造、decision.md 1節)、クラス名だけでは点検者名行と実施日行を区別できない。そのため本
モジュールの置換パターンは、直前の`<span>実施日</span>`ラベルを手がかりに実施日行のみを
対象とする(点検者名行の「山田 太郎」は意図的に置換対象から外す)。
"""

from __future__ import annotations

import html
import re

_DATE_ROW_VALUE_PATTERN = re.compile(
    r'(<span>実施日</span>\s*<span><span class="value">)[^<]*(</span>)'
)


def render_date_only_html(template_html: str, *, date: str) -> str:
    """monthly.html/annual.htmlのテンプレート文字列を受け取り、「実施日」行の
    value spanだけを注入済みの値に置き換えた結果を返す(decision.md 4節(1)(4))。

    点検者名行は対象外のため、テンプレート側のダミー値「山田 太郎」がそのまま残る
    (decision.md 4節(2)、点検者名キャッシュは次回候補)。`date`はサーバー側で算出した
    `YYYY-MM-DD`形式のみを想定するが、daily_form_render.render_daily_form_html()と契約を
    揺らさないよう同様にエスケープしてから埋め込む。
    """
    escaped_date = html.escape(date, quote=True)
    rendered, count = _DATE_ROW_VALUE_PATTERN.subn(
        lambda m: f"{m.group(1)}{escaped_date}{m.group(2)}", template_html, count=1
    )
    if count != 1:
        raise ValueError("実施日のvalue属性(span)がテンプレート内に見つからない")
    return rendered
