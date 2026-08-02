# 構造化出力スキーマの机上検証レポート(2026-07-31 13:58 UTC、2026-07-31 14:58 UTC追記、2026-08-02 14:00 UTC追記)

## 追記(2026-08-02 14:00 UTC)
json-schema-multi-intent-extension.mdの改訂(単一項目9a FAQでも`faq_segments`を
1要素配列で必ず付与する方針に変更)を受け、E10・E14_faqのフィクスチャに
`faq_segments`(それぞれ`[{topic: "parking", resolved: true}]`・
`[{topic: "payment", resolved: true}]`)を追加。既存22件フィクスチャは全件パスを
再確認済み(スキーマ自体はfaq_segmentsの要素数を制約していないため、
スキーマファイル自体の変更は不要だった)。

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

## 追記(2026-07-31 14:58 UTC): N3・N4・E1・E3・E4・E7・E8の追加検証
上記「次の課題」で挙げていたN3・N4・E1・E3・E4・E7・E8の期待構造化出力を
conversation-samples-test-cases.mdに明文化し、validate_test_cases.mdのフィクスチャに追加した。
- N3・N4(確定系): 3項目(名前・メニュー・日時)が揃った時点で`confirmed: true`になる
  ことを明示。N4は常連客のため顧客DB登録値からの補完という設定を明記。
- E1・E3・E4(候補提示・保留系): いずれもシステム側で自動処理が完結し、オーナーの
  個別判断を要しないため`needs_owner_check: false`とした。
- E7・E8(フォーマット崩れ系): json-output-retry-fallback.mdのフォールバック方針に従い、
  E7(構文が壊れてパース自体が失敗)は名前・メニュー等の情報がバックエンドに引き継がれず
  一律`intent: "escalation"`・`needs_owner_check: true`・`confirmed: false`に合成される点、
  E8(パースは成功するが自然文と矛盾)は元のJSONの値を引き継ぎつつ`confirmed`は常にfalseへ、
  `needs_owner_check`はtrueへ安全側に上書きされる点を区別して記録した。
  ここでの「期待される構造化出力」はLLMの生出力そのものではなく、リトライ・フォールバック処理後に
  バックエンドが記録する最終値である点に注意(E7は特に、実LLMがどこまで壊れたJSONを返しうるかは
  未検証で、あくまでフォールバック後の合成値を示す)。

新規追加7件を含む22件全件が引き続きスキーマ・依存関係違反なくパスした
(`python3 validate_test_cases.py`で確認)。

## わかったこと・次の課題
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
