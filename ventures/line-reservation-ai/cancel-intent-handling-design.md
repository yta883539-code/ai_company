# cancel intentの一次処理設計

作成日: 2026-08-02

## 背景
README.mdの「次にやること」で繰り返し残課題として挙げていた「cancel/change intentの実処理」のうち、
今回は`cancel`(顧客都合でのキャンセル申し出)のみを対象に設計・実装する。`change`(日時変更)は
「キャンセル+新規予約」より複雑な状態遷移(旧枠の解放と新枠のhold/confirmを1回の会話でどう
つなぐか)を要するため、今回はスコープに含めず、次回以降の課題として残す。

現状(intent-to-flow-mapping.md・prototype/cloud_function_process_event.pyのモジュールdocstring
「実装範囲」参照)、`cancel`/`change` intentはいずれも予約フロー外として
`EscalationConsolidator.on_event()`への転送のみが行われ、`BookingSlotManager`側の枠は
一切解放されない。このため顧客が「やっぱりキャンセルします」と伝えても、内部的には枠が
埋まったまま(pendingまたはconfirmed)になり、他の顧客に再提示されない不具合状態にあった。

## 対応方針: `ConversationFlowStateMachine.cancel_booking(user_id, now)`の新設

顧客の会話状態(`_ConversationState.stage`)に応じて処理を分岐する。

| 直前のstage | 処理 | オーナーへの通知 |
|---|---|---|
| 状態なし(`None`、または既にarchive_completed_conversations()で間引かれた過去の確定予約) | 何もrelease()する対象が無い。エンジンの会話メモリだけでは実在の予約有無を確定できないため、安全側でオーナーへ転送する | あり(`escalation_reason="cancel_not_found"`) |
| `candidates_presented` | まだ`hold()`していない(候補提示しただけ)ため、取り消す実体的な枠が無い。会話状態のみ削除する | なし(オーナー側の予約記録にまだ何も存在しないため) |
| `awaiting_details` | pending状態のholdを`BookingSlotManager.release()`で解放し、会話状態を削除する。pendingの時点ではオーナー側の外部予約記録(スプレッドシート等)にもまだ載っていない想定のため、confirmedと同列には扱わない | なし |
| `confirmed` | 確定済みの枠を`release()`し、会話状態を削除する。オーナー側の外部予約記録には既に確定予約として載っているため、どの枠が顧客都合でキャンセルされたかをオーナーが手動で反映できるよう通知する | あり(`escalation_reason="booking_cancelled"`、`slot_key`・`name`を添える) |

「状態なし」のケースをオーナー転送にしたのは、本エンジンの会話メモリ(`_states`)はプロセス内の
一時的なものであり(実装時はFirestore等への永続化を想定、firestore-data-model.md参照)、
`archive_completed_conversations()`で来店日の翌日以降は確定予約の状態も間引かれるため、
「本当に予約が存在しないのか」「単に会話状態が失効/未読み込みなだけなのか」をエンジン単体では
区別できないため。誤って「予約はありません」と即答してクレームになるより、オーナーに一次確認を
委ねる安全側を選んだ(faq-response-templates.mdの「未登録・一部未入力のケース」と同じ考え方)。

`candidates_presented`/`awaiting_details`をオーナー通知の対象外にしたのは、この段階では
オーナー側の外部予約記録(手動確認が必要な確定予約一覧)に何も反映されていないため、
通知してもオーナーが確認すべき実体が無く、通知過多(escalation-consolidation-logic.mdが
警戒している状態)を招くだけと判断したため。

## 顧客への返信文言

`format_cancel_confirmed_message()`(確定済み予約のキャンセル)・`format_cancel_pending_message()`
(候補提示中/仮押さえ中のキャンセル)・`format_cancel_not_found_message()`(該当予約なし)の
3種を新設し、いずれもmessage-tone-variants.mdの3トーン(formal/standard/casual)に対応する
(`_render_by_tone()`を流用)。

## escalation_reasonのenum拡張

`booking_cancelled`・`cancel_not_found`は、`booking_conflict`・`candidate_selection_unresolved`と
同様にLLM構造化出力ではなくシステム内部から発火するイベントのため、`booking_output.schema.json`の
enumには追加しない。`engine.py`の`SYSTEM_ESCALATION_REASONS`に追加し、
`NotificationLogAggregator`側で一般相談(consultation)とは別枠に振り分けられるようにした。

なお、`booking_conflict`・`candidate_selection_unresolved`は現状でも実際の
`ConversationEventProcessor.process()`からは`NotificationLogAggregator.record()`に一切渡っておらず
(`_logs.record()`は関数冒頭のLLM出力に対してのみ呼ばれ、内部生成イベントには呼ばれていない)、
`_demo()`内のスタンドアロン実演でのみ両者が揃って呼ばれている。今回追加する2つの理由も同じ
既存のギャップを引き継ぐ(今回新たに作った問題ではないため、このギャップの解消は別途の課題として
残す)。

## 残る課題
- `change` intent(日時変更)の設計・実装
- 上記「システム内部イベントが`NotificationLogAggregator`に実際には記録されない」ギャップの解消
- 実LLM/実LINE API接続自体(オーナー承認待ち、pending-approval.md参照)
