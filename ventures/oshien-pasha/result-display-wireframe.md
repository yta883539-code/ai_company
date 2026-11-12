# 生成結果表示部分(4出力カード)のUI/UXワイヤーフレーム(フェーズ110)

input-form-ui-ux-design.md(フェーズ109)の次回候補(1)「生成結果表示部分(4出力カード)の
UI/UXワイヤーフレーム」に対応する。result-display-page-generation-request-design.md
(フェーズ102)が定義した`receive_generation_request()`のレスポンス
(`schema/output.schema.json`の`status`分岐、4出力: itinerary_draft/day_timetable/
cost_estimate/hashigo_check)を、画面上にどう配置するかをテキストワイヤーフレームとして
設計する。他venture同様、実装(HTML/CSS/JS)・実LLM呼び出し・実デプロイは行わず、テキスト
ベースの設計検討に留める。

## 1. 画面遷移上の位置づけ

input-form-ui-ux-design.mdで確定した自由記述フォーム(「当選情報メモ」1本)から送信した後、
同一ページ内で以下の3状態を切り替える構成とする(別ページへの遷移は行わない。モバイルで
「送信→結果まで」の往復を減らすため、course-set-pasha・event-komiguai-pashaの一部venture
が採用する「同一ページ内で入力欄を結果表示に差し替える」方式を踏襲)。

1. 入力中/未送信(フォームのみ表示)
2. 送信中(ローディング表示、フォームは非活性化。input-form-ui-ux-design.md既定の二重送信
   防止と対応)
3. 結果表示(`status`の値により以下いずれかに分岐)
   - `status=generated` → 4出力カードを表示(本ドキュメントの主題)
   - `status=out_of_scope` → `out_of_scope_message`を1枚のメッセージカードとして表示
   - `status=insufficient_input` → `missing_fields_request`を1枚のメッセージカードとして
     表示し、フォームへの「追記して再送信」ボタンを添える(フォーム自体は消さず、入力内容を
     保持したまま再表示する方針。入力し直しの手間を避けるため)

## 2. `status=generated`時の4出力カード構成

会場単位配列(itinerary_draft・day_timetable)と単一オブジェクト(cost_estimate・
hashigo_check)が混在するため(output.schema.json参照)、画面上は「会場ごとのまとまり」を
上位、「全体共通の2カード」を下位に置く2段構成とする。

```
┌───────────────────────────┐
│ ✓ 遠征プランができました           │ ← 完了見出し(H2)、チェックマークアイコン
├───────────────────────────┤
│ 【会場1: ○○ホール】              │ ← venue_name_input を見出しに表示
│                             │
│ ① 遠征プラン下書き               │ ← itinerary_draft[0]
│  最寄り駅: △△駅 徒歩10分           │   venue_matched=trueなら nearest_station_note
│  宿泊候補エリア: △△駅周辺/□□駅周辺    │   lodging_area_candidates(箇条書き)
│  交通メモ: ...                  │   transport_note
│  ※venue_matched=falseの場合は「会場名を │ ← falseのときの代替文言
│    確認できなかったため一般的な       │
│    調べ方を案内します」+ 一般的な案内文  │
│                             │
│ ② 当日タイムテーブル草案            │ ← day_timetable[0](venue_name_inputで対応)
│  10:00 現地到着目安              │   timetable配列を time_label/action の
│  11:00 開場                    │   2列リストで縦に並べる
│  11:30 グッズ列開始(目安)          │
│  ...                         │
├───────────────────────────┤
│ 【会場2: △△アリーナ】             │ ← 会場が複数ある場合は①②を会場ごとに
│  (①②をもう1セット)              │   繰り返す(multi-venue-hashigo-schema-
│                             │   design.md、常に配列として返るため
│                             │   単一会場でも「会場1」見出しは付ける)
├───────────────────────────┤
│ ③ 費用内訳見積り                 │ ← cost_estimate(会場をまたいだ全体の
│  交通費: 約◯◯円                 │   合算見積りのため、会場セクションの外
│  宿泊費: 約◯◯円                 │   〈下位〉に1カードとして配置)
│  物販予算: 約◯◯円                │   transport_yen/lodging_yen/goods_yenが
│  ※実際の料金は目的地・時期により        │   nullの項目は「—」表示(非表示にはしない。
│    変動します                   │   「見積りに含まれていない」ことを明示
│                             │   するため)
│  note: ...                   │   note(常に表示)
├───────────────────────────┤
│ ④ ハシゴ無理チェック               │ ← hashigo_check
│                             │
│ [applicable=falseの場合]        │
│  今回は複数公演の「ハシゴ」の           │ ← 複数公演の言及が無い入力での既定表示
│  言及が見つかりませんでした            │   (リスクが無い旨の誤った安心感を与え
│                             │   ないよう、「チェック対象外」である旨を
│                             │   明示する文言とする)
│                             │
│ [applicable=trueの場合]         │
│  リスク: [低/中/高の色付きバッジ]       │ ← risk_level(low=緑/medium=黄/high=赤)
│  note: ...                   │   note
├───────────────────────────┤
│ [ もう一度相談する ]              │ ← 新規入力に戻るボタン(フォームを
│                             │   空にして状態1へ)
└───────────────────────────┘
```

