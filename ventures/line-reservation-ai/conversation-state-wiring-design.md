# 会話状態hydrate/dehydrateの呼び出し配線設計(フェーズ続き189)

作成日: 2026-09-04(フェーズ続き189)

## 1. 背景・対応する残課題

conversation-state-persistence-design.md(フェーズ続き188)2節・
conversation-flow-construction-design.md(フェーズ続き187)4節の両方に、同じ理由
(キャッシュ有無の判断が未確定)で共通して残っていた以下の課題に対応する。

> `build_conversation_flow_state_machine_for_store()`と
> `export_state_for_persistence()`/`import_state_from_persistence()`を実際にどこから
> (Cloud Function Bの処理冒頭でget()→import、処理末尾でexport→set、という組み合わせに
> なる見込み)呼ぶ配線自体は、店舗単位で`ConversationFlowStateMachine`インスタンスを
> キャッシュするか毎回新規構築するかの判断が未確定なままのため、次回以降の課題として残る。

## 2. 決定: インスタンス内キャッシュを採用しない(毎回新規構築)

conversation-state-persistence-design.md 2節が指摘していた通り、firestore-data-model.md
3節が前提とする「Cloud Functions側でLINE Webhook受信のたびに処理する」構成は、HTTP起動の
Cloud Functionsインスタンスがウォームスタートを保証されない。ウォームスタート時のみ有効な
インスタンス内キャッシュ(TTL数分)を仮に実装しても、コールドスタート時には効果が無く、
「キャッシュがあることを前提にした実装」と「キャッシュが無い場合のフォールバック実装」の
2通りを両方正しく動かす必要が生じ複雑化する。

一方、本フェーズまでに`export_state_for_persistence()`/`import_state_from_persistence()`
(フェーズ続き188)・`build_conversation_flow_state_machine_for_store()`(フェーズ続き187)
という、hydrate/dehydrateに必要な部品は既に安価に呼べる状態で揃っている。キャッシュを
挟まなくても「呼び出しのたびに`ConversationFlowStateMachine`を新規構築し、対象ユーザーの
会話状態だけをFirestoreから読んで復元し、処理後に書き戻す」という設計で正しく動作し、
実装・検証すべき経路が1通りで済む。

よって本フェーズでは、**インスタンス内キャッシュは採用せず、`ConversationEventProcessor.
process()`の呼び出しのたびに(=1 Cloud Tasksタスク=1メッセージイベントの処理のたびに)、
対象ユーザーの会話状態をFirestoreドキュメントからhydrateし、処理完了後にdehydrateして
書き戻す**方式を採用する。`ConversationFlowStateMachine`自体を毎回新規構築するかどうか
(=`build_conversation_flow_state_machine_for_store()`をどこで呼ぶか)は、本フェーズの
対象である「1ユーザー分の会話状態(`_states[user_id]`)のhydrate/dehydrate」とは独立した
話であり(店舗プロフィール由来の`monthly_booking_limit`の再取得コストの話でしかない)、
今回はCloud Function Bのエントリポイント自体(`handle_process_conversation_event()`が
`processor`を受け取る前提のまま)を変更しないため、`build_conversation_flow_state_machine_
for_store()`をどこから呼ぶかの結線は引き続き別課題として残す(6節)。

## 3. 決定: `ConversationEventProcessor`にhydrate/dehydrateを内蔵する

`prototype/cloud_function_process_event.py`に以下を追加した。

### 3.1 `ConversationStateStoreProtocol` / `InMemoryConversationStateStore`

`LinePushClient`/`ConfirmedReplyRecorder`/`OwnerFollowStatusStoreProtocol`と同じ
「実クライアントとInMemory版の共通インターフェース」パターンを踏襲した、
`stores/{storeId}/conversations/{sessionId}`ドキュメント1件分のget/set/deleteのみを
要求する最小Protocol。

```python
class ConversationStateStoreProtocol(Protocol):
    def get(self, store_id: str, user_id: str) -> Optional[dict]: ...
    def set(self, store_id: str, user_id: str, data: dict) -> None: ...
    def delete(self, store_id: str, user_id: str) -> None: ...
```

`delete()`を要求するのは、`cancel_booking()`/`change_booking()`が`_states`から当該
エントリを削除した結果`export_state_for_persistence()`がNoneを返すケース(2節参照)に
対応するため。`InMemoryConversationStateStore`は`dict[(store_id, user_id), dict]`で
これを模した検証用実装。実装時は実Firestoreクライアントの`get()`/`set()`/`delete()`
呼び出しに差し替えるだけで動作する設計。

### 3.2 `ConversationEventProcessor`の変更

コンストラクタに`conversation_state_store: Optional[ConversationStateStoreProtocol] =
None`を追加した(未指定時は従来通り何もしない後方互換、`confirmed_reply_recorder`等
既存の任意引数と同じパターン)。

`process()`を以下のように分割した。

- `process(event, llm_call, now, tone)`: `event`から`user_id`を取り出し検証した後、
  `_hydrate_conversation_state(user_id)` → `_process_message_event(user_id, event,
  llm_call, now, tone)`(従来の`process()`本体をそのまま移した内部メソッド) →
  `_persist_conversation_state(user_id)`の順に呼ぶ薄いラッパー。
- `_hydrate_conversation_state(user_id)`: `conversation_state_store.get(store_id,
  user_id)`を読み、ドキュメントがあれば`flow.import_state_from_persistence(user_id,
  store_id, data)`を呼ぶ。無ければ(初回会話・アイドル失効後の再会話等)何もしない。
- `_persist_conversation_state(user_id)`: `flow.export_state_for_persistence(user_id)`
  の結果が`dict`なら`conversation_state_store.set(...)`、`None`なら
  `conversation_state_store.delete(...)`。

