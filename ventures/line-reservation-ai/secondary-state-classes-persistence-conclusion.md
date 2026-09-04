# BookingSlotManager/NotificationLogAggregator/EscalationConsolidatorの hydrate/dehydrate 要否 結論

conversation-state-persistence-design.md 4節・processor-cache-persistence-design.md 5節に
「次回以降、個別に要否を検討する」として残っていた残課題(`BookingSlotManager`・
`NotificationLogAggregator`・`EscalationConsolidator`の内部状態にも
`ConversationFlowStateMachine`と同様のhydrate/dehydrateメソッドが必要かどうか)について、
実際には既存の2つの設計ドキュメント(firestore-transaction-design.md・
firestore-data-model.md 4節)が、この3クラスとも**hydrate/dehydrateという形自体が
不要である**という結論を既に出していたことを確認した。以下に3クラスそれぞれの根拠を
整理し、残課題を解消済みとする。

## なぜ`ConversationFlowStateMachine`にはhydrate/dehydrateが必要だったか(再確認)

`ConversationFlowStateMachine._states`は、1回のCloud Function呼び出し(1メッセージ受信)の
「読み込み→(会話ロジックの実行、複数フィールド`stage`・`candidates`・`heldLabel`等を
インメモリで書き換え)→まとめて書き戻し」という一括の read-modify-write を、
呼び出しの都度Firestoreドキュメント全体に対して行う必要があった。このため
「複数フィールドをドキュメントの内部表現とインメモリの内部表現との間で相互変換する」
専用のexport/import関数(hydrate/dehydrate)が必要だった。

## `BookingSlotManager`・`EscalationConsolidator`: 不要(Firestoreトランザクションが代替)

firestore-transaction-design.mdが既に、`hold()`/`confirm()`(`BookingSlotManager`)と
`on_event()`(`EscalationConsolidator`)のいずれも「1回の呼び出し=1つのFirestore
トランザクション内で完結するread-modify-write」として設計済みである。

- `hold()`/`confirm()`: `slot_ref.get(transaction=...)`で対象ドキュメント1件のみを
  読み、同じトランザクション内で`set()`/`update()`する。呼び出しをまたいでインメモリに
  状態を保持する必要がない(`_slots: dict`という呼び出し間で共有されるインメモリ辞書
  そのものが、Firestore接続後は丸ごと不要になり、各メソッドが直接
  `firestore.transactional`関数を呼ぶだけの薄いラッパーに置き換わる)。
- `on_event()`: `window_ref.get(transaction=...)`→分岐→`set()`/`update()`も同型。
  `_windows: dict`も同様に丸ごと不要になる。

つまり、conversation stateのように「hydrateして複数フィールドをインメモリに展開し、
ビジネスロジックを実行してからまとめてdehydrateして書き戻す」という2段階の変換が
必要なのではなく、**インメモリの`_slots`/`_windows`辞書自体をFirestore
トランザクション呼び出しに置き換える**(hydrate/dehydrateという変換層を挟まず、
メソッドの内部実装をFirestoreクライアント呼び出しに差し替えるだけ)というのが
正しい移行の形である。これは残課題が問うていた「同様のhydrate/dehydrateメソッドが
必要か」という問いに対して「不要、ただし理由は"仕組みが違うから"」という明確な回答になる。

## `NotificationLogAggregator`: 不要(集計自体をFirestore側のクエリに委譲)

firestore-data-model.md 4節が既に、`NotificationLogAggregator`のインメモリ集計
(`_seen_topics`・`consultation_count`等のカウンタ)を、Firestore接続後は

1. `notificationLogEntries`への追記型(append-only)書き込み(読み込み不要、常に新規`set()`)
2. ユニーク化は`notificationLogUniqueTopics/{date}_{sessionId}_{topic}`という決定的な
   ドキュメントIDへの冪等な`set()`(存在チェックの読み込みすら不要、同じIDへの
   再書き込みは意味的に無害)
3. 件数の参照は書き込み時ではなく参照時に`count()`集約クエリで都度算出

という3つの操作に置き換える設計であることを既に示している。`_seen_topics`という
インメモリ集合や`consultation_count`等のインメモリカウンタは、呼び出しをまたいで
値を保持する必要そのものが無くなる(カウンタの「現在値」はいつでも`count()`クエリで
Firestore側から取得できるため、インメモリにキャッシュして再構築する意味がない)。
このため、hydrate/dehydrateという「呼び出しの前後でインメモリ状態を復元・保存する」
仕組みは、`BookingSlotManager`/`EscalationConsolidator`とはさらに異なる理由(そもそも
インメモリに状態を持たせる設計ではなくなる)で不要となる。

## 結論のまとめ

| クラス | インメモリ状態 | Firestore接続後の置き換え方 | hydrate/dehydrate要否 |
|---|---|---|---|
| `ConversationFlowStateMachine` | `_states`(複数フィールド) | 1呼び出しの前後でexport/importし呼び出し元がset() | **必要**(実装済み、conversation-state-wiring-design.md) |
| `BookingSlotManager` | `_slots` | メソッド内部を直接Firestoreトランザクションに置き換え | 不要(firestore-transaction-design.md) |
| `EscalationConsolidator` | `_windows` | 同上 | 不要(firestore-transaction-design.md) |
| `NotificationLogAggregator` | `_seen_topics`等のカウンタ | 書き込みは追記/冪等set、集計は都度count()クエリ | 不要(firestore-data-model.md 4節) |

## 本ドキュメントで新たに変更した実装

無し(既存設計の相互参照・結論の明文化のみ)。`prototype/engine.py`の3クラスの
実装・テストへの変更も無い(いずれもFirestore未接続のプロトタイプとして現状のまま
インメモリ辞書ベースの実装を維持し、実接続時に上記の置き換えを行う設計のみが
確定した状態)。

## 残課題

- 上記はいずれも机上設計であり、実際のFirestore接続(GCPプロジェクト作成、
  オーナー承認待ち)後に、`BookingSlotManager`/`EscalationConsolidator`の
  メソッドをFirestoreトランザクション呼び出しに、`NotificationLogAggregator`の
  `record()`相当のメソッドをFirestore書き込み+`count()`クエリ呼び出しに、
  それぞれ実際に置き換える実装作業自体は引き続き残る。
- `build_conversation_flow_state_machine_for_store()`(フェーズ続き187)を実際に
  Cloud Function Bのどこから呼ぶかの結線(conversation-state-wiring-design.md 6節・
  processor-cache-persistence-design.md 5節から持ち越し、未変更)。
