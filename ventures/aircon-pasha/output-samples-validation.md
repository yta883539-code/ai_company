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

## サンプルケース(18件。2026-08-21 14:00 UTC改訂でG4・CI1〜CI3を追加、2026-09-12 03:00 UTC改訂でCO1〜CO3・NEG1を追加、2026-09-13 19:00 UTC改訂でG5・G6を追加、2026-09-14 15:00 UTC追加のG7〈本表への反映漏れを2026-09-18 17:00 UTC改訂で解消〉、2026-09-18 17:00 UTC改訂でG8・NEG2を追加)

| ケースID | status | 想定シナリオ |
|---|---|---|
| G1_basic | generated | 基本ケース。入力メモに次回推奨時期の記載あり(is_estimate=false) |
| G2_estimate_next_date | generated | 入力メモに次回推奨時期の記載が無く、一般的な目安で代替(is_estimate=true、デフォルト「1〜2年に1回」、history_rows[0].next_recommended_dateはnull) |
| G3_model_and_date_unextractable | generated | 機種系統・号数、施工日を入力メモから抽出できず、history_rows[0]のwork_date/model_type_and_capacityがnullになるケース(is_estimate=true、デフォルト「1〜2年に1回」) |
| G4_multiple_units_same_visit | generated | 同一訪問先(自宅)でリビング・寝室の2台を同時に分解洗浄し、history_rowsが要素数2の配列になるケース(2026-08-21 14:00 UTC追加、市場調査で複数台セット割引が業界標準と判明したことを受けたもの) |
| G5_estimate_high_usage_annual | generated | 入力メモに次回推奨時期の記載は無いが、ほぼ毎日稼働に近い高頻度使用の言及があるため、厳守事項4の粒度分岐で「年1回」を目安として採用するケース(2026-09-13 19:00 UTC追加) |
| G6_estimate_pet_smoking_semiannual | generated | 入力メモに次回推奨時期の記載は無いが、ペットを飼育している環境の言及があるため、厳守事項4の粒度分岐で「年2回」を目安として採用するケース(2026-09-13 19:00 UTC追加) |
| G7_management_company_recipient | generated | recipient=management_company(管理会社宛)のケース。厳守事項9の定型ボイラープレート(費用負担区分の判定は行っていない旨)を文末に付す(2026-09-14 15:00 UTC追加、フェーズ217。本表への反映は2026-09-18 17:00 UTC改訂で実施) |
| G8_busy_season_grumble_not_cancellation | generated | 入力メモ冒頭に「今月は依頼が多すぎて全然回らない」という繁忙期の愚痴が含まれるが、契約継続・解約のいずれにも言及しない雑談の域を出ない表現であるため、厳守事項6a(iii)により解約意図とは混同せず通常どおり作業完了報告を生成するケース(subscription_procedure_noticeはNoneのまま)。llm-system-prompt-draft.md「次の課題」が既知の限界として残していた6a境界の具体例を固定するサンプル(2026-09-18 17:00 UTC追加) |
| OOS1_reservation_question | out_of_scope | 会員管理・予約受付・決済に関する質問への不応答ケース(厳守事項6) |
| II1_no_work_content | insufficient_input | 分解洗浄を実施したこと自体が読み取れず再送を促すケース(厳守事項7) |
| CI1_cancellation_intent_clear / CI2_downgrade_intent / CI3_cancellation_unclear | cancellation_intent / downgrade_intent / cancellation_unclear | 厳守事項6a(解約意図検知)関連ケース(フェーズ91で追加済み、本ドキュメントへの反映漏れを2026-08-21 14:00 UTC改訂で解消) |
| CO1_checkout_intent / CO2_pricing_inquiry / CO3_checkout_intent_unclear | checkout_intent / pricing_inquiry / checkout_intent_unclear | 厳守事項6b(有料プラン開始意図検知)関連ケース(2026-09-12 03:00 UTC追加) |
| NEG1_checkout_url_mismatch_is_detected | checkout_intent | ネガティブテスト。includes_checkout_url不一致(厳守事項6b違反)が検出されることの確認用 |
| NEG2_management_company_missing_boilerplate_is_detected | generated | ネガティブテスト。recipient=management_companyなのに厳守事項9の定型ボイラープレートが本文に含まれていない(厳守事項9違反)が検出されることの確認用(2026-09-14 15:00 UTC追加、フェーズ217。本表への反映は2026-09-18 17:00 UTC改訂で実施) |

## 結果(2026-09-18 17:00 UTC改訂時点)

```
合計 18 件中 18 件パス、0 件失敗
```

G1〜G8・OOS1・II1・CI1〜CI3・CO1〜CO3の16件が違反なくパスし、NEG1・NEG2の2件は
意図通りエラーが検出されることを確認した(`python3 schema/validate_test_cases.py`で
実行内容を確認できる)。以下は2026-08-09作成時点(15件)の記述。
`next_recommended_date_is_estimate`と`history_rows[*].next_recommended_date`の整合性の
いずれの違反もなくパスした。特にG2(is_estimate=true・next_recommended_dateはnull許容)と
G1(is_estimate=false・next_recommended_dateは非null必須)の対比により、
schema/output.schema.jsonのdescriptionに記載していた整合性ルールが機械的にチェック
可能であることを確認した。G4では2要素の配列それぞれに対して整合性チェックが個別に
適用されることも確認した(schema/validate_test_cases.pyのitems対応・配列ループ処理)。
G5・G6(2026-09-13 19:00 UTC追加)では、厳守事項4のデフォルト目安の粒度分岐(使用頻度が
高い場合は「年1回」、ペット・喫煙環境がある場合は「年2回」)についても、G2・G3が既に
カバーしていた基本の「1〜2年に1回」と同様にprototype/post_generation_checks.pyの
打消し文言チェック(ESTIMATE_DISCLAIMER_KEYWORDS)を通過する形でサンプルを作成できる
ことを確認し、粒度分岐3パターン(1〜2年に1回/年1回/年2回)すべてのサンプルが揃った。

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
- G8(2026-09-18 17:00 UTC追加)は、llm-system-prompt-draft.md「次の課題」が既知の限界
  として残していた厳守事項6a(iii)(契約継続に触れない雑談・愚痴)と6a(解約意図検知)の
  混同防止について、具体的な入力メモ・期待出力の組み合わせを固定したもの。あくまで
  「この入出力ペアなら整合的である」ことのスキーマレベル確認に留まり、実LLMが繁忙期の
  愚痴を実際に解約意図と誤検知しないかどうかは、他の6a/6b境界の検証と同様に実LLM接続後
  (オーナー承認待ち)の検証課題として引き続き残る。
