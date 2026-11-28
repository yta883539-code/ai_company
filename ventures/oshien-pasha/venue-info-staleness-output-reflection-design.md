# last_verified_date・naming_rights_review_due の output.schema.json への反映方法(検討)

README.mdフェーズ168 次回候補(3)「`last_verified_date`・`naming_rights_review_due`
フィールドを含めたschema/output.schema.json側への反映方法の検討」に対応する。

## 背景

`schema/venue-master.json` の各会場レコードは `last_verified_date`(最終確認日)・
`naming_rights_review_due`(ネーミングライツ契約満了日、未確認の場合null)・
`naming_rights`(ネーミングライツ対象かどうか)・`verification_note`(確認内容の
履歴)を持つ(フェーズ15で定義、`_meta.field_notes`参照)。これらは現在、
naming-rights-review-due-reconfirmation-rule.md(フェーズ144)で定めた「いつ
運営側が再確認すべきか」の判断専用に使われており、`output.schema.json`(利用者への
出力構造)側には一切反映されていない。利用者はvenue_matched=trueの会場について、
その会場名・最寄り駅情報が「いつ確認された情報か」「ネーミングライツにより名称が
変わる可能性がある情報かどうか」を知る手段が無い。

## 検討した3案

1. **`last_verified_date`・`naming_rights_review_due`をそのまま出力に転記する案。**
   利用者にとって`naming_rights_review_due`は現在56件中大半がnull(契約満了日が
   WebSearchで裏取りできていないケースが多数、venue-alias-verification-and-naming-
   rights-risk.md参照)であり、null値をそのまま見せても情報価値が薄い。また契約
   満了日という運営管理目的の内部情報を利用者向け出力にそのまま出す必要性も薄く、
   却って「この日付までに何かが起きる」という誤解を招くリスクがある。不採用。
2. **何も反映しない案(現状維持)。** 運用上は再確認ルール(フェーズ144)で
   内部管理ができているため実害はないが、ネーミングライツにより名称が変更され
   うる会場(現在18件)について利用者が気づかず最新の正式名称と異なる案内を
   信じてしまうリスクへの対処が無いままになる。不採用。
3. **内部フィールドの生値ではなく、利用者にとって意味のある形に加工した注記
   フィールドを`itinerary_draft`配列の各要素に追加する案。** 以下の2条件に限り
   非null化する注記文字列とする。
   - (a) `venue_matched=true` かつ `naming_rights=true` の会場: 「この会場の
     名称はネーミングライツ契約により変更される場合があります。最新の正式名称は
     主催者・会場公式サイトでご確認ください。」という定型注記。
   - (b) `venue_matched=true` かつ `last_verified_date` が生成時点から一定期間
     (暫定180日、根拠は次節)以上前の会場: 「会場情報の確認から時間が経過して
     いるため、最新情報は主催者・会場公式サイトでご確認ください。」という定型注記。
   - (a)(b)両方に該当する場合は(a)の文面を優先する(ネーミングライツの注記の方が
     具体的で利用者の行動に直結するため)。venue_matched=falseの場合は既存の
     `nearest_station_note`の案内文言で十分であり本注記は不要(null)。

   **本フェーズの結論: 案3を採用する。**

## 180日しきい値の根拠(暫定)

naming-rights-review-due-reconfirmation-rule.md(フェーズ142)の「再確認リード
タイム基準」(満了日まで6ヶ月以内で運営側の本格再確認対象とする)とは目的が異なる
(運営側のWebSearch再確認トリガーではなく、利用者への情報鮮度の警告)。利用者向け
警告としては、最寄り駅・徒歩分数等の基本情報が180日(約6ヶ月)前のWebSearch確認を
前提にしている場合、路線工事・バス路線改編・会場周辺の再開発等の変化が起きていても
気づけないリスクを踏まえ、暫定的に180日を閾値とする。会場マスタ56件の
`last_verified_date`を実際に確認したところ、本フェーズ時点(2026-11-28)で
180日以上前の確認となっているレコードは0件(最も古いものでも2026年内の日付)で
あり、現時点でこの閾値を適用しても(b)に該当する会場は無い。したがって本フェーズ
時点ではこの閾値の採用による既存の利用者向け出力内容への影響は無く、閾値自体の
妥当性(180日が長すぎる・短すぎる)は今後の運用実績(実際の再確認間隔の分布)を
見て見直す前提とする。

## 実装方針(次回以降)

- `output.schema.json`の`itinerary_draft.items.properties`に
  `venue_info_caution_note`(`type: ["string", "null"]`)を追加し、`required`
  配列にも加える(既存フィールドと同様、非該当時は明示的にnullを要求する既存の
  分岐方針を踏襲)。
- 上記フィールド追加は`validate_test_cases.py`のTEST_CASES(input-output-sample-
  mapping.md記載の既存フィクスチャ)全件に新フィールドを追記する作業を伴うため、
  schema改訂とフィクスチャ追記は同一フェーズ内でセットで行う(スキーマだけ先行
  改訂するとvalidate_test_cases.pyが既存フィクスチャ側の`required`違反で
  失敗するため)。
- `prototype/venue_matcher.py`(またはその後処理を担う
  `itinerary_draft_postprocessor.py`)側に、venue-master.jsonの`naming_rights`・
  `last_verified_date`を参照して上記注記文字列を組み立てるロジックを追加する。
  現在`venue_matcher.py`はマッチング(名寄せ)のみを担うため、注記生成を
  マッチャー自体に持たせるか後処理側に分離するかは実装着手時に
  venue-matcher-llm-postprocessing-integration-design.md(フェーズ100台)の
  既存の責務分担方針と整合させる形で決める。

本フェーズは検討・結論(案3採用)・180日しきい値の暫定根拠の明文化までとし、
schema/output.schema.json・validate_test_cases.py・prototype/venue_matcher.py等の
実改修は次回以降に持ち越す(1フェーズでの作業量を抑える既存方針を踏襲)。
schema/venue-master.json・既存テスト・schema検証は本フェーズでは変更していない
ため今回は再実行不要。実LLM/Stripe/GCP/Firestore接続・支払い・アカウント作成・
外部公開・送信は一切行っていない。承認が必要なアクションは今回発生していないため
pending-approval.mdへの追記なし。

## 次回候補

1. 上記実装方針に沿って`output.schema.json`に`venue_info_caution_note`を追加し、
   `validate_test_cases.py`の既存フィクスチャ(N1・N2・N3・N4 join/skip・E1〜E4)
   全件に新フィールドを追記、`venue_matcher.py`またはpostprocessor側への
   注記生成ロジック追加に着手する。
2. 混同注意リストの他候補(例: 他地域の同一地名・改称/分割施設群)をWebSearchで
   探索・会場マスタへ追加。
3. 宮崎県体育館・宮崎市総合体育館・大分県立総合体育館の徒歩分数・最寄り駅は
   本実行環境のネットワーク制約下では確証が得られないため、オーナーのネットワーク
   許可拡大が得られた場合に再試行。
4. 承認待ち事項(launch-readiness-checklist.md参照)がオーナーから承認された場合は
   その着手を最優先。
