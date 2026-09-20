# 期待JSON出力サンプルの机上検証(2026-09-20 23:00 UTC)

## 位置づけ

aircon-pasha/output-samples-validation.md・course-set-pasha/output-samples-validation.md
と同じ位置づけの文書を、本ventureにはまだ存在していなかった(cross-venture parityの
ギャップ)。kura-pasha自体はschema/validate_test_cases.pyが既に32件(正常系23件+
ネガティブ9件)まで積み上がり、llm-quality-verification-plan.md・llm-quality-
verification-results-template.mdも先行して用意済みだったが、実LLM接続前の「机上検証の
まとめ」としてこのケース一覧・結果・残る未検証事項を1文書に整理する種別だけが本venture
単独では未着手だった。本ドキュメントの作成はAPIキー取得・課金を伴わない机上作業であり
承認不要。実際のLLM API呼び出しはこれまで通りオーナー承認待ちのまま未実施
(pending-approval.md参照)。

## 検証方法

course-set-pasha・aircon-pashaと同じ設計方針を踏襲し、既存のschema/validate_test_cases.py
(外部ライブラリ非依存のpure stdlib簡易バリデータ)を使う。

- output.schema.jsonのサブセット(type/enum/required/additionalProperties)を解釈して
  フィールド単位の型・必須項目違反を検出する`validate_against_schema()`。
- スキーマ単体では表現できない`status`⇔各出力フィールドのnull/非nullの依存関係
  (厳守事項3・4・6・7・7a・7b・7c、および各種design.md側の判定基準)を個別にチェックする
  `validate_cross_field_rules()`。

## サンプルケース(32件。正常系23件+ネガティブ9件)

| ケースID | status | 想定シナリオ |
|---|---|---|
| G1_new_basic | generated | 基本ケース。区分=新規制作、鞍の型・革の種類・用途・納期がすべて揃っている |
| G2_repair_with_remarks | generated | 区分=修理、備考欄の破損箇所・症状の記述をそのまま転記(厳守事項2) |
| OOS1_membership_question | out_of_scope | 会員管理・予約受付・決済に関する質問への不応答ケース(厳守事項6) |
| II1_no_category | insufficient_input | 区分の記載が無く再送を促すケース(厳守事項3) |
| II2_no_saddle_type | insufficient_input | 鞍の型が読み取れず再送を促すケース(厳守事項7) |
| C1_cancellation_intent | cancellation_intent | 厳守事項7a(解約意図検知)の明確な解約意思表示ケース |
| C2_downgrade_intent | downgrade_intent | 厳守事項7a、複数職人プランからのダウングレード意思表示ケース |
| C3_cancellation_unclear | cancellation_unclear | 厳守事項7a(iv)、解約意図か判断できないケース |
| C4_busy_season_grumble_not_cancellation | generated | 受注が立て込んでいることへの愚痴のみで契約継続・解約に触れない表現が続いても、厳守事項7a(iii)により解約意図と混同せず通常どおり受注メモを生成するケース(subscription_procedure_noticeはNoneのまま) |
| C5_busy_grumble_not_checkout_intent | generated | 「プラン」の語を含む繁忙の愚痴が続いても、申込・開始意図に触れないため厳守事項7b(iii)によりcheckout_noticeと混同しないケース。C4と対になる7b版の境界固定サンプル |
| M1_member_retention_selection | member_retention_selection | member-retention-notice-design.mdの明確な指定パターン |
| M2_member_retention_unclear | member_retention_unclear | 同design.md、判断不能パターン |
| CT1_contractor_transfer_selection | contractor_transfer_selection | contractor-transfer-design.mdの職人アカウント引き継ぎ先を明確に指定するパターン |
| CT2_contractor_transfer_unclear | contractor_transfer_unclear | 同design.md、引き継ぎ意図か判断できないパターン |
| CTC1_contractor_transfer_confirmed | contractor_transfer_confirmed | contractor-transfer-confirmation-detection-design.md、引き継ぎ承諾の明確な確認 |
| CTC2_contractor_transfer_cancelled | contractor_transfer_cancelled | 同design.md、引き継ぎ取り消しの明確な確認 |
| CTC3_contractor_transfer_reconfirm_unclear | contractor_transfer_reconfirm_unclear | 同design.md、承諾か取り消しか判断できず再確認するパターン |
| CTE1_contractor_transfer_expired_notice | contractor_transfer_expired_notice | contractor-transfer-expired-notice-design.md、引き継ぎ期限切れ通知 |
| CO1_checkout_intent | checkout_intent | 厳守事項7b、有料プラン(複数職人プラン等)開始意図の明確な表明 |
| CO2_pricing_inquiry | pricing_inquiry | 厳守事項7b、料金の問い合わせのみ(開始意図ではない) |
| CO3_checkout_intent_unclear | checkout_intent_unclear | 厳守事項7b(iv)、開始意図か問い合わせか判断できないケース |
| WIR1_workshop_invite_request | workshop_invite_request | 厳守事項7c、複数職人プランでの職人追加(招待コード発行)意図の明確な表明 |
| WIR2_workshop_invite_request_unclear | workshop_invite_request_unclear | 厳守事項7c(iv)、職人追加意図か判断できず意思確認を返すケース |
| NEG1_category_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。order_summary.categoryとdelivery_notice.categoryの不一致(厳守事項4違反)が検出されることの確認用 |
| NEG2_portal_link_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。cancellation_unclear時にincludes_portal_link=trueとなっている(厳守事項7a(iv)相当違反)が検出されることの確認用 |
| NEG3_member_retention_kind_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。member_retention_notice.kindとstatusの不一致が検出されることの確認用 |
| NEG4_contractor_transfer_kind_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。contractor_transfer_notice.kindとstatusの不一致が検出されることの確認用 |
| NEG5_contractor_transfer_confirmation_kind_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。contractor_transfer_confirmation.kindとstatusの不一致が検出されることの確認用 |
| NEG6_contractor_transfer_expired_notice_present_when_status_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。statusがcontractor_transfer_cancelledなのにcontractor_transfer_expired_noticeが非nullである(整合性違反)が検出されることの確認用 |
| NEG7_contractor_transfer_expired_notice_name_null_is_detected | (エラー検出確認) | ネガティブテスト。candidate_member_nameがnullになっている(design.md3節違反)が検出されることの確認用 |
| NEG8_checkout_url_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。includes_checkout_url不一致(厳守事項7b違反)が検出されることの確認用 |
| NEG9_workshop_invite_code_mismatch_is_detected | (エラー検出確認) | ネガティブテスト。includes_invite_code不一致(厳守事項7c違反)が検出されることの確認用 |

