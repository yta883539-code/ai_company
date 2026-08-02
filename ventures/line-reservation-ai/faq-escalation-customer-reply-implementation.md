# escalation/faq intentの顧客向け返信の実装(2026-08-02 11:00 UTC新規作成)

webhook-function-b-implementation.mdの残課題(1)「escalation/faq intentの顧客向け返信
(faq_segmentsとの統合)」に対応した。従来、`prototype/cloud_function_process_event.py`は
`intent != "new_booking"`のイベントを一律`EscalationConsolidator`への転送のみに留めており、
faq/escalation intentでは顧客への自動返信が一切送られていなかった(オーナーに通知が飛ぶだけで、
顧客は無反応のまま放置される状態だった)。

## 実装内容

- `prototype/engine.py`に、faq-response-templates.mdの項目別テンプレートに対応する
  `format_faq_address_message()`・`format_faq_payment_message()`・
  `format_faq_unregistered_message()`を新規追加(既存の`format_faq_parking_message()`は
  台数未入力ケース(空文字capacity)に対応するよう軽微に拡張、既存呼び出し・テストとの
  後方互換は維持)。
- `ConversationEventProcessor`(cloud_function_process_event.py)に`store_faq_info`
  (owner-settings-wireframe.mdの「店舗FAQ情報」入力欄に対応する辞書、
  例: `{"address": ..., "parking": {"available": bool, "capacity": str}, "payment_methods": [...]}`)
  を新規パラメータとして追加。
- `intent: "faq"`かつ`faq_segments`が付与されている場合(複合質問、E13相当)に
  `_handle_faq()`を呼び、項目(topic)ごとに1メッセージずつ送信するようにした
  (faq-response-templates.mdの「1メッセージ1用件」原則準拠)。
  - `resolved: true`の項目は店舗FAQ情報から組み立てた回答を送信。
  - `resolved: false`の項目、および`resolved: true`だが店舗FAQ情報に該当値が
    登録されていない項目(構造化出力と店舗設定の不整合)は、共通の保留文言
    (`format_faq_unregistered_message()`)に安全側フォールバックする。
- `intent: "escalation"`(厳守事項6・10)の場合は`_handle_escalation()`を呼び、
  同じ保留文言を一次応答として即時送信するようにした。

## 未解決のまま残した制約

単一項目FAQ(E10・E6等、構造化出力の`faq_segments`が`null`のケース)は、
json-schema-multi-intent-extension.mdの既存方針(「単一項目では`faq_segments`を
省略することを推奨」)により、どの店舗FAQ項目(topic)への質問かを表す情報が
構造化出力に一切含まれない。このためengine側ではテンプレート回答を一意に組み立てられず、
今回は従来通り「単一項目faqはオーナー転送のみ・自動返信なし」の挙動を維持した
(`test_single_item_faq_without_segments_is_still_forwarded_only`で回帰確認)。

この制約の解消には、json-schema-multi-intent-extension.mdの推奨を見直し
「`intent: "faq"`のときは単一項目でも1要素配列として`faq_segments`を必ず付与する」
方向に倒すスキーマ変更が必要になる可能性がある(llm-system-prompt-draft.md・
booking_output.schema.json・conversation-samples-test-cases.mdのE6/E10/E14の
期待JSON出力など影響範囲が広いため、次回以降の課題として切り出した)。

## テスト

`prototype/test_cloud_function_process_event.py`に`EscalationReplyTests`・
`FaqSegmentReplyTests`を新規追加(7件)。既存の`test_non_booking_intent_is_forwarded_without_touching_flow`
は挙動変更(escalationはもはや「転送のみ」ではない)に伴い、cancel intentを使う
`test_unimplemented_intent_is_forwarded_without_touching_flow`に置き換えた。
全68件パス確認済み(旧61件+新規7件)。
