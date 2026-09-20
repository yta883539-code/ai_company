# 期待JSON出力サンプルの机上検証(2026-08-07 16:00 UTC、2026-08-22 06:00 UTC追記)

## 位置づけ

README.md「次にやること(候補)」1点目
「改訂後のschema/output.schema.jsonに対応する期待JSON出力サンプル(status別3パターン)を
作成し、line-reservation-aiのvalidate_test_cases.pyのような机上バリデータでstatus⇔
null/非nullの依存関係違反がないか検証する」に対応。

schema-structured-output-compat-check.md(2026-08-07 15:00 UTC)の改訂方針
(`allOf`/`if`/`then`を撤去し、全プロパティを常時`required`化・該当しない場合は`null`を許容、
`status`に応じたnull/非nullの依存関係はコード側検証で担保)が、実際のサンプル出力に対して
機械的に検証可能かを確認するため、schema/validate_test_cases.py を新規作成した。

## 検証方法

line-reservation-aiのschema/validate_test_cases.pyと同じ設計。

- 外部ライブラリ非依存(pure stdlib)の簡易バリデータで、output.schema.jsonのサブセット
  (type/enum/required/additionalProperties/items)を解釈してフィールド単位の型・必須項目
  違反を検出する。
- スキーマ単体では表現できない`status`⇔null/非nullの依存関係(厳守事項7・8に対応する
  分岐)は`validate_cross_field_rules()`で個別にチェックする。

## サンプルケース(18件、ネガティブテスト3件を含めると21件)

作成当初(2026-08-07 16:00 UTC)は5件だったが、その後の厳守事項追加に伴いschema/
validate_test_cases.pyへケースが追加され続け、2026-08-22 06:00 UTC時点で9件・
2026-09-19定例更新(フェーズ226)時点で21件(TEST_CASES 18件+ネガティブテスト3件)と
なっていた。以降しばらく一覧表・件数表記が初版更新(9件)のまま追随できていなかったが、
本フェーズ(2026-09-20定例更新)で`schema/validate_test_cases.py`のTEST_CASES全件を
棚卸しし、以下の表を全面更新した。

