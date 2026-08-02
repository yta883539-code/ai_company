# 単一項目FAQのfaq_segments付与ルール見直し(2026-08-02 14:00 UTC新規作成)

README「次にやること」の残課題(a)「単一項目FAQ(faq_segmentsがnullのケース)でも
自動返信できるようにするスキーマ変更の要否検討」に対応した。

## 背景・問題

faq-escalation-customer-reply-implementation.md(2026-08-02 11:00 UTC)で
複合FAQ(`faq_segments`が2項目以上)は項目ごとにテンプレート自動返信できるようにしたが、
単一項目FAQ(E10「駐車場はありますか」等)は`json-schema-multi-intent-extension.md`の
既存推奨(「複合質問(2項目以上)のときのみ`faq_segments`を付与、単一項目では省略」)により
`faq_segments`が`null`のままとなり、engine側がどの店舗FAQ項目(topic)への質問かを
特定できず、テンプレート回答を自動生成できない(オーナー転送のみ・顧客への自動返信なし)
という制約が残っていた。E10・E14(前半)のような、店舗FAQ情報に登録済みの単純な質問でさえ
毎回人手対応が必要になり、本サービスの価値提案(定型的なやり取りの自動化)を損なう
ギャップだった。

## 検討した選択肢

1. **単一項目でもfaq_segmentsを1要素配列で必ず付与する方向にスキーマ推奨を変更**(採用)
   - 既存の複合質問向け処理ループ(`_handle_faq`、`prototype/cloud_function_process_event.py`)を
     そのまま流用でき、要素数が1でも2以上でも同じコードパスで動く。追加の分岐実装が不要。
   - JSON Schema(`schema/booking_output.schema.json`)側は`faq_segments`の要素数に
     制約(`minItems`等)を設けていなかったため、スキーマファイル自体の変更は不要
     (`validate_test_cases.py`のフィクスチャ22件全件パスを確認済み)。
   - デメリット: 単純な単一項目質問でも配列を組み立てる分、LLM側の出力がわずかに複雑になる
     (json-schema-multi-intent-extension.mdの既存懸念「実際のLLMが安定して出力できるか」は
     単一項目の追加によりやや悪化する可能性はあるが、要素数1の配列は複合(2項目以上)より
     単純なため、大きな追加リスクではないと判断)。
2. トップレベルに`faq_topic`のような単一値フィールドを新設し、`faq_segments`とは別に
   単一項目用の経路を用意する(不採用: 単一項目用・複合質問用の2つの経路をengine側で
   二重に実装・保守する必要が生じ、json-schema-multi-intent-extension.mdが元々避けようとした
   「二重管理」を別の形で再導入してしまうため)。
3. 現状維持(単一項目は`null`のままオーナー転送のみ)(不採用: 上記の通り本サービスの
   自動化価値を損なうギャップが残るため)。

## 決定

選択肢1を採用。ただし全ての`faq` intentに機械的に強制するのではなく、
**厳守事項9a(店舗登録済み静的情報access/parking/payment/hoursに基づく回答)に該当する
場合のみ**`faq_segments`を1要素以上の配列で必須にする。厳守事項9b(雑談・スパム的入力、
E6等)は特定の店舗FAQ項目に基づく回答ではないため、引き続き`faq_segments`は`null`のまま
とする(9bにまで`topic: "other"`等を無理に割り当てると、雑談判定と9a判定の境界が
かえって曖昧になるため)。

## 反映箇所

- `json-schema-multi-intent-extension.md`: 「単一項目では省略」推奨を撤回し、
  9aに基づく`faq` intentは項目数によらず配列必須とする方針に改訂。
- `llm-system-prompt-draft.md`: 出力形式の`faq_segments`説明文を改訂履歴付きで更新。
- `schema/booking_output.schema.json`: `faq_segments`のdescriptionを更新
  (スキーマの構造自体は変更なし)。
- `conversation-samples-test-cases.md`: E10・E14(前半)に期待される構造化出力
  (`faq_segments`1要素配列)を追記。E6には`faq_segments`が引き続き`null`である理由を明記。
- `schema/validate_test_cases.py` / `schema-validation-report.md`: E10・E14_faqの
  フィクスチャに`faq_segments`を追加し、22件全件パスを再確認。
- `prototype/cloud_function_process_event.py`: モジュールdocstring・`process()`内の
  コメントを更新(コード自体の分岐ロジックは変更不要、既存の`_handle_faq`がそのまま
  単一要素配列にも対応できるため)。デモ(`_demo()`)に単一項目FAQ自動返信の例(4b)を追加。
- `prototype/test_cloud_function_process_event.py`: 単一項目`faq_segments`が
  自動返信される新規テスト(`test_single_item_faq_segments_is_answered_from_template`)を追加。
  既存の「faq_segments無しは転送のみ」テストは、9b雑談・レガシー出力向けの安全側
  フォールバックを検証するテストとして名称・入力例(E6相当の「こんにちは!」)を更新。

## テスト結果

`prototype/test_cloud_function_process_event.py`: 21件全件パス(既存20件+新規1件、
既存1件は名称・内容更新)。`schema/validate_test_cases.py`: 22件全件パス。
リポジトリ全体(engine 32件・webhook 17件・process_event 21件・reminder_scheduler 21件)、
合計91件全件パス確認済み。

## 未解決のまま残した課題

- 実際のLLMが本改訂の指示(9aは単一項目でも配列で出力)に安定して従えるかは、
  json-schema-multi-intent-extension.mdの既存の未検証事項と同様、実LLM接続後の課題として残る
  (オーナー承認待ち、pending-approval.md参照)。
- 厳守事項9aの5トピック(access/parking/payment/hours/other)のうち、
  `faq-response-templates.md`が実際にテンプレートを持つのはaccess/parking/paymentの3つのみで、
  hours/otherはresolved: trueでも安全側で保留文言にフォールバックする既存の挙動
  (`test_access_topic_uses_registered_address`参照)は変更していない。hours/otherの
  テンプレート追加は別課題として残る。
