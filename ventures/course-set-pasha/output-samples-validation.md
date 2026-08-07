# 期待JSON出力サンプルの机上検証(2026-08-07 16:00 UTC)

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

## サンプルケース(5件)

| ケースID | status | 想定シナリオ |
|---|---|---|
| G1_basic | generated | 基本ケース。写真言及なし、変更なしエリアなし |
| G2_with_photo_and_unchanged_areas | generated | 写真言及あり(mentions_photo=true)、変更なしエリア2件を明記 |
| G3_count_and_date_unextractable | generated | 入力メモから本数・改訂日(西暦)を抽出できず、history_rowのcount/revision_dateがnullになるケース |
| OOS1_membership_question | out_of_scope | 会員管理・予約に関する質問への不応答ケース(厳守事項7) |
| II1_no_area_no_count | insufficient_input | エリア名・本数が不明で再送を促すケース(厳守事項8) |

## 結果

```
合計 5 件中 5 件パス、0 件失敗
```

5件すべてが、型・必須項目・`status`に応じたnull/非null依存関係のいずれの違反もなく
パスした。特に、schema-structured-output-compat-check.mdで懸念していた「`status`の値に
応じてどのフィールドがnullであるべきか」というクロスフィールドの依存関係(`allOf`撤去後は
スキーマ単体では表現されない)についても、コード側検証(`validate_cross_field_rules`)で
機械的にチェックできることを確認した。

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
