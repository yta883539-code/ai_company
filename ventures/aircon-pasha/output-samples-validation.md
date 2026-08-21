# 期待JSON出力サンプルの机上検証(2026-08-09 16:00 UTC)

## 位置づけ

README.md「次にやること(候補)」1点目
「期待JSON出力サンプル(status別)の作成と机上バリデーション
(course-set-pasha/output-samples-validation.md相当)。特にcare_guideの
next_recommended_date_is_estimateとhistory_row.next_recommended_dateの整合性を
確認するサンプルを含める」に対応。

course-set-pasha・line-reservation-aiと同じ設計方針を踏襲し、
schema/validate_test_cases.py を新規作成した。

## 検証方法

course-set-pasha/schema/validate_test_cases.pyと同じ設計。

- 外部ライブラリ非依存(pure stdlib)の簡易バリデータで、output.schema.jsonのサブセット
  (type/enum/required/additionalProperties)を解釈してフィールド単位の型・必須項目違反を
  検出する。
- スキーマ単体では表現できない`status`⇔null/非nullの依存関係(厳守事項6・7に対応する分岐)、
  および`completion_report.mentions_refrigerant_or_electrical`が必ずboolean(null不可)で
  あること、`care_guide.next_recommended_date_is_estimate`と`history_row.next_recommended_date`
  の整合性(is_estimate=falseならnext_recommended_dateはnull不可)は
  `validate_cross_field_rules()`で個別にチェックする。

## サンプルケース(9件、2026-08-21 14:00 UTC改訂でG4・CI1〜CI3を追加)

| ケースID | status | 想定シナリオ |
|---|---|---|
| G1_basic | generated | 基本ケース。入力メモに次回推奨時期の記載あり(is_estimate=false) |
| G2_estimate_next_date | generated | 入力メモに次回推奨時期の記載が無く、一般的な目安で代替(is_estimate=true、history_rows[0].next_recommended_dateはnull) |
| G3_model_and_date_unextractable | generated | 機種系統・号数、施工日を入力メモから抽出できず、history_rows[0]のwork_date/model_type_and_capacityがnullになるケース |
| G4_multiple_units_same_visit | generated | 同一訪問先(自宅)でリビング・寝室の2台を同時に分解洗浄し、history_rowsが要素数2の配列になるケース(2026-08-21 14:00 UTC追加、市場調査で複数台セット割引が業界標準と判明したことを受けたもの) |
| OOS1_reservation_question | out_of_scope | 会員管理・予約受付・決済に関する質問への不応答ケース(厳守事項6) |
| II1_no_work_content | insufficient_input | 分解洗浄を実施したこと自体が読み取れず再送を促すケース(厳守事項7) |
| CI1_cancellation_intent_clear / CI2_downgrade_intent / CI3_cancellation_unclear | cancellation_intent / downgrade_intent / cancellation_unclear | 厳守事項6a(解約意図検知)関連ケース(フェーズ91で追加済み、本ドキュメントへの反映漏れを本改訂で解消) |

## 結果

```
合計 9 件中 9 件パス、0 件失敗
```

9件すべてが、型・必須項目・`status`に応じたnull/非null依存関係・
`next_recommended_date_is_estimate`と`history_rows[*].next_recommended_date`の整合性の
いずれの違反もなくパスした。特にG2(is_estimate=true・next_recommended_dateはnull許容)と
G1(is_estimate=false・next_recommended_dateは非null必須)の対比により、
schema/output.schema.jsonのdescriptionに記載していた整合性ルールが機械的にチェック
可能であることを確認した。G4では2要素の配列それぞれに対して整合性チェックが個別に
適用されることも確認した(schema/validate_test_cases.pyのitems対応・配列ループ処理)。

## 残る未検証事項

- 上記はあくまで机上検証であり、実際にLLMがこの形式で安定して構造化出力を生成できるかは
  未確認(実LLM呼び出しはAPIキー取得・課金がオーナー承認待ちのため、他ventureと同様に
  実装フェーズ・API接続時の検証に持ち越し)。
- G3のように「抽出できない項目をnullとして扱う」ケースは、LLMが実際に「わからないので
  nullを返す」のか「それらしい値を推測して埋めてしまう」のかは机上検証では確認できない
  (llm-system-prompt-draft.mdの厳守事項3として明記済みだが、プロンプト遵守率の検証は
  実LLM接続後の課題として残る)。
- completion_report.mentions_refrigerant_or_electricalがtrue/false双方で正しく分岐する
  保証(冷媒補充等の実施記述を淡々と書くだけならfalse、専門的当否評価に踏み込めばtrue)は、
  システムプロンプトの厳守事項1の遵守にかかっており、こちらも実LLM検証が必要。
- (解消済み 2026-08-21 14:00 UTC: 1メモで複数台を同時に扱うケースについてWebSearchで調査した
  結果〈market-research.md参照〉、複数台セット割引が業界標準であり無視できない頻度で
  発生すると判明したため、history_rowをhistory_rows〈配列〉に変更し、G4_multiple_units_
  same_visitケースを追加した。実LLMが複数台メモを正しく複数要素に分割生成できるかは
  引き続き実LLM接続後の検証課題として残る)
