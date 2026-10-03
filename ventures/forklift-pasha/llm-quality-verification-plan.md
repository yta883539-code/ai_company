# 実LLM接続後の生成品質検証プラン(フェーズ7・2026-10-03 07:00 UTC)

## 位置づけ

kura-pasha/course-set-pasha/aircon-pashaのllm-quality-verification-plan.mdと同じ位置づけの
文書を、本ventureにはまだ存在していなかったため新規作成する(output-samples-validation.md
フェーズ6の「次回候補」1点目に対応)。schema/validate_test_cases.pyに机上検証用フィクスチャが
既に11件(正常系8件+ネガティブ3件)揃っているが、これらを実際にAPIキー取得・課金の承認が
下りた際にどう検証へ転用するかを事前に整理しておく。本ドキュメントの作成・整理はAPIキー取得や
課金を伴わないため承認不要な机上作業であり、実際のLLM API呼び出しはこれまで通りオーナー承認待ち
のまま未実施(pending-approval.md参照)。

## 検証観点(厳守事項・出力別)

llm-system-prompt-draft.mdの厳守事項1〜7を対象に、schema/validate_test_cases.pyのG1〜G4・
OOS1・II1〜II3の8正常系ケースを実LLMに投入し、以下の観点ごとに合否判定する。

| # | 厳守事項 | 検証観点 | 判定方法 | 対象ケース |
|---|---|---|---|---|
| 1 | 厳守事項1(点検結果の良否判断・修理要否の判断をしない) | 入力メモの結果(「異常なし」「ブレーキ○」等)がそのまま転記され、AIが独自に安全性を評価・保証する文言が混入していないか | 人手のみ(機械チェック不可、否定の証明ができないため) | G1〜G4全件 |
| 2 | 厳守事項2(点検種別必須、欠落時は再送依頼) | II2(種別欠落)で`status=insufficient_input`となり種別の追記を促す文言になっているか、推測で種別を決定していないか | 機械チェック(`status`値の一致)+人手(`missing_fields_request`の文言が種別を名指ししているかの目視) | II2 |
| 3 | 厳守事項3(annualで検査業者名必須、欠落時は再送依頼) | II3(annualで検査業者名欠落)で`status=insufficient_input`となり検査業者名の追記を促す文言になっているか | 機械チェック(`status`値+`inspection_record.inspector_company`のnull一致)+人手(文言が検査業者名を名指ししているかの目視) | II3・G4(対比) |
| 4 | type=dailyのreminder_notice常時null(mvp-flow-draft.md) | G1(daily)で`reminder_notice`が常にnullであり、monthly/annual(G2〜G4)との出し分けが保たれているか | 機械チェック(`inspection_record.type`別のnull/非null一致) | G1〜G4 |
| 5 | 厳守事項4(点検・検査の実施自体を代行・指示しない) | 出力文言に「点検を実施します」等、AIが点検・検査行為自体を代行するかのような記述が混入していないか | 人手のみ | G1〜G4全件 |
| 6 | 厳守事項6(対象外要求への不応答) | OOS1で`inspection_record`/`reminder_notice`が共にnullのまま定型文言のみ返しているか | 機械チェック(`status=="out_of_scope"`時に両フィールドがnullであることの確認) | OOS1 |
| 7 | 厳守事項7(ですます調・絵文字不使用) | 絵文字が一切含まれていないか、文体が統一されているか | 機械チェック(他venture同様のpost_generation_checks.py相当の絵文字検出、本venture未実装のため実装候補とする)+人手(ですます調の文体統一は自由文であり機械チェックでの網羅確認は困難) | 全件 |

## 検証手順(承認後に着手する想定)

1. schema/validate_test_cases.pyのG1〜G4・OOS1・II1〜II3(8正常系ケース)の入力メモ文面を
   実際にAPIへ投入し、構造化出力を`validate_against_schema()`・`validate_cross_field_rules()`
   にそのまま通す(型・必須項目・cross-fieldルールは機械チェックで即座に合否判定可能)。
2. 上表の「人手」判定項目については、各ケースにつき最低3回ずつ生成し(同一入力でも生成結果が
   ばらつく可能性があるため)、3回中何回意図通りかを記録する。3回中1回でも厳守事項1・4・7に
   抵触する生成があれば「不合格」とし、プロンプト側の指示強化を検討する基準とする(他ventureの
   実LLM検証着手時と同じ基準を採用)。
3. 生成に要したトークン数を`count_tokens`(無料エンドポイント)で計測し、llm-api-cost-
   estimate.mdの想定シナリオ(シナリオA/B)に近いかを確認する。

## 記録先

aircon-pasha・course-set-pasha・kura-pashaはllm-quality-verification-results-template.mdを
別ファイルとして用意している。本ventureも同じ方針を踏襲し、実LLM検証着手の承認が下りた時点で
llm-quality-verification-results-template.mdを別ファイルとして切り出す(先行して本文書だけを
用意し、結果記録用テンプレートは承認が近づいた段階で作成する判断とする)。

## 残る未確定事項

- 「3回中1回でも不合格なら要改善」という基準は他venture同様に暫定であり、実際の生成結果を
  見た上で緩め・厳しめのいずれに調整すべきかは実測後に見直す。
- 厳守事項7(絵文字不使用)の機械チェックスクリプト(他ventureのpost_generation_checks.py相当)
  は本ventureにはまだ実装されていない。承認前の机上整備として次回候補とする。

## 次の課題

- 厳守事項7の機械チェック用スクリプト(prototype/post_generation_checks.py相当)の新規実装。
- 実顧客ヒアリング(送信・連絡が必要なためオーナー許可待ち)。
- tech-stack.md・ci-setup.md等、他venture並みの運用文書の整備(他venture対比で未着手の項目)。
