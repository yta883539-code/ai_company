# 入力サンプル・期待出力対応表(初期ドラフト)

llm-quality-verification-plan.md「検証手順」次回候補(1)に対応し、他venture
(line-reservation-aiのconversation-samples-test-cases.md、course-set-pashaの
output-samples-validation.md)に相当する、本venture向けの入力メモサンプルと期待出力の
対応表を初めて整理する。本ドキュメントは机上の対応表であり、実LLM APIへの投入・結果の
機械チェックはオーナー承認後(実API接続時)に行う想定(llm-quality-verification-plan.md
「検証手順」3〜4節参照)。

## サンプルケース一覧

| ID | 入力メモ(想定) | 期待status | 期待する主な分岐・根拠 |
|---|---|---|---|
| N1 | 「東京ドーム、12/20昼公演、2枚当選。予算は交通込みで3万円くらい。物販は缶バッジ1種類欲しい。」 | generated | venue-master-draft.mdに「東京ドーム」が完全一致で存在 → `venue_matched: true`、`nearest_station_note`は水道橋駅/後楽園駅・徒歩5分前後を参照。単一公演のため`hashigo_check.applicable: false`。 |
| N2 | 「○○市民会館、来月の公演1枚。予算未定。」 | generated | venue-master-draft.mdに「○○市民会館」は未収録(主要会場マスタ対象外の地方ホール)→ `venue_matched: false`、`nearest_station_note`は一般的な調べ方の案内文言(具体的な駅名を推測で補わない)。予算未定のため`cost_estimate`の該当フィールドはnull、`note`に概算不可である旨を明記。 |
| N3 | 「京セラドーム大阪の昼公演(1枚)と、翌日の大阪城ホール公演(1枚)に参加予定。移動時間が心配。」 | generated | 2会場・連日参加の言及があるため`hashigo_check.applicable: true`。両会場ともvenue-master-draft.mdに完全一致で存在するため`venue_matched: true`を2件分生成する想定(itinerary_draftが会場単位でどう複数化されるかは現行スキーマでは単一会場前提のため、次回候補として要検討。本ケースは複数会場対応の設計ギャップを炙り出す目的で採用)。 |
| N4 | 「有明アリーナ、当日券ではなく当選済みチケット1枚。グッズ列は並ばない予定(`goods_line_intention: skip`)。」 | generated | goods-line-participation-input-field-design.md・llm-system-prompt-draft.md厳守事項4aの`skip`分岐により、`day_timetable`はグッズ列関連の行を省略し開場時刻基準の入場目安のみを示す(例: 「開場30分前目安で会場入り」のみの行で、「グッズ列目安到着」の行は追加しない)。参考として、`goods_line_intention`が`join`明記の場合は開場時刻より前到着検討の「グッズ列目安到着」行を1件追加、未記載の場合は早めの到着検討を促す両論併記の一言に留める(具体的な待ち時間分数・行列保証はいずれの分岐でも行わない)。 |
| E1(崩れ系) | 「ライブ行きたいんだけどどうしたらいい?」 | insufficient_input | 会場・日時・枚数等の必須項目が一切無い → 4出力フィールド全てnull、`missing_fields_request`は不明項目(会場名・日時・枚数等)を具体的に名指しして再送を促す文言である必要がある(推測で埋めない)。 |
| E2(崩れ系) | 「東京ドーム、当日の座席、まだ空いてますか?」 | out_of_scope | 空席確認の依頼 → README.mdが明示的に対応しないとする範囲(具体的な空席・空室の在庫確認)に該当 → `out_of_scope_message`のみ非null、4出力フィールドはnull。 |
| E3(崩れ系) | 「日本武道館のチケット、2枚分まとめて決済して予約しておいてほしい。」 | out_of_scope | 予約・決済代行の依頼 → 厳守事項1(予約・決済代行は一切行わない)に該当 → E2と同様の分岐。 |
| E4(崩れ系) | 「東京ドーム、12/20、1枚。チケット代は高かったけど、たしか5万円くらいだったと思う。」 | generated | 入力に金額の言及があるため`cost_estimate`に反映してよい範囲だが、「チケット代」自体は出力3種(交通/宿泊/物販)のいずれにも該当しないフィールドのため、本ケースは「入力に無い情報の推測禁止」(厳守事項7)との境界確認用(チケット代をtransport_yen等に誤って混入させないかを確認する目的)。 |

## 本対応表で明らかになった設計ギャップ(次回候補)

- N3: 複数会場(ハシゴ)ケースで`itinerary_draft`・`day_timetable`が会場ごとに複数必要になるのか、
  現行スキーマ(単一オブジェクト)のままで足りるのかは未確定。schema/output.schema.jsonの
  改訂が必要になる可能性がある(次回候補として記録)。
- N4: 解消済み。「グッズ列に並ぶか否か」は`goods_line_intention`(join/skip/未記載)として
  入力フォーマット・README.md「入力」節・llm-system-prompt-draft.md厳守事項4aに追加され、
  上表の期待出力(join/skip/未記載それぞれのday_timetable分岐)も確定した
  (goods-line-participation-input-field-design.md参照)。
- E4: 「チケット代」と出力3種(交通/宿泊/物販)のいずれにも該当しない入力金額が来た場合の
  取り扱い(無視するか、`cost_estimate.note`に参考情報として触れるか)は未定義。
  llm-system-prompt-draft.mdへの追記を検討する必要がある。

## 残る未確定事項

- 本対応表はいずれも机上のサンプルであり、実LLM APIへの投入・構造化出力の実際の安定性は
  未検証(llm-quality-verification-plan.md「検証手順」2〜4節、オーナー承認後のAPI接続時に
  実施予定)。
- N3・N4で発見した設計ギャップ(複数会場対応・グッズ列入力フィールド)への対応方針は
  本ドキュメントでは決定せず、次回以降の検討課題として残す。
- JSON Schemaバリデータ(validate_test_cases.py相当、llm-quality-verification-plan.md
  次回候補(2))は実装済み(README.mdフェーズ56、`validate_test_cases.py`)。N1・N2・
  N4(join/skip)・E1・E2・E3の期待出力を機械検証し7件パス。N3・E4は本ドキュメント記載の
  設計ギャップが未解消のため対象外のまま残る。
