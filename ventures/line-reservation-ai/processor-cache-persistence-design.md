# Cloud Function B自身のユーザーごとローカルキャッシュの永続化(フェーズ続き190)

作成日: 2026-09-04(フェーズ続き190)

## 1. 背景・対応する残課題

conversation-state-wiring-design.md(フェーズ続き189)4節に、以下の残課題が残っていた。

> `ConversationEventProcessor`自身が持つuser_idごとのローカルキャッシュ
> (`_candidates_by_user`・`_held_label_by_user`・`_search_context_by_user`・
> `_pending_new_booking_context_by_user`)は、今回のhydrate/dehydrateの対象に含めておらず、
> 「キャッシュなし・毎回新規構築」の運用ではターンをまたぐたびに空になる。
> `ConversationFlowStateMachine`自体の状態遷移には影響しないが、顧客向け案内文言の一部
> (hold時・confirm時のメッセージに含める候補ラベル文字列)が空文字列になりうるという
> 顧客体験上のギャップが残る。

同md 4節が挙げていた対応方針の候補、(a)これら4キャッシュを`_ConversationState`
(engine.py側)に統合し`export_state_for_persistence()`/`import_state_from_persistence()`
自体を拡張する、(b)`ConversationEventProcessor`側に専用のhydrate/dehydrateペアを追加し
同じ`conversation_state_store`ドキュメントへ追記する、のうち本フェーズは**(b)を採用**した。
理由: これら4キャッシュはConversationFlowStateMachineクラスの責務(hold/confirm可否の
判定)ではなくConversationEventProcessorクラス固有の責務(案内文言の組み立て)に属する
値であり(同クラスdocstring参照)、engine.py側の`_ConversationState`・
`export_state_for_persistence()`のスキーマ(firestore-data-model.md 3節が「同メソッドの
実装が正」と明記)を変更するより、Firestoreドキュメントは共有しつつシリアライズ責務は
呼び出し元(cloud_function_process_event.py)に閉じておく方が変更範囲が小さく、
engine.py側のテスト・既存呼び出し元への影響も無い。

## 2. 実装

`prototype/cloud_function_process_event.py`の`ConversationEventProcessor`に以下を追加した。

### 2.1 `_export_processor_cache_for_user(user_id) -> Optional[dict]`

`_candidates_by_user`・`_held_label_by_user`・`_search_context_by_user`・
`_pending_new_booking_context_by_user`のうち、当該user_idにエントリがあるものだけを
`{candidates, heldLabel, searchContext, pendingNewBookingContext}`(いずれも省略可能な
サブキー)のplain dictへ変換する。`candidates`は`export_state_for_persistence()`の
`candidates`フィールドと同じ`{slotKey, label, startMinutes}`形式(`_slot_key_to_string()`を
再利用)。4つとも該当エントリが無ければNoneを返す。

### 2.2 `_import_processor_cache_for_user(user_id, data)`

上記の逆変換。`data`に含まれるサブキーのみ該当する4辞書へ書き戻す(存在しないサブキーは
何もしない)。

### 2.3 `_hydrate_conversation_state()` / `_persist_conversation_state()`の変更

- `_persist_conversation_state()`: `export_state_for_persistence()`(`_states`由来)と
  `_export_processor_cache_for_user()`(本フェーズの4キャッシュ由来)の両方を評価し、
  どちらか一方でも値があれば同じドキュメントへ`processorCache`キーとしてマージして
  `set()`する。両方Noneの場合のみ`delete()`する(従来はflow側がNoneなら常に`delete()`
  していたが、「flow側は空だがpendingNewBookingContextだけはある」ケース〈3節参照〉を
  保持できるようにするための変更)。
- `_hydrate_conversation_state()`: 読み出したドキュメントに`stage`キーがあれば従来通り
  `import_state_from_persistence()`を呼ぶ。`stage`キーが無い(=flow側のエントリが元々
  存在しなかった)場合は呼ばない(`import_state_from_persistence()`は`data["stage"]`を
  必須として参照するため、呼ぶと`KeyError`になる)。`processorCache`キーがあれば
  `_import_processor_cache_for_user()`を呼ぶ。

## 3. 実装中に再確認したエッジケース: `_states`にエントリが無いのに永続化が必要なケース

`_start_new_booking()`が「メニュー未言及」で聞き返す分岐は、`present_candidates()`を
一度も呼ばないまま`_pending_new_booking_context_by_user[user_id]`だけを設定して返る
(cloud_function_process_event.py参照)。このケースでは`flow._states`に当該user_idの
エントリが無いため`export_state_for_persistence()`はNoneを返すが、
`_pending_new_booking_context_by_user`には値があるため`_export_processor_cache_for_user()`
はNoneを返さない。2.3節の変更により、この場合ドキュメントは`{processorCache:
{pendingNewBookingContext: {...}}}`(`stage`キー無し)としてそのまま永続化される
(firestore-data-model.md 3節に追記)。

対応するテスト
(`test_pending_new_booking_context_persists_without_flow_state`)で、この形の
ドキュメントが正しく書き込まれ、次ターンの全く新規のインスタンスで正しく読み戻され
`_merge_pending_new_booking_context()`が機能することを確認した。

## 4. テスト

`prototype/test_cloud_function_process_event.py`の`ConversationStateWiringTests`に
以下を追加・拡張した。

- `test_first_turn_with_no_persisted_document_behaves_as_fresh_conversation`: 候補提示後の
  永続化ドキュメントに`processorCache.candidates`・`processorCache.searchContext`が
  含まれ、`heldLabel`・`pendingNewBookingContext`は含まれないことを確認するよう拡張。
- `test_round_trip_persistence_across_fresh_state_machine_instances`: 2ターン目・3ターン目を
  それぞれ完全に独立した(=`_candidates_by_user`等のローカルキャッシュを一切共有しない)
  processorインスタンスで処理した際に、hold時・confirm時の案内文言に含まれる候補ラベルが
  空文字列にならず正しく復元されることを確認するよう拡張(本フェーズが解消する顧客体験上の
  ギャップの直接テスト)。
- `test_pending_new_booking_context_persists_without_flow_state`(新規): 3節のエッジケースの
  直接テスト。

venture全体(`python3 -m unittest discover -s prototype -p "test_*.py"`)679件全件パス・
schema検証(`python3 schema/validate_test_cases.py`)25件全件パスを確認した。

## 5. 引き続き残る課題

- `BookingSlotManager`/`NotificationLogAggregator`/`EscalationConsolidator`のhydrate/
  dehydrate要否の検討(conversation-state-persistence-design.md 4節から持ち越し、未変更)。
- `build_conversation_flow_state_machine_for_store()`(フェーズ続き187)を実際にCloud
  Function Bのどこから呼ぶかの結線(conversation-state-wiring-design.md 6節から持ち越し、
  未変更)。
- 実際のFirestore接続(GCPプロジェクト作成、オーナー承認待ち)自体は引き続き残る課題。
