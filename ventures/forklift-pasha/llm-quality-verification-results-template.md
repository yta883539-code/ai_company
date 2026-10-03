# 実LLM接続後の検証結果記録テンプレート(フェーズ9・2026-10-03 09:00 UTC)

## 位置づけ

llm-quality-verification-plan.md「記録先」節で「実LLM検証着手の承認が下りた時点で
llm-quality-verification-results-template.mdを別ファイルとして切り出す」としていたが、
kura-pasha/aircon-pasha/course-set-pashaはAPIキー取得・課金を伴わない机上作業として
先行して本ファイル相当を用意していることを確認した。本ventureも同じ方針に揃え、承認を
待たずに空の記録表だけを先に用意しておく(本ドキュメント自体の作成はAPIキー取得や課金を
伴わない机上作業であり、承認不要)。実際の記入(表の空欄埋め)は実LLM接続の承認が下りて
検証に着手した時点で行う。

## 記入方法

llm-quality-verification-plan.md「検証手順」節と同じ基準に従う。

- 各ケースにつき3回生成し、機械チェック項目はschema/validate_test_cases.py・
  prototype/post_generation_checks.pyの実行結果(pass/fail)をそのまま転記する。
- 人手判定項目は目視で合否(OK/NG)を判定し、NGの場合は具体的にどう厳守事項に抵触したかを
  「メモ」欄に一言残す。
- 3回中1回でもNGがあれば当該ケース・観点は「不合格」として最終判定列に記録し、プロンプト
  側の改善検討対象とする(厳守事項1・4(人手判定分)・5・7は特に人手判定を伴うため慎重に
  確認する)。
- 表が埋まった段階で、この結果を本ファイルにそのまま残すか、分量次第で
  `llm-quality-verification-results-YYYY-MM-DD.md`のような別ファイルに切り出すかを
  その時点で判断する。

## 記録表(G1〜G4: 厳守事項1・4(type=dailyのreminder_notice null)・5)

| ケース | 試行 | 厳守事項1(人手) | reminder_notice null一致(機械、G1=daily対象) | 厳守事項5(人手) | 最終判定 | メモ |
|---|---|---|---|---|---|---|
| G1_daily | 1回目 | | | | | |
| G1_daily | 2回目 | | | | | |
| G1_daily | 3回目 | | | | | |
| G2_monthly_no_reminder | 1回目 | | | | | |
| G2_monthly_no_reminder | 2回目 | | | | | |
| G2_monthly_no_reminder | 3回目 | | | | | |
| G3_monthly_with_reminder | 1回目 | | | | | |
| G3_monthly_with_reminder | 2回目 | | | | | |
| G3_monthly_with_reminder | 3回目 | | | | | |
| G4_annual_with_company | 1回目 | | | | | |
| G4_annual_with_company | 2回目 | | | | | |
| G4_annual_with_company | 3回目 | | | | | |

## 記録表(OOS1: 厳守事項6)

| ケース | 試行 | 厳守事項6(機械: inspection_record/reminder_notice共にnull) | 最終判定 | メモ |
|---|---|---|---|---|
| OOS1_unrelated_request | 1回目 | | | |
| OOS1_unrelated_request | 2回目 | | | |
| OOS1_unrelated_request | 3回目 | | | |

## 記録表(II1〜II3: 必須項目欠落時の挙動)

II1(車両番号欠落)はllm-quality-verification-plan.mdの検証観点表に個別の行はないが、
schema/validate_test_cases.pyのfixtureに存在するため、status=insufficient_inputの一致・
missing_fields_requestが車両番号を名指ししているかを同じ基準で確認する。

| ケース | 試行 | status一致(機械) | missing_fields_requestの文言(人手) | 最終判定 | メモ |
|---|---|---|---|---|---|
| II1_no_vehicle_id | 1回目 | | | | |
| II1_no_vehicle_id | 2回目 | | | | |
| II1_no_vehicle_id | 3回目 | | | | |
| II2_no_type(厳守事項2) | 1回目 | | | | |
| II2_no_type(厳守事項2) | 2回目 | | | | |
| II2_no_type(厳守事項2) | 3回目 | | | | |
| II3_annual_no_company(厳守事項3) | 1回目 | | | | |
| II3_annual_no_company(厳守事項3) | 2回目 | | | | |
| II3_annual_no_company(厳守事項3) | 3回目 | | | | |

## 記録表(全件: 厳守事項7)

| ケース | 絵文字不使用(機械・post_generation_checks.py) | ですます調の統一(人手) | メモ |
|---|---|---|---|
| G1_daily | | | |
| G2_monthly_no_reminder | | | |
| G3_monthly_with_reminder | | | |
| G4_annual_with_company | | | |
| OOS1_unrelated_request | | | |
| II1_no_vehicle_id | | | |
| II2_no_type | | | |
| II3_annual_no_company | | | |

## トークン数・コスト実測記録欄

| ケース | 入力トークン数 | 出力トークン数 | llm-api-cost-estimate.mdの想定シナリオ(A/B)に近いか |
|---|---|---|---|
| G1_daily | | | |
| G2_monthly_no_reminder | | | |
| G3_monthly_with_reminder | | | |
| G4_annual_with_company | | | |
| OOS1_unrelated_request | | | |
| II1_no_vehicle_id | | | |
| II2_no_type | | | |
| II3_annual_no_company | | | |

## 総合結果サマリ(全ケース記入後に埋める)

- 不合格となったケース・観点の一覧:
- プロンプト改善が必要と判断した箇所:
- 「3回中1回でも不合格なら要改善」基準を緩め/厳しめいずれに調整すべきかの所見:
- temperature等のパラメータ調整要否の所見:
- llm-api-cost-estimate.mdの試算との乖離があったかの所見:
