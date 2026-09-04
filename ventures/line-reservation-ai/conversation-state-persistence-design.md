# 会話状態(_states)の永続化用hydrate/dehydrate設計(フェーズ続き188)

作成日: 2026-09-04(フェーズ続き188)

## 1. 背景・対応する残課題

conversation-flow-construction-design.md(フェーズ続き187)4節に、本フェーズの対象外
として明示的に残されていた2つの課題のうち、以下を切り出して対応する。

> 会話状態(`_states`)自体をFirestoreドキュメントとの間でhydrate/dehydrateする方式
> (`ConversationEventProcessor`のdocstringが「実装ではFirestoreの会話状態ドキュメントに
> 含める想定」と述べている部分)は、本フェーズの対象外のまま残る。

もう1つの課題(`build_conversation_flow_state_machine_for_store()`を実際にどこから・
どのタイミングで呼ぶか)は、2節で述べる理由により本フェーズでも決定せず、次回以降の
課題として残す。

## 2. 「呼び出しタイミング」自体は本フェーズで決めない

firestore-data-model.md 3節はもともと「Cloud Functions側でLINE Webhook受信のたびに
`lastActivityAt`が閾値を超えたドキュメントをクエリして処理する」という便乗トリガー方式
(idle-conversation-trigger-design.md)を前提にしており、HTTP起動のCloud Functionsは
インスタンスの温存(ウォームスタート)が保証されないため、そもそも店舗単位で
`ConversationFlowStateMachine`インスタンスをプロセス間キャッシュする設計とは相性が
良くない。とはいえ「その場合でもインスタンス内キャッシュ(TTL数分)を挟む余地がある」
という記述(1節、`stores/{storeId}`ドキュメントについて)もあり、キャッシュ有無の
最終判断はまだ下していない。

本フェーズは、conversation-flow-construction-design.md 2節と同じ理由(キャッシュ有無の
判断がどちらに転んでも、hydrate/dehydrateという最小単位の処理自体は共通して必要)で、
この判断を待たずに先に着手できる部分だけを切り出す。

## 3. 決定: `ConversationFlowStateMachine`にhydrate/dehydrateメソッドを新設

`prototype/engine.py`の`ConversationFlowStateMachine`に以下の2メソッドを追加した。

- `export_state_for_persistence(user_id) -> Optional[dict]`: `_states[user_id]`を
  firestore-data-model.md 3節のスキーマに一致するplain dictへ変換する。該当する状態が
  無ければ`None`。
- `import_state_from_persistence(user_id, store_id, data) -> None`: 上記の逆変換。
  `data`はFirestoreドキュメントを読み取ったplain dict(スキーマは同一)を想定する。

いずれも実際のFirestore読み書き(`get()`/`set()`)自体は呼び出し側(Cloud Function B)の
責務とし、ここではdictとの相互変換のみを担う(`build_conversation_flow_state_machine_for_store()`
と同じ「結線点を切り出すヘルパー」という位置づけ)。

### slot_keyの形式変換

engine.py内部の`slot_key`は`(store_id, date_str, time_str)`の3要素タプルだが、
firestore-data-model.mdの`slotKey`文字列(`"2026-08-09_15:30"`)はドキュメントパス
(`stores/{storeId}/conversations/{sessionId}`)自体に`storeId`を含むため`storeId`を
持たない。モジュール関数`_slot_key_to_string()`/`_slot_key_from_string()`で相互変換する。
`import_state_from_persistence()`が`store_id`引数を取るのはこのため
(呼び出し側はドキュメントパスの`storeId`をそのまま渡す想定)。

### スキーマの記載漏れ2件を発見・修正

実装の過程で、firestore-data-model.md 3節に以下2フィールドの記載が漏れていたことが
判明し、あわせて追記した(詳細は同ファイル参照)。

- `emojiUsedLast`: `consume_casual_emoji_allowance()`が参照する内部状態
  (`_ConversationState.emoji_used_last`)。message-tone-variants.mdの絵文字頻度上限の
  判定に必要だが、当初のスキーマに含まれていなかった。
- `candidates[].startMinutes`: `_Candidate.start_minutes`。`slotKey`・`label`のみ
  記載されており、当初のスキーマから漏れていた(現状`export_state_for_persistence()`は
  この値を単に運搬するだけで、復元後のロジックがすぐに参照するわけではないが、
  `_Candidate`の全フィールドを欠落なく往復させるため含めた)。

## 4. 本フェーズでは対応しない範囲(引き続き残る課題)

- `build_conversation_flow_state_machine_for_store()`(フェーズ続き187)と
  今回のhydrate/dehydrateを実際にどこから(Cloud Function Bの処理冒頭で
  `get()`→`import_state_from_persistence()`、処理末尾で`export_state_for_persistence()`
  →`set()`、という組み合わせになる見込み)呼ぶ配線自体は、2節で述べたキャッシュ有無の
  判断が未確定なままのため、次回以降の課題として残る。
- `BookingSlotManager`(`stores/{storeId}/bookingSlots/{slotKey}`)・
  `NotificationLogAggregator`(`stores/{storeId}/notificationLogEntries/{autoId}`)・
  `EscalationConsolidator`(`stores/{storeId}/escalationWindows/{sessionId}`)は
  それぞれ別コレクションとして設計済み(firestore-data-model.md 2・4・5節)だが、
  これらの内部状態についても同様のhydrate/dehydrateメソッドが必要かどうかは未検討。
  会話状態(本フェーズ)と異なり、これらは基本的に「1操作=1ドキュメントへの
  読み書き」で完結する設計(hold()/confirm()がトランザクション内で完結する、
  firestore-transaction-design.md参照)のため、`_states`辞書のような
  「複数フィールドをまとめてメモリに保持し、後でまとめて書き戻す」形の変換が
  同じ形で必要になるとは限らない。次回以降、個別に要否を検討する。
- 実際のFirestore接続(GCPプロジェクト作成、オーナー承認待ち)自体は引き続き
  残る課題。

## 5. テスト

`prototype/test_engine.py`に`ConversationStatePersistenceTest`を追加した。
- 状態未作成時に`export_state_for_persistence()`が`None`を返すこと。
- `candidates_presented`ステージ(候補一覧つき)の往復変換、復元後に通常の
  `select_slot()`フローがそのまま使えること。
- `awaiting_details`→`confirmed`ステージの往復変換(`BookingSlotManager`の保留状態は
  別コレクションのため、テストでは同じ店舗の`slots`インスタンスを共有する想定で検証)。
- `reconfirmCount`・`emojiUsedLast`を含まない最小限のdict(過去バージョンとの
  後方互換)からの復元。
- `emojiUsedLast`の往復変換。
