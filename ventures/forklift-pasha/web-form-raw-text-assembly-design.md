# daily.htmlのUI選択値→raw_text組み立て設計(フェーズ240)

位置づけ: web-form-ui-design.md(フェーズ71)が定めたボタン選択・プルダウン中心の
daily区分入力UI(web-form-mockup/daily.html)と、form_submission_flow.pyの
receive_form_submission()が要求する単一のraw_text自由記述フィールド
(`request.form.get("raw_text")`、prototype/form_submission_flow.py 319行目)との
間を橋渡しする、フロントエンド側の組み立てロジックの机上設計(フェーズ239
「次回候補(2)」対応)。daily.html自体は「JS不使用」方針(フェーズ72・77、CSSの
`:checked`/`:has()`疑似クラスのみで画面を再現する既定方針)を踏襲した静的モック
アップであるため、本フェーズでは実コード化(JS実装)は行わず設計のみとし、実際の
関数実装は実フォーム実装・ホスティング(いずれもオーナー承認待ち、pending-approval.md
参照)に合わせて行う。

## 背景

mvp-flow-draft.md(フェーズ1)の入力例が示すとおり、バックエンドが期待する
raw_text(入力メモ)は「2号機、始業前点検、ブレーキ○、警告灯○、異音なし、
2026-10-02」のような1本の自然文であり、llm_generate()がこれを解釈して
schema/output.schema.json準拠の構造化出力(vehicle_id・result・items等)を
生成する想定になっている。一方web-form-ui-design.mdのdaily区分UIは、この
自然文を点検者に直接書かせず、車両ボタン・異常なし/異常ありの一次選択・
項目チェックリスト・自由記述欄(異常あり時のみ)という構造化された入力に
分解している(入力負荷低減が目的)。両者の間には「構造化された選択値を
どう1本のraw_textへ戻すか」という組み立て処理が必要だが、この処理自体は
これまでどのventure側設計文書にも記載がなく、本フェーズで新規に設計する。

## 組み立て方針

対象はdaily.htmlのDOM構造(フェーズ228時点)。実装時は下記相当のテキスト
テンプレートをJSで組み立て、フォーム送信直前にhidden input(name="raw_text")
または`FormData`へ設定する想定。

### 入力元の値

- `vehicle_label`: `input[name="vehicle"]:checked`に対応する表示ラベル
  (「1号車」等)。`#vehicle-new`が選ばれている場合は`.vehicle-add-input`の
  入力値をそのまま使う(空の場合は後述のとおり送信不可とする)。
- `mode`: `input[name="mode"]:checked`が`#mode-ok`か`#mode-ng`か。
- 「異常なし」モード: `.checklist-ok`内の項目名(`.item-name`)全件を
  表示順にそのまま使う(個別オフは本モックアップでは未実装のため全件固定)。
- 「異常あり」モード: `.checklist-ng .item-block`を1件ずつ走査し、
  `input[type="checkbox"]`がオンの項目のみ`.item-check-label-text`の
  項目名と`.item-note`の自由記述を組にして使う。オフの項目は「異常なし」
  として別途まとめる(厳守事項1との整合のため、オンにした項目の自由記述は
  点検者本人の記述をそのまま転記し、言い換え・要約はJS側でも行わない)。
- `inspector`: `.prefill-row`1件目の`.value`(点検者名、デフォルト値表示)。
- `date`: `.prefill-row`2件目の`.value`(実施日、デフォルト値表示)。

### テンプレート

- 異常なしモード:
  `"{vehicle_label}、始業前点検、{items.join('・')}異常なし、点検者:{inspector}、{date}実施"`
  例: 「1号車、始業前点検、ブレーキ・警告灯・異音・異臭・油圧(リフト・チルト)・
  タイヤ・フォーク異常なし、点検者:山田 太郎、2026-10-06実施」
- 異常ありモード:
  `"{vehicle_label}、始業前点検、{for each checked item: item_name}:{item_note}。"`
  を異常あり項目ごとに連結し、続けて異常なし項目があれば
  `"{items_ok.join('・')}は異常なし。"`を追記、最後に
  `"点検者:{inspector}、{date}実施"`を付す。
  例: 「1号車、始業前点検、ブレーキ:ブレーキペダルの戻りがやや遅い気がする。
  警告灯・異音・異臭・油圧(リフト・チルト)・タイヤ・フォークは異常なし。
  点検者:山田 太郎、2026-10-06実施」

この形式はmvp-flow-draft.mdの入力例(「2号機、始業前点検、ブレーキ○、警告灯○、
異音なし、2026-10-02」)と同じ「車両・区分・項目別所見・日付」の並びを保つため、
llm-system-prompt-draft.mdが前提とする入力メモの一般的な形式から外れず、
既存のllm_generate()側の想定(スタブ・実LLM双方)を変更する必要はないと判断した。

## 未検証・残課題

- 実際のJS実装(DOMから値を集約してraw_textを組み立てる関数、仮称
  `buildDailyRawText()`)は、daily.html自体の「JS不使用」方針を変更する
  タイミング(実フォーム実装着手時)に合わせて行う。本設計はその際の
  参照資料として位置づける。
- 「車両を追加」の自由記述が空、または異常あり項目のうち自由記述が空の
  まま送信されるケースのJS側バリデーション(送信ブロック)は、annual.htmlの
  検査業者名欄と同様に実装時に合わせて設計する(現状はCSSの
  `:placeholder-shown`による視覚的な警告表示のみで、送信自体を止める
  機構はない)。
- monthly/annual区分はweb-form-ui-design.mdの方針により自由記述欄中心の
  ままであり、本設計のような構造化→raw_text組み立ては不要(自由記述欄の
  内容をそのままraw_textとして送れば足りる)。daily区分のみが本設計の対象。
- 点検者名・実施日の「変更」リンクは編集UI自体が未実装(web-form-ui-design.md
  側の既知の残課題)であり、本設計はデフォルト値がそのまま使われる前提で
  テンプレートを定義した。編集UI実装時は`.value`相当の取得元を合わせて
  見直す必要がある。

最終更新: 2026-11-15 22:00 UTC(フェーズ240: 新規作成)