`_process_message_event()`が例外を送出した場合、`_persist_conversation_state()`は
呼ばれない(書き戻しをスキップする)。`handle_process_conversation_event()`は例外を
`status_code=500`へ正規化しCloud Tasksに再試行させる設計(既存実装)のため、次回の
再試行時は直近の正常完了時点の永続化済み状態から改めてhydrateすれば良く、失敗した
処理途中の不完全な状態を書き戻さない方が安全側になる。

follow/unfollowイベント(`process_follow_event()`/`process_unfollow_event()`)は
`ConversationFlowStateMachine`の状態を参照・変更しないため、hydrate/dehydrateの対象に
含めていない。

## 4. 実装中に発見した残課題: Cloud Function B自身が持つユーザーごとのローカルキャッシュ

実装・テストの過程で、`ConversationEventProcessor`自身が持つ以下4つのuser_idごとの
ローカルキャッシュ(`_states`とは別に、Bが顧客への案内文言を組み立てるためだけに
保持している値)が、今回のhydrate/dehydrateの対象に含まれていないことに気づいた。

- `_candidates_by_user`: 直近提示した候補一覧(hold時の案内文言の候補ラベル用)。
- `_held_label_by_user`: holdした枠のラベル(confirm時の予約内容ラベル用)。
- `_search_context_by_user`: 直近の空き枠検索条件(確定操作競合時の再検索・メニュー名の
  ターン間引き継ぎ用)。
- `_pending_new_booking_context_by_user`: メニュー未言及時の聞き返し中に保持する
  日時範囲等(次ターンへの引き継ぎ用)。

いずれも`ConversationEventProcessor`クラスのdocstringが元々
「実装ではFirestoreの会話状態ドキュメントに含める想定」と述べていた箇所に相当する
(cloud_function_process_event.py参照)。2節で決定した「呼び出しのたびに新規インスタンスを
構築する」設計のもとでは、これらのキャッシュは`_states`と異なり本フェーズでは永続化
されないため、実際にCloud Functionsインスタンスがコールドスタートするたびに空になる。

**この影響の範囲**: `ConversationFlowStateMachine`自体の状態遷移(hold/confirm可否の
判定、すなわち`_states`のhydrate/dehydrateで正しく引き継がれる部分)には影響しない
(select_slot_from_reply()はFlow内部の`state.candidates`を使って正しく解決できるため)。
影響するのは顧客向け案内文言の一部表示(hold時・confirm時のメッセージに含める候補
ラベル文字列)のみで、これが空文字列になりうる(`ConversationEventProcessor.
_handle_candidate_selection()`/`_handle_details()`参照)。予約自体は正しく確定され、
実害(二重予約・誤確定等)は生じないが、顧客への案内文言の品質が本来より劣化する。

**本フェーズでは対応しない**: このギャップの解消(上記4キャッシュも`_states`と同様に
Firestoreドキュメントへ含めてhydrate/dehydrateする設計)は、本フェーズのスコープ
(`_states`自体の呼び出し配線)を超えるため、次回以降の課題として切り出して残す。
対応方針の候補としては、(a)これら4キャッシュの内容を`_ConversationState`
(engine.py側)に統合し`export_state_for_persistence()`/`import_state_from_persistence()`
自体を拡張する、(b)`ConversationEventProcessor`側に専用のhydrate/dehydrateペアを
追加し同じ`conversation_state_store`ドキュメントへ追記する、の2通りが考えられ、
次回以降どちらが適切か検討する。

## 5. テスト

`prototype/test_cloud_function_process_event.py`に`ConversationStateWiringTests`を
追加した。

- 初回会話(永続化済みドキュメントが無い)の場合、従来通り新規会話として扱われ、
  処理完了後に`export_state_for_persistence()`相当のdictが正しく書き込まれること。
- 3つの完全に独立した`ConversationEventProcessor`/`ConversationFlowStateMachine`
  インスタンス(ただし同じ`conversation_state_store`と`BookingSlotManager`を共有、
  「キャッシュなし・毎回新規構築」を再現)にまたがって、候補提示→hold→confirmの
  3ターンの会話が正しく継続できること(各インスタンスは処理開始時点で`flow.stage()`が
  `None`であることを確認した上で処理し、hydrateにより正しい状態から再開できることを
  検証)。
- `cancel_booking()`で`_states`のエントリが削除された場合、永続化側の
  ドキュメントも`delete()`されること。
- `conversation_state_store`未指定(None)時は従来通りhydrate/dehydrateを行わない
  (既存呼び出し元・テストへの後方互換)こと。

venture全体678件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`)
パス・schema検証25件(`python3 schema/validate_test_cases.py`)パスを確認した。

## 6. 引き続き残る課題

- 4節の「Cloud Function B自身が持つユーザーごとのローカルキャッシュ」の永続化。
- `build_conversation_flow_state_machine_for_store()`(フェーズ続き187)を実際に
  Cloud Function Bのどこから呼ぶか(`handle_process_conversation_event()`が受け取る
  `processor`自体をどう組み立てるか)の結線。本フェーズは`processor`が既に構築済みで
  あることを前提にした`ConversationEventProcessor`内部の配線のみを対象にしたため、
  エントリポイント自体の変更は行っていない。
- `BookingSlotManager`/`NotificationLogAggregator`/`EscalationConsolidator`の
  hydrate/dehydrate要否の検討(conversation-state-persistence-design.md 4節から
  持ち越し、未変更)。
- 実際のFirestore接続(GCPプロジェクト作成、オーナー承認待ち)自体は引き続き残る課題。
