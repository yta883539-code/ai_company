#!/usr/bin/env python3
"""web-form-ui-design.mdフェーズ71「daily区分の入力画面」・form_submission_flow.py
main()のdocstringが次回候補として残していた「Webフォームのボタン選択・プルダウン入力を
フォーム送信前に1本の自由記述文(raw_text)へ組み立てる処理」に着手する(フェーズ256)。

設計上の判断: web-form-mockup/daily.html冒頭コメントの方針「JSは一切使用せず」
(course-set-pasha/liff-plan-selection-ui-wireframe.md等と同じJS不使用方針)を維持したまま
raw_textを組み立てるには、ブラウザ側JSで複数inputの値を1本の文字列へ結合することができない
(CSSのみでは不可能)。そのため、組み立て処理自体はフロントエンドJSではなく**サーバー側**に
置き、ブラウザは通常のHTML `<form>` POST(JS不使用)で各input/checkbox/textareaの値を
個別のフォームフィールドとしてそのまま送信し、本モジュールがサーバー側でそれらを結合して
raw_text相当の文字列を組み立てる方式とする。これにより「JS不使用」の方針と「raw_textへの
事前組み立て」の両方を矛盾なく満たせる。

本モジュールはdaily区分(始業前点検)専用。typeフィールドはURL(どの入力画面から送信
されたか)で確定済みという設計(web-form-ui-design.md 14行目)のため、組み立てる文章の
先頭に点検種別を明記した固定行を含める(LLM側のtype抽出〈schema/output.schema.jsonの
type、記載が無い場合はinsufficient_input〉を、本画面ではURLで確定済みのdailyとして
常に満たせるようにするため)。

未着手として残す範囲(次回候補):
- web-form-mockup/daily.htmlに実際の`<form>`タグ・各inputへの`name`属性・送信時の
  action配線を追加すること自体(現状のdaily.htmlはフォーム送信に一切接続されていない
  静的モックアップのまま、本フェーズではHTML側の変更は行わない)。
- main()/receive_form_submission()が、素のraw_textに代えて本モジュールが要求する
  構造化フィールド群を受け取り、本モジュールを呼び出してからprocess_form_submission()に
  委譲するよう配線すること(daily区分のURL〈Cloud Functionsのルーティング〉をどう
  monthly/annualと区別するかという設計判断が別途必要なため、本フェーズでは据え置く)。
- monthly/annual区分は現状自由記述欄方式のまま(web-form-ui-design.md「未検証・残課題」
  記載のとおりチェックリスト化自体が未判断)のため、本モジュールと同種の組み立て処理は
  対象外。
"""

from __future__ import annotations

# daily.html・market-research.md記載の一般的な点検項目(安衛則第151条の25の参考例)。
# 正式な項目一覧の確定(実LLM検証・実顧客ヒアリング後)は未着手(daily.html冒頭コメント
# 「未実装・意図的なプレースホルダー」に同じ注記あり)。
DAILY_CHECKLIST_ITEMS = ("ブレーキ", "警告灯", "異音", "油圧", "タイヤ", "フォーク")

_MODE_OK = "ok"
_MODE_NG = "ng"
_VALID_MODES = (_MODE_OK, _MODE_NG)


def assemble_daily_raw_text(
    *,
    vehicle_label: str,
    inspector_name: str,
    date: str,
    mode: str,
    checked_items: "list[str]",
    item_notes: "dict[str, str] | None" = None,
) -> str:
    """daily区分の構造化フィールド(ブラウザが通常のフォームPOSTでそのまま送信した値)を、
    process_form_submission()にそのまま渡せる1本の自由記述文(raw_text)へ組み立てる。

    - `mode="ok"`(「異常なし」選択): `checked_items`はチェックを外さなかった(=該当する)
      項目名のみを渡す。web-form-ui-design.md 2.のとおり「異常なし」側はデフォルト全
      チェック済みで、該当しない項目は個別にオフにできる設計のため、オフにされた項目は
      そもそも`checked_items`に含まれず、組み立て後の文章にも現れない。
    - `mode="ng"`(「異常あり」選択): `checked_items`はオンにした(=異常を申告した)項目名
      のみを渡す。`item_notes`は項目名をキーとする自由記述(「どう異常だったか」)の対応表。
      厳守事項1(AIが独自に安全性評価を追記しない)に合わせ、本関数も記述内容を一切加工
      せず転記するのみ(空文字列のnoteも、項目名のみの形でそのまま含める。虚偽の記述を
      補わない)。
    - 一方の値が空文字列・`checked_items`が空リストであっても、本関数自体はエラーに
      せず組み立てを続行する(厳守事項2「推測で埋めない」の判定自体はLLM側
      〈schema/output.schema.jsonのinsufficient_input〉の責務であり、本関数はその手前の
      文章組み立てのみを担う。他venture同様、insufficient_inputの判定ロジックを
      フロントエンド・組み立て層とLLM層の二重に持たない方針)。

    Raises:
        ValueError: `mode`が"ok"/"ng"のいずれでもない場合(呼び出し元のバグ、daily.html
        のラジオボタン値が"ok"/"ng"以外を送ってくることは想定しない契約違反のため、
        他venture同様フォームの欠落・空文字列とは区別しValueErrorとして伝播させる)。
    """
    if mode not in _VALID_MODES:
        raise ValueError(f"invalid mode: {mode!r} (expected one of {_VALID_MODES!r})")

    lines = [
        "点検種別: 日次点検(作業開始前点検)",
        f"車両: {vehicle_label}",
        f"点検者: {inspector_name}",
        f"実施日: {date}",
    ]

    if mode == _MODE_OK:
        lines.append("点検結果: 異常なし")
        if checked_items:
            lines.append("点検項目: " + "、".join(checked_items))
    else:
        lines.append("点検結果: 異常あり")
        notes = item_notes or {}
        item_lines = []
        for item in checked_items:
            note = notes.get(item, "").strip()
            item_lines.append(f"{item}:{note}" if note else item)
        if item_lines:
            lines.append("点検項目: " + "、".join(item_lines))

    return "\n".join(lines)