## 3. 表示方針の確定事項

- 4出力カードは縦一列(モバイル1カラム、landing-page-wireframe.mdと同じ基本方針)で、
  ①②③④の番号をLPの訴求(landing-page-wireframe.md「1入力→4出力」の画像)と一致させる
  ことで、LPで見た内容と結果画面の対応関係を利用者が迷わず追えるようにする。
- `venue_matched=false`・`cost_estimate`の各`*_yen`が`null`・`hashigo_check.applicable=
  false`のいずれも、「情報が無いので非表示にする」のではなく「この情報は確認できなかった/
  対象外だった」ことを明示する文言で表示する方針を統一する。output.schema.jsonの
  各フィールドが`null`を許容している設計意図(断定を避ける、README.mdの「実際の予約・決済・
  空席確認は行わない」方針)を画面表示でも一貫させるため。
- risk_levelの色付きバッジ(低=緑/中=黄/高=赤)は、tone-and-manner-guideline.mdが定める
  「不安を煽らない」トーンとのバランスを取るため、medium/highであっても断定的な警告色の
  強調(点滅・大きな赤背景全面等)は用いず、小さめのバッジ表示に留める方針とする(具体的な
  配色コード自体は実装フェーズで検討、本フェーズはテキストワイヤーフレームのみ)。
- 会場が1件のみの入力でも「【会場1: ○○ホール】」の見出しを常に付ける(multi-venue-
  hashigo-schema-design.mdが「単一/複数で型を変えない」方針を取っているため、表示側も
  単一/複数で見出しの出し方を変えない)。

## 4. 残課題

- (対応済み・フェーズ111)LLM呼び出し失敗時(タイムアウト・Structured Outputs不整合等)の
  エラー表示文言・分岐方針はllm-generation-failure-handling-design.mdで確定した
  (`status_code=502`時に「生成中に時間がかかってしまい、結果を表示できませんでした。
  少し時間をおいてから、もう一度お試しください。」+「もう一度試す」ボタン、入力内容は
  保持したまま再送信)。本ワイヤーフレームのASCII図への反映自体は次回候補として残す。
- risk_levelバッジの具体的な配色コード・アイコンの確定(実装フェーズ)。
- `landing-page/index.html`と同様の非公開試作HTML化(フェーズ109次回候補(2)、本フェーズは
  テキストワイヤーフレームのみで止めた)。
- 実LLM呼び出し・実際のHTML/JS実装・外部サービスへの接続は、本フェーズでも行っていない
  (設計検討のみ)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は
  本フェーズでは発生していないためpending-approval.mdへの新規追記は不要(既存の承認待ち
  事項〈Stripe/GCPアカウント開設等〉の範囲内で扱う)。

最終更新: 2026-11-11 01:00 UTC(フェーズ110: 生成結果表示部分〈4出力カード〉の
UI/UXワイヤーフレームを新規作成。会場単位配列〈itinerary_draft/day_timetable〉を会場ごとの
まとまりとして上位に、全体共通2カード〈cost_estimate/hashigo_check〉を下位に配置する2段構成、
null値・applicable=falseの明示表示方針を確定。コード変更なし)
