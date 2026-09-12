# 厳守事項9a「メニュー内容/料金表」の`topic`追加可否決定(2026-09-12 16:00 UTC)

conversation-samples-test-cases.mdのE19「補足」・フェーズ続き218が「次回以降の課題」として
残していた、`faq_segments`の`topic`列挙値(access/parking/payment/hours/other)に
メニュー・料金表専用の項目(menu/pricing)を追加すべきかどうかを検討する。

## 背景

- llm-system-prompt-draft.md厳守事項9aの説明文冒頭は「メニュー内容/料金表」も店舗が
  事前登録した静的情報の例として挙げているが、実装(`faq_segments`のtopic列挙値・
  faq-response-templates.mdのテンプレート)には対応する項目が存在せず、常に`topic: "other"`
  と同じ扱いで6にエスカレーションしていた(E19参照)。
- E19の「補足」では、追加を検討する際の懸念点として「店舗にとって価格変更のたびにFAQ情報欄を
  更新する運用負荷との兼ね合い」を挙げていた。

## 検討: 追加専用の登録欄は必要か

owner-settings-wireframe.md「2. メニュー設定ページ」を確認したところ、店舗は予約受付の
大前提として、メニュー名・料金(任意表示)・所要時間を最初から登録・維持している
(所要時間は予約枠の自動ブロック計算(`resolve_menu_duration()`、
prototype/cloud_function_process_event.py)に使う必須データであり、料金変更時にはメニュー
自体の編集操作で更新される)。

つまり、access/parking/payment/hoursのようにFAQ回答専用に別枠で入力してもらう項目とは異なり、
メニュー・料金は「予約フローのために店舗が既に維持している一次データ」がそのまま存在する。
E19「補足」が懸念していた「FAQ情報欄を別途更新する運用負荷」は、既存のメニュー設定データを
再利用する限り発生しない(店主がメニュー編集画面で料金を直せば、予約フロー・FAQ回答の両方に
同時に反映される)。

## 決定

`faq_segments.topic`に`"menu"`を追加する(`"pricing"`は別トピックとして分けず、メニュー名と
料金を1つのFAQ項目にまとめて扱う。実際の店舗登録データも「メニュー名+料金」がセットで
1レコードのため、分割すると店舗側の入力構造と合わなくなるため)。

回答テンプレートの設計方針は既存の9a項目(登録値をそのまま組み立てるのみ、AIによる言い換え・
推測を行わない)を踏襲する:

- 各メニュー項目の名称をそのまま列挙する。
- 料金は、当該メニュー項目が「任意表示」設定で表示オンになっている場合のみ、登録された金額を
  そのまま添える。表示オフの項目は名称のみを列挙し、金額を推測で補わない・非表示である旨も
  特に説明しない(parking・payment・hoursの既存テンプレートで「未登録項目は言及自体をしない」
  としている方針と同じ)。
- 所要時間はFAQ回答には含めない。所要時間は予約枠計算専用の内部値であり、
  「メニュー内容/料金表」という質問の対象(店舗が案内したい情報)には含まれないため。
- 登録済みメニューが1件も無い店舗(`store_faq_info`に`menu`キーが無い、またはリストが空)は、
  他トピックと同じく安全側で厳守事項6のエスカレーションに倒す。

## 反映箇所

- `prototype/engine.py`: `format_faq_menu_message()`を新設。
- `prototype/cloud_function_process_event.py`: `_render_faq_segment()`に`menu`トピックの
  分岐を追加。
- `schema/booking_output.schema.json`: `faq_segments[].topic`のenumに`"menu"`を追加。
- `prototype/test_cloud_function_process_event.py` / `prototype/test_engine.py`:
  登録済みメニュー(料金表示オン/オフ混在)・未登録の両パターンをテストで固定
  (venture全体776件、うち本フェーズで6件追加)。
- `llm-system-prompt-draft.md`: 厳守事項9aの説明文・スキーマのtopic列挙値・
  faq-response-templates.mdへの参照を更新(「メニュー内容/料金表は常にエスカレーション」という
  従来の注記を「`topic: "menu"`として自動回答対象」に修正)。
- `faq-response-templates.md`: 「メニュー内容・料金表(menu)」節を新設。
- `conversation-samples-test-cases.md` / `schema/validate_test_cases.py`: E20(メニュー・
  料金表FAQ)を新規追加。

## 未解決のまま残す課題

- 所要時間や「◯◯コースの内容」のような、名称・料金以外のメニュー詳細(施術内容の説明文等)を
  尋ねられた場合の扱いは本決定のスコープ外。owner-settings-wireframe.mdのメニュー設定ページに
  詳細説明欄が無いため、現状は登録値が存在せず`other`相当のエスカレーションに自然に落ちる
  (対応する登録欄が無い限りコード変更は不要)。
- メニュー件数が多い店舗(10件以上等)で全件列挙が長文になりすぎる場合の省略・要約要否は
  未検討。実際の店舗ヒアリング(customer-interview-design.md)でメニュー件数の実態が
  見えてから再検討する。