## 結果(2026-09-20 23:00 UTC作成時点)

```
合計 32 件中 32 件パス、0 件失敗
```

`python3 schema/validate_test_cases.py`で実行内容を確認できる。G1・G2・OOS1・II1・II2・
C1〜C5・M1・M2・CT1・CT2・CTC1〜CTC3・CTE1・CO1〜CO3・WIR1・WIR2の23件が違反なくパスし、
NEG1〜NEG9の9件は意図通りエラーが検出されることを確認した。あわせて回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(103件)も変更前と同じ結果で
パスすることを確認した(本ドキュメント作成に伴うコード変更は無い)。

G1(新規制作)とG2(修理)の対比により、`order_summary.category`と`delivery_notice.category`
の一致(厳守事項4)が機械的にチェック可能であることを確認した。C4・C5では、厳守事項7a
(iii)・7b(iii)(契約継続・解約や申込・開始のいずれにも触れない愚痴)の境界が、他venture
(aircon-pasha G8・G9、course-set-pasha同種ケース)と同じ帰着ルールでcross-venture parityを
保った形でサンプル化できていることを確認した。

## 残る未検証事項

- 上記はあくまで机上検証であり、実際にLLMがこの形式で安定して構造化出力を生成できるかは
  未確認(実LLM呼び出しはAPIキー取得・課金がオーナー承認待ちのため、llm-quality-
  verification-plan.mdに記載の検証手順に持ち越し)。
- II2のように「鞍の型が読み取れない」ケースは、LLMが実際に「わからないので再送を促す」
  のか「それらしい型を推測して埋めてしまう」のかは机上検証では確認できない
  (llm-system-prompt-draft.md厳守事項3・7として明記済みだが、プロンプト遵守率の検証は
  実LLM接続後の課題として残る)。
- C4・C5(繁忙期の愚痴と解約意図・開始意図の混同防止)は、あくまで「この入出力ペアなら
  整合的である」ことのスキーマレベル確認に留まり、実LLMが実際に愚痴を意図と誤検知
  しないかどうかは、他の7a/7b/7c境界の検証と同様に実LLM接続後(オーナー承認待ち)の
  検証課題として引き続き残る。
- M1・M2・CT1・CT2・CTC1〜CTC3・CTE1・WIR1・WIR2は、それぞれの専用design.md側にも
  個別の判定基準が定義されている。本文書ではschema/cross-fieldレベルの整合性確認に
  留め、design.md側の判定基準に基づく詳細な合否判定はllm-quality-verification-plan.md
  「検証観点」節の記載どおり各design.md側で行う運用とする(重複掲載を避けるための方針、
  aircon-pasha・course-set-pashaの同種文書と同じ切り分け)。
