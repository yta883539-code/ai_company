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

## フェーズ26追記(2026-10-04 02:00 UTC): 次回実施期限の年次・月次計算ロジックの実装と境界値テスト

本フェーズまで、G2/G3フィクスチャの`reminder_notice`は次回実施期限を人手で計算した固定値に
すぎず、期限算出ロジック自体は未実装だった。`prototype/due_date_logic.py`を新規実装し、
`compute_next_due_date(inspection_type, last_date)`(monthly: +1ヶ月、annual: +1年、daily:
Noneを返す)と`should_remind(inspection_type, last_date, today)`(期限7日前以内〈境界値を
含む〉または期限超過でTrue、llm-system-prompt-draft.md 25行目の「期限が近い(7日前以内)」に
対応)を用意した。`prototype/test_due_date_logic.py`(15件、全件パス)で以下の境界値を検証した。

- 月末繰り上げ: 1/31+1ヶ月が存在しない日付(2/31等)になる場合にその月の末日へ丸められること
  (非うるう年2/28・うるう年2/29の両方)。
- うるう日: 2024-02-29(annual)+1年が非うるう年の2025年では2/28に丸められること。
- 7日しきい値の境界: 期限7日前はリマインド対象、8日前は対象外、期限当日・超過後も対象で
  あることをannual・monthlyの両方で確認。

## フェーズ27追記(2026-10-04 03:00 UTC): フィクスチャとdue_date_logic.pyの計算結果の突き合わせ

フェーズ26の「次回候補」1点目に従い、`schema/validate_test_cases.py`のG2/G3/G4フィクスチャの
`body`・`reminder_notice`に埋め込まれていた次回実施期限(いずれもdue_date_logic.py実装前に
人手で計算した固定値)を、`compute_next_due_date()`の計算結果と突き合わせる統合テスト
`prototype/test_due_date_integration.py`(4件、全件パス)を新規作成した。

- G2(monthly、2026-10-01実施)→`compute_next_due_date`の結果が2026-11-01と一致。
- G3(monthly、2025-11-05実施)→結果が2025-12-05と一致し、`reminder_notice`本文中の
  日付文字列(2025-12-05)が計算結果と一致することも確認。
- G4(annual、2026-09-15実施)→結果が2027-09-15と一致。

これにより、フィクスチャ作成(フェーズ3)時点の人手計算とdue_date_logic.py実装(フェーズ26)
時点の計算ロジックが食い違っていないことを機械的に確認できた(今回は食い違いなし)。なお
`should_remind()`(リマインド要否の判定)自体はフィクスチャに「今日」の日付情報が含まれて
いないため本テストの対象外とし、次回実施期限の値そのものの整合確認に限定した。

## フェーズ28追記(2026-10-04 04:00 UTC): should_remind()の境界値統合テスト追加

フェーズ27の次回候補に従い、`should_remind()`(リマインド要否判定)を検証する統合テスト
`prototype/test_should_remind_integration.py`(9件、全件パス)を新規作成した。G2/G3/G4
フィクスチャの`reminder_notice`はどの「今日」の日付で生成されたかの情報を持たないため、
それらのreminder_notice有無とは直接比較せず、代わりにフェーズ27で突き合わせ済みの
next_due_date(G2: 2026-11-01・G3: 2025-12-05・G4: 2027-09-15)を起点に、「今日」の日付を
明示した新規境界値ケースを用意した。

- G2(monthly)・G3(monthly)・G4(annual)いずれも、due-today=7日(境界)で`should_remind`が
  True、8日でFalseになることを確認(REMINDER_THRESHOLD_DAYS=7日の境界が月次・年次の両方で
  正しく機能することを確認)。
- G2でdue当日・due翌日(1日超過)もTrueになることを確認(期限超過後もリマインド対象を
  継続するフェーズ26の設計判断を再確認)。
- G1(daily)はtoday=last_dateでも`should_remind`がFalseになることを確認(次回期限の概念が
  無いdailyは常にリマインド対象外)。

last_dateはG2/G3/G4フィクスチャと同じ値を使ったため、next_due_date算出からリマインド要否
判定までの一連の流れを通して確認する統合テストになっている。
`python3 prototype/test_should_remind_integration.py`(9件、全件パス)・回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(11件、変化なし)・
`python3 prototype/test_due_date_integration.py`(4件)・`python3 schema/validate_test_cases.py`
(11件)をいずれも再実行しパスを確認した。

## 次回候補

- 実LLM(Claude API)での動作検証はAPIキー取得がオーナー承認待ちのため未着手。
- llm-quality-verification-plan.md・llm-quality-verification-results-template.md
  相当の文書(他venture同様)はまだ未作成。
- 名簿PDF本文に依存しない間接チャネル探索の再検討(フェーズ24・26から持ち越し)。
