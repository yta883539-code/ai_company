# Cloud Function A(Webhook受信ハンドラ)の実装

## 位置づけ
webhook-async-processing-design.mdの残課題「実装(Cloud Function Aのハンドラコード)自体は
引き続きGCPプロジェクト作成(オーナー承認待ち)後の着手」について、実際のGCPプロジェクト作成・
デプロイ(アカウント作成に該当し引き続きオーナー承認待ち)とは切り離せる範囲――**ハンドラの
判断ロジック自体**――を先に実行可能なコードに落とし込んだ。engine.pyがLLM呼び出しを
`llm_call`スタブとして差し替え可能にしたのと同じ考え方で、Cloud Tasksクライアントを
`TaskQueueClient`プロトコルとして差し替え可能にしてある。

## 実装したもの(`prototype/cloud_function_webhook.py`)
- `verify_line_signature()`: `X-Line-Signature`のHMAC-SHA256 + Base64検証。Python標準ライブラリ
  (hmac/hashlib/base64)のみで完結するため実装まで行った。チャネルシークレット自体はLINE公式
  アカウント開設(アカウント作成、オーナー承認待ち)後に得られる値のため、実際の検証はその後。
- `make_task_name()`: `webhookEventId`(ULID)から決定的なCloud Tasksタスク名を導出
  (`line-event-{webhookEventId}`)。Cloud Tasksのタスク名制約(英数字・ハイフン・アンダースコア、
  500文字以内)のバリデーションも実装。
- `handle_webhook_event()`: 1イベント単位の処理。`deliveryContext.isRedelivery`による早期
  スキップ(第1防御層)→ タスク名導出・enqueue(第2防御層、Cloud Tasks側の重複排除に相当)の
  2段構成をwebhook-async-processing-design.md通りに実装。
- `webhook_receiver()`: エントリポイント本体。署名検証失敗時のみ401相当、それ以外は個々の
  イベント処理の異常(webhookEventId欠落等の通常発生しない異常系)を握りつぶしつつ常に200を
  返す設計とした(LINE側の不要な再送連鎖を避けるため)。
- `InMemoryTaskQueueClient` / `TaskAlreadyExistsError`: 実際の`google.cloud.tasks_v2`
  クライアントの重複排除挙動(同名タスク再作成時のAlreadyExists)を模した検証用クライアント。
  GCPプロジェクト作成後は`TaskQueueClient`プロトコルを満たす実クライアントに差し替えるだけで
  動作させられる設計。

## テスト(`prototype/test_cloud_function_webhook.py`)
unittest 17件、全件パス。
- タスク名導出の決定性・不正文字/空文字の拒否
- 通常イベントのenqueue、`isRedelivery`イベントの早期スキップ
- 同一`webhookEventId`の2回目呼び出しが重複排除されること(LINE再送を想定したシナリオ)
- 署名検証の正常系・異常系(不正署名・ヘッダー欠落・シークレット不一致)
- Webhookレシーバー全体: 正常系200+enqueue、署名不正時401+enqueueなし、
  200ロスト後のLINE再送を想定した重複排除、異常イベント混在時も200を維持しつつ該当イベントのみスキップ

## 未実装のまま残るもの(次の課題)
- **Cloud Function B(`process_conversation_event`)**: LLM呼び出し・
  `ConversationFlowStateMachine`の状態遷移・`_render_by_tone()`によるメッセージ整形・
  LINE Push Message APIでの送信を行う側。実LLM呼び出しがpending-approval.md記載のAPIキー・
  課金承認待ちのため、Aと異なり「クラウド接続なしで検証可能なロジック」の切り出しが難しく
  未着手のまま残す。承認後、`process_llm_output()`(engine.py)の出力を受けて
  `intent-to-flow-mapping.md`の対応表で分岐するハンドラとして実装する見込み。
- 実際のGCPプロジェクト作成・Cloud Functions/Cloud Tasksへのデプロイ、
  LINE公式アカウントのチャネルシークレット取得(アカウント作成、オーナー承認待ち)。
- ログ出力先の設計(異常イベントスキップ時の記録方法)はデプロイ環境確定後の課題として残置。
