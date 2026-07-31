# 構造化出力スキーマの机上検証レポート(2026-07-31 13:58 UTC)

## 位置づけ
README.mdの「次にやること」で繰り返し指摘されていた
「E10〜E16はいずれも机上設計・実LLM未検証のまま件数が積み上がっているため、
そろそろ実装フェーズ(実際にLLM呼び出しを行う自動テスト化)への着手を検討する時期」
を受けた第一歩。実LLM呼び出し(APIキー・課金が必要)はまだ行わず、
その前段として「これまで文章で書き溜めてきた期待JSON出力に、
記述ミス・スキーマ違反・依存関係違反がないか」を機械的に検証した。

## 実施内容
- `schema/booking_output.schema.json`: llm-system-prompt-draft.md(出力形式)・
  json-schema-multi-intent-extension.md(faq_segments拡張)・
  notification-log-classification-labels.md(escalation_reason/feature_hint拡張)を
  統合したJSON Schema(draft-07)を新規作成。
- `schema/validate_test_cases.py`: 外部ライブラリ非依存(pure stdlib)の簡易JSON Schemaバリデータと、
  conversation-samples-test-cases.mdに明記された期待JSON出力(N1・N2・E2・E5・E6・E9〜E16の15ケース、
  E13/E14は分岐ごとに分けて計15件)のフィクスチャを実装。
  加えて、JSON Schema単体では表現しきれない依存関係ルール
  (`faq_segments`にresolved:falseが含まれる場合は`needs_owner_check`がtrueであること、
  `feature_hint`は`escalation_reason: "unimplemented_feature"`のときのみ許容されること)も
  コード側で検証。

## 結果
15件全てパス(スキーマ違反・依存関係違反なし)。
これまでconversation-samples-test-cases.md・json-schema-multi-intent-extension.md・
notification-log-classification-labels.mdに分散して書かれてきた期待出力の記述に、
少なくとも構造面での矛盾は見つからなかった。

## わかったこと・次の課題
- N3(候補提示後の確定)・N4(常連客)・E1・E3・E4・E7・E8は、
  自然文側の期待挙動は明記されているが構造化出力の全フィールドまでは書き下されておらず、
  今回のフィクスチャには含めていない。次回以降、これらも期待JSON出力を明文化して
  スキーマ検証対象に加えることで、conversation-samples-test-cases.md自体の記述の
  抜けを埋める副次効果が見込める。
- 今回の検証はあくまで「人間が書いた期待値同士の整合性」であり、
  「実LLMが本当にこの通りのJSONを安定して生成できるか」は未検証のまま。
  実LLM呼び出しにはAPIキーの取得・課金が発生するため、実行はオーナー承認後に着手する
  (pending-approval.mdに記録済み)。
- バリデータ自体は今後、実LLM呼び出しの自動テストに転用できる形
  (期待値との突合ロジックの土台)として設計した。

## 実行方法
```
cd ventures/line-reservation-ai/schema
python3 validate_test_cases.py
```
外部ライブラリのインストールは不要(pure Python標準ライブラリのみ)。
