# `needs_owner_check`のオーナー通知配線 intent横断点検(フェーズ続き136)

作成日: 2026-08-25

## 背景

new-booking-needs-owner-check-notification-design.md(フェーズ続き135)「残る課題」に
記載した「同様のパターン(`needs_owner_check: true`だがintentの分岐先がオーナー通知を
呼ばない組み合わせ)が他のintentでも起こりうるかは未点検」を受け、`intent`が
`faq`/`escalation`/`cancel`/`change`の各分岐について`ConversationEventProcessor`が
LLM構造化出力の`needs_owner_check`を実際にオーナー通知(`_notify_owner()`経由の
`EscalationConsolidator.on_event()`呼び出し)へ正しくつなげているかを点検した。

## 点検結果

### faq / escalation intent: 問題なし

`process()`は`intent == "faq" and faq_segments`で`_handle_faq()`へ、
`intent == "escalation"`で`_handle_escalation()`へ分岐するが、両関数とも
`needs_owner_check`の値に関わらず**無条件に**`_notify_owner(user_id, output, now, reply_text)`を
呼んでいる(cloud_function_process_event.py 701行目・742行目)。実際にオーナーへpushするか
どうかの判定は`_notify_owner()`が呼ぶ`EscalationConsolidator.on_event()`ではなく、
`engine.py`の`is_escalation_event_owner_notable()`(呼び出し元は`_dispatch_notify_actions()`
経由、要pushのアクションのみ生成)が`needs_owner_check`と`escalation_reason`の両方を見て
判定する設計になっており、`needs_owner_check: false`のfaq(9a・9bとも)は正しく非通知に
なる。つまりfaq/escalationは「常に`_notify_owner()`を呼ぶが、実際にpushするかは
`needs_owner_check`込みで下流が判定する」設計のため、フェーズ続き135のnew_bookingのような
「呼ばれること自体がない」ギャップは存在しない。

### cancel / change intent: フェーズ続き135と同型の欠落ではないと判断

`_handle_cancel()`/`_handle_change()`はいずれも`output`の`needs_owner_check`を一切
参照せず、`ConversationFlowStateMachine.cancel_booking()`/`change_booking()`が返す
`result.found`・`result.stage`(会話・予約の実体状態)のみでオーナー通知要否を独自に
決定している(cancel-intent-handling-design.md「対応方針」の表参照:
状態なし→通知あり、`candidates_presented`/`awaiting_details`→通知なし、`confirmed`→通知あり)。

一見するとnew_bookingと同型(LLMの`needs_owner_check`が握りつぶされている)に見えるが、
以下の理由で同じ欠落とは判断しなかった。

1. llm-system-prompt-draft.md 厳守事項3は「キャンセル・変更の意図を検知した場合、
   (中略)オーナー通知フラグを立てる」としており、`cancel`/`change` intentでは
   `needs_owner_check`は(矛盾検知等の異常時に限らず)**通常時から一貫して`true`**に
   なる想定である。これはnew_booking intentで`needs_owner_check`が通常`false`で
   矛盾検知時のみ`true`になり異常の合図として機能するのとは根本的に性質が異なる
   ("常にtrueなフラグ"は個別のイベントを区別する情報を持たない)。
2. cancel-intent-handling-design.mdは、厳守事項3の「常に通知」をそのまま実装すると
   `candidates_presented`/`awaiting_details`(オーナー側の外部予約記録にまだ何も
   反映されていない段階)でも毎回通知が飛び、escalation-consolidation-logic.mdが
   警戒する「通知過多」を招くという理由を明記した上で、あえて`needs_owner_check`
   フラグではなく予約の実体状態(`result.found`/`result.stage`)を通知要否の判断軸に
   採用している。これは見落としではなく検討済みの設計判断であり、この一次資料
   (cancel-intent-handling-design.md「オーナーへの通知」列とその直後の理由説明)を
   本ドキュメントから明示的に参照する形で「意図的な設計」であることを記録として残す。
3. 自然文とJSONの矛盾検知(E8相当)がcancel/change intentのケースで発生した場合
   (例:自然文は「キャンセルします」なのにJSONの`confirmed`だけ矛盾した値になる等)、
   矛盾検知の安全側上書きが`confirmed`/`needs_owner_check`に対して行われても、
   `confirmed`は`_handle_cancel`/`_handle_change`の分岐に元々影響しない
   (両関数は`output`の`confirmed`を参照しない)ため、new_bookingのように
   「安全側に倒したはずが顧客に確定と誤解される」実害は生じない。したがって
   矛盾検知起点の追加対応も不要と判断した。

## 結論

- フェーズ続き135で修正したnew_bookingの欠落は、`needs_owner_check`が「通常false・
  異常時のみtrue」という個別イベントの異常性を表すフラグとして使われている intentに
  固有の問題だった。
- faq/escalationは元々`needs_owner_check`込みで下流判定される設計のため対象外。
- cancel/changeは`needs_owner_check`が意味的に「常にtrue」であり個別の異常性を
  区別する情報を持たないため、フラグを無視して予約の実体状態で通知要否を判断する
  現行設計は見落としではなく合理的な選択と判断した。
- 以上により、new-booking-needs-owner-check-notification-design.md「残る課題」の
  intent横断点検はこれをもって完了とする。

## 副次的に見つかった軽微な記録漏れ

本点検の過程で、フェーズ続き135(2026-08-24 23:00 UTC、コミット9e8eaa2)の設計・実装
(new-booking-needs-owner-check-notification-design.md新規作成、engine.py・
cloud_function_process_event.py・テスト2ファイルの変更)がREADME.md「次にやること(候補)」
へのフェーズログ追記を伴わずにコミットされていたことに気づいた。本ドキュメントの
README追記と合わせて、フェーズ続き135のログを遡って追加した。
