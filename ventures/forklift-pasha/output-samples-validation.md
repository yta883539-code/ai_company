# 期待JSON出力サンプルの机上検証(2026-10-03 05:00 UTC)

## 位置づけ

kura-pasha/course-set-pasha/aircon-pashaのoutput-samples-validation.mdと同じ位置づけの
文書。pricing-plan.md・llm-api-cost-estimate.mdの「次のステップ候補」として挙げられていた
fixtureファイル(テストケース)の作成(フェーズ5申し送り)に対応し、
schema/validate_test_cases.py(本フェーズで新規作成、外部ライブラリ非依存のpure stdlib
簡易バリデータ)で検証した期待JSON出力サンプルの一覧・結果をまとめる。本ドキュメント
作成・検証スクリプトの実行はAPIキー取得・課金を伴わない机上作業であり承認不要。実際の
LLM API呼び出しはこれまで通りオーナー承認待ちのまま未実施(pending-approval.md参照)。

## 検証方法

kura-pasha等と同じ設計方針を踏襲し、schema/output.schema.jsonのサブセット
(type/enum/required/additionalProperties)を解釈するバリデータと、スキーマ単体では
表現できないstatus⇔各フィールドのnull/非nullの依存関係(厳守事項2・3・5、
mvp-flow-draft.mdのtype=daily時reminder_notice常時null等)を個別にチェックする
`validate_cross_field_rules()`を用いる。

## サンプルケース(11件。正常系8件+ネガティブ3件)

| ケースID | status | 想定シナリオ |
|---|---|---|
| G1_daily | generated | 基本ケース。type=daily(始業前点検)、reminder_noticeはnull |
| G2_monthly_no_reminder | generated | type=monthly、次回期限が近くないためreminder_noticeがnull |
| G3_monthly_with_reminder | generated | type=monthly、次回期限が7日以内に迫りreminder_noticeが非null |
| G4_annual_with_company | generated | type=annual、検査業者名(inspector_company)が記載されている厳守事項3準拠ケース |
| OOS1_unrelated_request | out_of_scope | 点検記録整形・期限管理以外の要求への不応答ケース(厳守事項6) |
| II1_no_vehicle_id | insufficient_input | 車両番号の記載が無く再送を促すケース |
| II2_no_type | insufficient_input | 点検種別の記載が無く再送を促すケース(厳守事項2) |
| II3_annual_no_company | insufficient_input | annualなのに検査業者名が無く再送を促すケース(厳守事項3) |
| NEG1_annual_missing_company_is_detected | (エラー検出確認) | ネガティブテスト。type=annualなのにinspector_companyがnull(厳守事項3違反)が検出されることの確認用 |
| NEG2_daily_with_reminder_is_detected | (エラー検出確認) | ネガティブテスト。type=dailyなのにreminder_noticeが非null(mvp-flow-draft.md違反)が検出されることの確認用 |
| NEG3_out_of_scope_with_record_is_detected | (エラー検出確認) | ネガティブテスト。status=out_of_scopeなのにinspection_recordが非null(排他性違反)が検出されることの確認用 |

## 結果(2026-10-03 05:00 UTC作成時点)

```
合計 11 件中 11 件パス、0 件失敗
```

`python3 schema/validate_test_cases.py`で実行内容を確認できる。G1〜G4・OOS1・II1〜II3の
8件が違反なくパスし、NEG1〜NEG3の3件は意図通りエラーが検出されることを確認した。

G2とG3の対比により、月次自主検査・特定自主検査の次回実施期限(前回実施日+1ヶ月/+1年)が
7日以内に迫っているかどうかでreminder_noticeの非null判定が機械的にチェック可能であること
を確認した。G1とG2/G3/G4の対比により、type=dailyのみreminder_noticeが常にnullであるという
mvp-flow-draft.mdのルールも併せて確認した。

## 次回候補

- 実LLM(Claude API)での動作検証はAPIキー取得がオーナー承認待ちのため未着手。
- llm-quality-verification-plan.md・llm-quality-verification-results-template.md
  相当の文書(他venture同様)はまだ未作成。
- annual区分での検査業者名以外の必須項目(次回実施期限の年次計算の境界値ケース等)の
  テストケース追加。
