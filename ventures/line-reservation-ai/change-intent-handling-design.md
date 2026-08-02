# change intentの一次処理設計

作成日: 2026-08-02

## 背景
cancel-intent-handling-design.mdの残課題として明示的に残していた`change`(日時変更)の
実処理を設計・実装する。同ドキュメントが指摘していたとおり、`change`は「キャンセル+新規予約」
より複雑な状態遷移(旧枠の解放と新枠のhold/confirmを1回の会話でどうつなぐか)を要するが、
`cancel_booking()`実装によって「旧枠の解放」部分は既に部品として存在するため、これを
再利用しつつ「新規予約フローの開始」部分(`_start_new_booking()`)へそのままつなぐ設計とした。

booking_output.schema.jsonは実は本ドキュメント着手前から`change`を`new_booking`と同様に
`requested_date_range`/`time_of_day_preference`を伴い得るintentとして設計済みだった
(両フィールドの説明文に「intentがnew_booking/changeで日付の手がかりがある場合」と
明記されている)。つまりスキーマ側は「変更後の希望日時」をLLMが`change`発話から
抽出することを既に想定しており、今回の設計はそれを実際に接続しただけと言える。

## 対応方針: `ConversationFlowStateMachine.change_booking(user_id, now)`の新設

`cancel_booking()`と全く同じ分岐(stageに応じたrelease()・confirmed分のみオーナー通知)を
行うが、決定的に異なる点が1つある: **`cancel_booking()`は会話を終了させるが、
`change_booking()`は呼び出し側が続けて新規予約フローを開始する前提で、会話状態の削除のみを
行い顧客への最終的な返信はしない**(その後の`present_candidates()`呼び出しに委ねる)。

| 直前のstage | 処理 | オーナーへの通知 |
|---|---|---|
| 状態なし | `cancel_booking()`と同じくfound=Falseを返す。呼び出し側で安全側のオーナー転送を行う | あり(`escalation_reason="change_not_found"`、呼び出し側で発火) |
| `candidates_presented` | まだhold()していないため取り消す実体が無い。会話状態のみ削除し、そのまま新規候補検索へ進む | なし |
| `awaiting_details` | pending状態のholdを`release()`し、会話状態を削除してから新規候補検索へ進む | なし(cancelと同じ理由: オーナー側の外部予約記録にまだ何も載っていないため) |
| `confirmed` | 確定済みの枠を`release()`し、会話状態を削除してから新規候補検索へ進む | あり(`escalation_reason="booking_change_started"`、`slot_key`・`name`を添える) |

`escalation_reason`を`cancel_booking()`の`booking_cancelled`ではなく`booking_change_started`と
分けたのは、オーナーが「単純なキャンセル(顧客が来なくなった)」と「日時変更手続き中
(顧客は引き続き来店する意思がある)」を通知の時点で区別できるようにするため。
`change_not_found`も同様に`cancel_not_found`と分け、オーナーが「何のために予約状況を
確認してほしいのか(キャンセルの申し出か、変更の申し出か)」を見分けられるようにした。

## 呼び出し側(Cloud Function B)の接続: 「解放」+「新規予約フロー開始」の合成

`ConversationEventProcessor._handle_change()`は次の順で処理する。

1. `change_booking()`を呼び、旧枠を解放する。
2. `found=False`の場合、`cancel`のnot_foundパターンと同じくオーナーへ転送し、
   `format_change_not_found_message()`を送って終了する。
3. `found=True`かつ直前のstageが`awaiting_details`/`confirmed`だった場合、
   `format_change_started_message()`で「旧予約を取り消した」旨を案内する
   (`candidates_presented`だった場合は解放すべき実体が無いため、この案内はスキップする。
   cancelの`format_cancel_pending_message()`と同様の考え方)。
4. その後、`_start_new_booking(user_id, output, now)`をそのまま呼ぶ。これは`intent: new_booking`が
   来た場合と全く同じ処理(メニュー所要時間解決 → `search_candidates_from_llm_output()` →
   `present_candidates()` → 候補一覧送信)であり、`change`のLLM出力に含まれる
   `requested_date_range`/`time_of_day_preference`/`menu`をそのまま入力として使う。

