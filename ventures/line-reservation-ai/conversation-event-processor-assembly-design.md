# Cloud Function B: ConversationEventProcessor組み立ての結線設計

## 1. 背景・対応する残課題

conversation-state-wiring-design.md 6節に残っていた「引き続き残る課題」のうち、
「`build_conversation_flow_state_machine_for_store()`(フェーズ続き187)を実際に
Cloud Function Bのどこから呼ぶか(`handle_process_conversation_event()`が受け取る
`processor`自体をどう組み立てるか)の結線」に着手した。

`handle_process_conversation_event()`(cloud_function_process_event.py)は、呼び出し元が
既に構築済みの`ConversationEventProcessor`を受け取る前提のままで、「1件のCloud Tasks
ペイロード(`destination`を含む)から実際にどうやって1店舗分の`ConversationEventProcessor`
インスタンスを組み立てるか」という組み立て工程自体は、これまでどの関数にも実装されて
いなかった。

## 2. 現状把握: 組み立てに必要な部品の棚卸し

`ConversationEventProcessor.__init__`が要求する引数のうち、店舗ごとに異なる値を
どこから取得するかを整理すると以下の通りだった。

| 引数 | 取得元(想定) | 現状 |
|---|---|---|
| `store_id` | `resolve_store_id_from_destination(payload)` | 実装済み(store-id-resolution-and-owner-identity-design.md) |
| `flow`(`ConversationFlowStateMachine`) | `build_conversation_flow_state_machine_for_store(store_id, store)` | 実装済み(フェーズ続き187) |
| `owner_user_id` | `store.get_owner_user_id(store_id)` | 実装済み(StoreProfileStoreProtocol) |
| `menu_durations` | `store.get_menu_durations(store_id)` | **未実装(本フェーズで追加)** |
| `store_faq_info` | `store.get_store_faq_info(store_id)` | **未実装(本フェーズで追加)** |
| `searcher`(`AvailabilitySearcher`) | 店舗の営業時間・スロット間隔から構築 | **未実装(店舗ごとの営業時間データ自体がStoreProfileStoreProtocolに無い)** |
| `booking_slots`/`consolidator` | `flow._slots`/`flow._consolidator`を共有(`_demo()`と同じ考え方) | 既存パターンを流用可能 |
| `logs` | `flow`と共有する`NotificationLogAggregator`インスタンス | 既存パターンを流用可能 |
| `push_client` | 実LINE Messaging API接続(オーナー承認待ち) | 承認待ち、DIで差し替え可能な設計は既存 |
| `conversation_state_store`/`confirmed_reply_recorder`/`store_profile` | 実Firestore接続(オーナー承認待ち) | 承認待ち |

## 3. 本フェーズで対応した範囲

`menu_durations`・`store_faq_info`はプランや通知先メールアドレスと同じ「店舗プロフィールの
単純な読み書き」であり、実Firestore接続を必要とせず`StoreProfileStoreProtocol`の一部として
今すぐ設計・実装できると判断した。`get_owner_email()`/`set_owner_email()`と同じパターンで
`get_menu_durations()`/`set_menu_durations()`・`get_store_faq_info()`/`set_store_faq_info()`を
`StoreProfileStoreProtocol`・`InMemoryStoreProfileStore`に追加した(store_profile_store.py)。

- `get_menu_durations(store_id)`は未設定の店舗に対して`ConversationEventProcessor`の
  `menu_durations`引数と同じ「dict必須(Noneを許容しない)」制約に合わせ、`None`ではなく
  空dict`{}`を返す。
- `get_store_faq_info(store_id)`も同様に未設定時は空dictを返す(`ConversationEventProcessor.
  __init__`の`store_faq_info=None`時の`or {}`フォールバックと結果的に同じ挙動になる)。
- いずれも戻り値は内部dictのコピーを返す(呼び出し元が戻り値を変更してもストア内部の
  状態に影響しないようにするため。他フィールド(文字列・bool等)は不変値のため問題にならな
  かったが、dictを返す新規フィールドで初めて必要になった配慮)。

## 4. 引き続き残る課題

- `searcher`(`AvailabilitySearcher`)の組み立てに必要な店舗の営業時間・スロット間隔
  データは、weekday-specific-business-hours.md・business-hours-lunch-break.mdで
  曜日別・複数時間帯対応の設計が既にされているが、それを`StoreProfileStoreProtocol`
  経由でどう読み出すかはまだ未設計(単純なgetter 1つでは表現できない構造のため、
  別途データモデルの設計が必要)。
- 上記が揃った後、実際に`ConversationEventProcessor`を組み立てて`handle_process_
  conversation_event()`へ渡す最上位の組み立て関数(例:
  `build_conversation_event_processor_for_payload(payload, store, push_client, ...)`)
  自体はまだ実装していない。`push_client`・`conversation_state_store`等の実クラウド
  接続に依存する引数がある間は、組み立て関数を実装しても実際にCloud Functions上で
  動作させることはできないため、優先度は`searcher`組み立てロジックの設計より低いと
  判断した。
- 実際のFirestore接続(GCPプロジェクト作成、オーナー承認待ち)自体は引き続き残る課題。
