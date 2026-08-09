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
- (訂正 2026-08-09 02:00 UTC: 当初「Aと異なりクラウド接続なしで検証可能なロジックの切り出しが
  難しく未着手のまま残す」としていたが誤りだった。実際には本項執筆の翌日(2026-08-02 10:00 UTC)に
  `prototype/cloud_function_process_event.py`としてCloud Function Bの着手が始まり、以後多数の
  フェーズを経て`ConversationEventProcessor`(intent別ディスパッチ・escalation/faqテンプレート
  返信・オーナー通知配線・前日リマインド連携等)としてAと同じ「実LLM/実クラウド接続なしで
  検証可能なロジック」の切り出し方針のまま実装済みである。以後このファイルで「Cloud Function Bは
  未着手」として再掲しないこと。candidate-label-weekday-fix.md・pending-timeout-ux.md・
  webhook-function-b-implementation.mdの訂正メモと同様の記載更新漏れ)
- 実際のGCPプロジェクト作成・Cloud Functions/Cloud Tasksへのデプロイ、
  LINE公式アカウントのチャネルシークレット取得(アカウント作成、オーナー承認待ち)。
- ログ出力先の設計(異常イベントスキップ時の記録方法)はデプロイ環境確定後の課題として残置。