この設計により、`change`は「1つの会話ターンの中で `cancel_booking()` → `present_candidates()`
(実質的な `new_booking` フローの開始)を連続実行するだけ」というシンプルな合成として
実装でき、新しいステートマシンの分岐を増やさずに済んだ。新しい日時の候補提示以降
(候補選択・氏名/メニュー確定)は既存の`new_booking`フローがそのまま再利用される
(呼び出し側は`change`固有の後続処理を一切持たない)。

## 検討したが採用しなかった案

**案: `change`専用の中間ステージ(例: `changing_awaiting_new_slot`)を新設する。**
旧予約の情報(旧slot_key等)を新しい予約が確定するまで会話状態に保持しておき、
万が一新しい日時選定の途中で顧客が離脱した場合に「元の予約はどうなったか」を
再現しやすくする案。しかし、`release_idle_conversations()`は既に`candidates_presented`/
`awaiting_details`の無応答離脱をエンジンの通知なしで許容している(candidates-expired-
notification-design.md)ため、`change`用に離脱時の特別な救済ロジックを追加するのは
複雑化に見合わないと判断した。旧予約が`confirmed`だった場合は`change_booking()`の時点で
既にオーナーへ通知済み(`booking_change_started`)であり、その後の顧客都合の離脱で
新しい予約が成立しなかった場合は、通常の候補提示離脱と同様にオーナー側の外部予約記録の
手動確認に委ねる(元々`confirmed`分のキャンセルもオーナーが手動で外部記録を更新する
前提であり、この点は既存のcancelフローと同じ運用コストで済む)。

## 顧客への返信文言

`format_change_started_message()`(旧予約の取り消し案内。直後に新しい候補一覧が続くことを
前提に「改めてご希望の日時を教えてください」という前振りで終える)・
`format_change_not_found_message()`(該当予約なし)の2種を新設し、いずれも
message-tone-variants.mdの3トーン(formal/standard/casual)に対応する(`_render_by_tone()`を流用)。

## escalation_reasonのenum拡張

`booking_change_started`・`change_not_found`は`booking_cancelled`・`cancel_not_found`と同様
LLM構造化出力ではなくシステム内部から発火するイベントのため、`booking_output.schema.json`の
enumには追加しない。`engine.py`の`SYSTEM_ESCALATION_REASONS`に追加し、
`NotificationLogAggregator`側で一般相談(consultation)とは別枠に振り分けられるようにした
(cancel-intent-handling-design.mdが指摘していた「システム内部イベントが
`NotificationLogAggregator`に実際には記録されない」ギャップは今回も引き継いでいる。
このギャップの解消は引き続き別途の課題として残す)。

## 追記(2026-08-02 18:00 UTC): change後の新規候補検索0件時の文言出し分け

上記で残課題としていた、`change`後の新規候補検索が0件だった場合の顧客向け文言の出し分けに
対応した。`_start_new_booking()`に`change_context: bool`引数を追加し、`change`経由かつ
実際に旧予約を解放した(直前stageが`awaiting_details`/`confirmed`で
`format_change_started_message()`を送った)場合のみ、通常の`REASK_DATE_RANGE_MESSAGE`ではなく
「以前のご予約は取り消し済みです」旨を含む`CHANGE_NO_CANDIDATES_MESSAGE`を送るようにした
(`prototype/cloud_function_process_event.py`)。

直前stageが`candidates_presented`だった場合(まだhold()していないため実際には何も
解放していない)は`change_context=False`のまま通常の文言を使う設計とした。この場合に
change専用文言を出すと「以前のご予約は取り消し済みです」という一文が事実と異なってしまう
(そもそも取り消すべき実体が無かった)ため。テスト2件追加(change後に旧予約を解放していた
場合/していなかった場合それぞれで0件になるケース)・既存分含め全119件パス。

## 残る課題
- 上記「システム内部イベントが`NotificationLogAggregator`に実際には記録されない」ギャップの解消
  (cancel-intent-handling-design.mdからの継続課題)
- 実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち、pending-approval.md参照)
