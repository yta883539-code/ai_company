#!/usr/bin/env python3
"""inspector-name-date-prefill-design.md(フェーズ261)4節(3)の実装。daily.html/
daily-empty.htmlをGETリクエスト時にサーバー側で動的レンダリングする処理本体。

design.md 1節の決定どおり、クライアント側JSは依然ゼロ(ブラウザに送られるHTMLは相変わらず
静的なプレーンHTML)のまま、`inspector_name`・`date`の2箇所の`value`属性だけをレンダリング
時に算出した値へ文字列置換する最小実装とする(design.md 4節(4)「テンプレートエンジンの
選定」は、新規の外部依存を避け標準ライブラリのみで足りる文字列置換方式を採用、と決定)。

web-form-mockup/daily.html・daily-empty.htmlはいずれも
`<input type="text" class="prefill-input" name="inspector_name" value="山田 太郎">`・
`<input type="date" class="prefill-input" name="date" value="2026-10-06">`という同一の
形(フェーズ259・260で実input化済み)で埋め込まれているため、1種類の置換ロジックを両HTMLに
共通して使える。
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

_INSPECTOR_NAME_VALUE_PATTERN = re.compile(r'(name="inspector_name" value=")[^"]*(")')
_DATE_VALUE_PATTERN = re.compile(r'(name="date" value=")[^"]*(")')


def today_jst_date_str(now: "datetime | None" = None) -> str:
    """実施日(date input)に注入する「当日」の日付文字列(YYYY-MM-DD、JST基準)。

    design.md 2節の決定: 実施日は常に当日固定でキャッシュ不要(他venture・スケジューラ設計
    と同じJST基準)。`now`省略時は現在時刻を使い、注入時は`now`(呼び出し元からの注入はテスト
    用。tzinfo無しの場合はJSTとみなす)をJSTへ変換してから日付を取り出す。
    """
    moment = now if now is not None else datetime.now(JST)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=JST)
    return moment.astimezone(JST).strftime("%Y-%m-%d")


def render_daily_form_html(template_html: str, *, date: str, inspector_name: str) -> str:
    """daily.html/daily-empty.htmlのテンプレート文字列を受け取り、`inspector_name`・
    `date`のvalue属性だけを注入済みの値に置き換えた結果を返す(design.md 4節(3))。

    `inspector_name`が空文字列(初回アクセス・事業者単位キャッシュ未設定)の場合、ダミー
    初期値「山田 太郎」を本番で表示しないというdesign.md 5節の方針に従い空欄になる(置換後の
    値がそのまま空文字列になる)。`inspector_name`はフォーム利用者が過去に入力した自由文字列
    のため、`"`や`<`等を含んでいても属性値の外に出てHTMLを破壊しないよう`html.escape()`で
    エスケープしてから埋め込む(dateはサーバー側で算出した`YYYY-MM-DD`形式のみのためエスケープ
    不要だが、契約を揺らさないよう同様に処理する)。
    """
    escaped_inspector_name = html.escape(inspector_name, quote=True)
    escaped_date = html.escape(date, quote=True)
    rendered, count = _INSPECTOR_NAME_VALUE_PATTERN.subn(
        lambda m: f"{m.group(1)}{escaped_inspector_name}{m.group(2)}", template_html, count=1
    )
    if count != 1:
        raise ValueError("inspector_nameのvalue属性がテンプレート内に見つからない")
    rendered, count = _DATE_VALUE_PATTERN.subn(
        lambda m: f"{m.group(1)}{escaped_date}{m.group(2)}", rendered, count=1
    )
    if count != 1:
        raise ValueError("dateのvalue属性がテンプレート内に見つからない")
    return rendered