| ケースID | status | 想定シナリオ |
|---|---|---|
| G1_basic | generated | 基本ケース。写真言及なし、変更なしエリアなし |
| G2_with_photo_and_unchanged_areas | generated | 写真言及あり(mentions_photo=true)、変更なしエリア2件を明記 |
| G3_count_and_date_unextractable | generated | 入力メモから本数・改訂日(西暦)を抽出できず、history_rowのcount/revision_dateがnullになるケース |
| G4_multi_area_single_memo | generated | フェーズ11(2026-08-07 20:00 UTC)で追加。1回のメモで3エリア(エリアF・G・H)を同時更新し、`history_rows`の要素数が更新エリア数(3)に一致するケース |
| OOS1_membership_question | out_of_scope | 会員管理・予約に関する質問への不応答ケース(厳守事項7) |
| II1_no_area_no_count | insufficient_input | エリア名・本数が不明で再送を促すケース(厳守事項8) |
| CI1_cancellation_intent_clear | cancellation_intent | フェーズ54(2026-08-15 08:00 UTC)で追加。解約意図が明確なケース。`subscription_procedure_notice`にStripeカスタマーポータルへの案内文が付与される(厳守事項7a) |
| CI2_downgrade_intent | downgrade_intent | 解約ではなくプラン変更(ダウングレード)の意図と判定されるケース。日割り精算・ポータル案内が付与される |
| CI3_cancellation_unclear | cancellation_unclear | 解約意図か判断できないあいまいなケース。断定せず本人へ確認を促す文言のみを返し、`includes_portal_link`はfalse |
| CI4_chitchat_no_course_content | insufficient_input | 2026-09-13 02:00 UTC追加。厳守事項7a(iii)(雑談の域を出ない表現)の帰着先を決定した際の期待出力。課題入れ替え内容を含まない雑談のみのメモで、エリア名・本数不明として再送を促す側に帰着するケース |
| CI5_chitchat_with_course_content | generated | 2026-09-13 02:00 UTC追加。CI4と対になるケース。雑談の後に課題入れ替え内容(エリアA新着8本等)が続く場合は、雑談部分を無視して通常どおり3出力を生成する側に帰着する |
| CI6_busy_season_grumble_not_cancellation | generated | 2026-09-18定例更新で追加。aircon-pashaのG8と対になる7a(iii)境界ケース。CI4・CI5(利用頻度低下方向の雑談)とは逆に、セッター側の多忙・繁忙を愚痴る表現(「セット依頼が多すぎて全然追いつかない」等)が契約継続に触れない雑談の域を出ない場合、解約意図とは判定せず通常どおり3出力を生成する |
| CI7_busy_grumble_not_checkout_intent | generated | 2026-09-19定例更新で追加。kura-pashaのC5・aircon-pashaのG9と対になる7b(iii)境界ケース。CI6とは逆に、「プラン」の語を含む繁忙の愚痴(「プランのことなんて考える暇もない」等)が有料プラン開始意図に触れない雑談の域を出ない場合、checkout意図とは判定せず通常どおり3出力を生成し、checkout_noticeはNoneのままとなる |
| CO1_checkout_intent | checkout_intent | 2026-09-12 02:00 UTC追加(フェーズ206)。厳守事項7b(i)相当。有料プラン開始意図が明確なケース。`checkout_notice`に案内文が付与されるが、Checkout Session URLはコード側で発行するため`includes_checkout_url`はfalse |
| CO2_pricing_inquiry | pricing_inquiry | フェーズ206追加。厳守事項7b(ii)相当。料金プランの問い合わせに対し、3プラン(ライト/スタンダード/セッター複数)の料金を案内する |
| CO3_checkout_intent_unclear | checkout_intent_unclear | フェーズ206追加。厳守事項7b(iv)相当。有料プラン開始意図か判断できないあいまいなケース。断定せず本人へ確認を促す文言のみを返す |
| CO4_chitchat_no_course_content | insufficient_input | 2026-09-13 22:00 UTC追加。CI4の7b版。厳守事項7b(iii)(雑談の域を出ない表現)の帰着先決定に伴う期待出力で、課題入れ替え内容を含まない雑談のみの場合は再送を促す側に帰着する |
| CO5_chitchat_with_course_content | generated | 2026-09-13 22:00 UTC追加。CI5の7b版。雑談の後に課題入れ替え内容が続く場合は雑談部分を無視して通常どおり3出力を生成する |
| NEG1_checkout_url_mismatch_is_detected | checkout_intent(不正フィクスチャ) | 2026-09-12 02:00 UTC追加(フェーズ206)。厳守事項7b違反(`checkout_notice.includes_checkout_url`を誤ってtrueにしてしまう)を意図的に仕込み、`validate_cross_field_rules`が実際に検出できることを確認するネガティブテスト |
| NEG2_portal_link_mismatch_is_detected | cancellation_unclear(不正フィクスチャ) | フェーズ225追加。厳守事項7a(iv)違反(`subscription_procedure_notice.includes_portal_link`を誤ってtrueにしてしまう)の検出確認。kura-pashaのNEGATIVE_CASE_PORTAL_LINK_MISMATCHと同型 |
| NEG3_empty_history_rows_is_detected | generated(不正フィクスチャ) | フェーズ226追加。`history_rows`空配列禁止ルール(status=generatedのとき1件以上必要)違反の検出確認 |

## 結果(2026-09-20定例更新時点)

```
合計 21 件中 21 件パス、0 件失敗
```

21件すべて(TEST_CASES 18件+ネガティブテスト3件)が、型・必須項目・`status`に応じた
null/非null依存関係のいずれの違反もなくパスした(ネガティブテスト3件は意図的な違反
フィクスチャであり、`validate_cross_field_rules`がそれぞれの違反を正しく検出できることを
「検出できた=OK」として確認している)。特に、schema-structured-output-compat-check.mdで
懸念していた「`status`の値に応じてどのフィールドがnullであるべきか」というクロスフィールド
の依存関係(`allOf`撤去後はスキーマ単体では表現されない)についても、コード側検証
(`validate_cross_field_rules`)で機械的にチェックできることを確認した。

最新の実行結果は`python3 schema/validate_test_cases.py`を直接実行して確認すること。

## 残る未検証事項

- 上記はあくまで机上検証であり、実際にLLMがこの形式で安定して構造化出力を生成できるかは
  未確認(実LLM呼び出しはAPIキー取得・課金がオーナー承認待ちのため、line-reservation-aiと
  同様に実装フェーズ・API接続時の検証に持ち越し)。
- G3のように「抽出できない項目をnullとして扱う」ケースは、LLMが実際に「わからないのでnullを
  返す」のか「それらしい値を推測して埋めてしまう」のかは机上検証では確認できない
  (llm-system-prompt-draft.mdの厳守事項として明記済みだが、プロンプト遵守率の検証は
  実LLM接続後の課題として残る)。
- mentions_photoがtrue/false双方で正しく分岐する保証は、システムプロンプトの厳守事項3の
  遵守にかかっており、こちらも実LLM検証が必要。
