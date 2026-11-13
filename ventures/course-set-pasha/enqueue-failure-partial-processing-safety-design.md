# Cloud Tasks enqueue失敗時のバッチ部分処理セーフティ設計

フェーズ373。process-memo-event-async-split-design.md(フェーズ370)・フェーズ372実装
(`dispatch_webhook_events()`のFAQ/非FAQ振り分け)のコードを読み直したところ、
`task_queue_client.create_task()`の例外処理が`TaskAlreadyExistsError`のみを捕捉し、
それ以外の例外(Cloud Tasks側のクォータ超過・一時的なネットワーク障害等)を一切
想定していない欠落に気づいた。本ドキュメントはそのギャップと対策を記録する。

## 発見したギャップ

`dispatch_webhook_events()`は`events`配列中の複数`message`イベントを1ループで処理する。
`task_queue_client`指定時、イベントごとに
`is_sync_faq_memo_event()`で経路2(同期FAQ reply)/経路3・4(非同期enqueue)へ振り分けるが、
enqueue対象イベントの`create_task()`が`TaskAlreadyExistsError`以外の例外を送出すると、
フェーズ372時点の実装ではその例外がそのまま`dispatch_webhook_events()`の外へ伝播していた。

これにより次の2つの問題が生じる。

1. **同一バッチ内の先行イベントの二重処理リスク**: `_mark_processed(message_events)`は
   `message_events`ループが例外なく完了した場合のみ呼ばれる(line-webhook-event-id-
   idempotency-design.md準拠)。ループ中盤でenqueue例外が発生すると、その直前に経路2で
   同期replyし終えていたFAQイベントも`webhook_event_id_store`へ未記録のままとなり、
   LINE Messaging API側のWebhook再送(署名検証失敗以外の5xx応答・タイムアウト時に
   発生する)によって同一バッチが再送された場合、既に送信済みのFAQ固定応答が重複して
   再送信されてしまう。
2. **後続イベントの未処理**: 例外伝播によりCloud Functionsハンドラ自体が異常終了するため、
   同バッチ内でenqueue例外発生イベントより後に並んでいた他のメモイベント(経路2・3/4
   いずれも)が一切処理されない。

## 採用方式

`create_task()`呼び出しを`TaskAlreadyExistsError`と「それ以外の`Exception`」の2段で
捕捉し、後者の場合は該当イベントを(enqueueせず)その場で`process_memo_event()`による
同期処理にフォールバックする。

- フォールバック時点では、`dispatch_webhook_events()`はまだ元のWebhook HTTPリクエスト
  処理の中にあり、各イベントの`replyToken`はLINE Messaging APIの有効期限
  (発行から一定時間)内である想定のため、同期replyへの切替は経路2(FAQ)と同じ前提で
  安全に行える。
- フォールバックしたイベントの`webhookEventId`は新設の
  `DispatchResult.enqueue_fallback_webhook_event_ids`に記録する。これにより
  `cloud-monitoring-alert-policy-design.md`側で「enqueue失敗率」を監視指標として
  追加する余地を残す(本フェーズでは監視設定自体は未着手)。
- 例外を握ることで後続イベントのループ処理は継続され、バッチ内の他イベントは通常通り
  処理される(問題2の解消)。
- `_mark_processed(message_events)`はループ全体が例外なく完了するようになるため、
  先行イベントの重複処理リスク(問題1)も解消される。

## 対象外・今後の課題

- Cloud Tasksの実運用では`create_task()`自体がリトライ機構(クライアントライブラリの
  デフォルト設定)を持つため、本設計が想定する「リトライを使い切った末の最終的な例外」
  がどの程度の頻度で発生するかは実デプロイ後でないと検証できない(実GCPプロジェクト
  作成はpending-approval.md 2026-11-08 08:00 UTC記載の運営方針判断待ち)。
- フォールバック発生時、本来「非同期・push応答」を想定していたイベントが「同期・reply
  応答」に切り替わる挙動の違いをユーザーに意識させないための文面側の配慮は、
  `process_memo_event()`側の既存の応答文言をそのまま使う前提とし、本フェーズでは
  新規の文言分岐は設けていない。
- `enqueue_fallback_webhook_event_ids`が実運用で非ゼロになり続ける場合(Cloud Tasks側の
  構成不備・権限不足等の恒常的な問題を示唆)のオーナー通知設計は、
  `blocked-but-billing-owner-notification-design.md`と同種の仕組みを横展開できる余地が
  あるが、本フェーズでは未着手(次回候補)。

## 実装・テスト

`prototype/cloud_function_webhook.py`の`dispatch_webhook_events()`に上記フォールバックを
実装し、`prototype/test_cloud_function_webhook.py`に次の2テストを追加した。

- `test_enqueue_transient_error_falls_back_to_sync_without_raising`: enqueue例外時に
  例外が伝播せず同期処理にフォールバックし、`enqueue_fallback_webhook_event_ids`に記録
  されることを確認。
- `test_enqueue_transient_error_does_not_block_other_events_in_batch`: 同一バッチ内の
  enqueue失敗イベントが、後続の正常イベントの処理(enqueue)を妨げないことを確認。

既存テスト(フェーズ372時点899件)と合わせて全901件・schema検証22件いずれもパスし、
回帰がないことを確認した。
