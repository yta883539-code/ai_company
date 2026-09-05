# デプロイ手順書(GCPアカウント作成承認後に実施)

## 位置づけ
本ドキュメントは、pending-approval.md記載の「GCPプロジェクト作成・APIキー取得(アカウント作成・
支払いが発生するためオーナー承認が必要なアクション)」が承認された際に、実際に何をどの順番で
行うかを事前に整理した実行手順書である。**本ドキュメント作成自体はアカウント作成・課金を一切
伴わない机上整理であり、承認前に着手してよい範囲内の作業として実施した。** 承認が得られるまでは
本手順書のいずれのステップも実行しない。

これまでの設計(hosting-platform-selection.md・firestore-data-model.md・
webhook-async-processing-design.md・firestore-transaction-design.md等)とprototype/配下の
コード(cloud_function_webhook.py・cloud_function_process_event.py・reminder_scheduler.py・
engine.py)は、以下の手順に沿ってそのまま接続できる設計にしてある。

## 手順

### ステップ0: 前提の確認(承認後、着手前に再確認)
- オーナーが承認したのは「(1)GCPプロジェクト作成、(2)Firestore有効化、(3)Cloud Functions/
  Cloud Tasks/Cloud Schedulerの有効化、(4)LLM APIキー取得、(5)LINE公式アカウント・
  Messaging APIチャネル開設」のどこまでかを、pending-approval.mdのオーナー回答文言で
  再確認する。範囲外のステップ(例: 本番ドメイン取得、決済機能等)は別途pending-approval.mdに
  追記して承認を待つ。

### ステップ1: GCPプロジェクト作成
- 新規GCPプロジェクトを作成(プロジェクトIDは`line-booking-mvp`等、本README「概要」の
  サービス名と紐づく命名を想定)。
- 請求先アカウントを紐づける(=支払い設定。この時点で初めて課金が発生しうるため、
  承認範囲に含まれていることを必ず確認してから実施する)。
- 想定コストの参考値: firestore-traffic-cost-estimate.mdの試算(プロプラン相当で
  無料枠内32〜130店舗規模)。MVP規模(協力店舗数店)であれば当面ほぼ無料枠内に収まる見込み。

### ステップ2: Firestore有効化・コレクション初期設定
- firestore-data-model.mdの設計通り、Native modeでFirestoreを有効化。
- コレクション(conversations・escalationWindows・notificationLogEntries等)はコード側の
  初回書き込みで自動作成されるため、事前の手動作成は不要。ただし複合クエリを使う箇所のみ、
  デプロイ前に`firestore.indexes.json`(venture直下、firestore-composite-index-plan.md
  〈フェーズ続き198〉で集約・生成済み)を`gcloud firestore deploy --only firestore:indexes`
  で先行作成する。escalationWindows・conversationsは全店舗横断のcollection groupクエリの
  ため`queryScope: COLLECTION_GROUP`の指定が必須である点に注意(詳細は同ドキュメント参照)。

### ステップ3: シークレット管理
- LLM APIキー・LINE Channel Secret/Channel Access Tokenは環境変数に直書きせず、
  Secret Managerに登録し、Cloud Functionsのランタイムから参照する。
- prototype/engine.pyの`llm_call`スタブ・cloud_function_webhook.pyの
  `verify_line_signature`が受け取るchannel_secretは、いずれもSecret Manager参照に
  差し替えるだけで済む引数設計に既にしてある(コード変更不要、注入方法の変更のみ)。

### ステップ4: Cloud Functions デプロイ(3関数)
1. **Function A(`webhook_receiver`, cloud_function_webhook.py)**: LINE Webhookの
   受信エンドポイント。署名検証→即時ACK→Cloud Tasksへエンキューのみを行う
   (webhook-async-processing-design.md通り)。HTTPトリガー、LINE側のWebhook URLに設定。
2. **Function B(`ConversationEventProcessor`, cloud_function_process_event.py)**:
   Cloud Tasksからディスパッチされる本処理。LLM呼び出し・状態遷移・LINE Push送信を行う。
   Cloud Tasksトリガー(またはHTTPターゲットとしてCloud Tasksから叩く構成)。
3. **Function C(`reminder_scheduler.py`のselect_due_initial_reminders/select_due_resends
   呼び出し元)**: 前日リマインド・再通知の定期実行。Cloud Schedulerトリガー(cron、
   reminder-scheduler-design.md通り5〜15分間隔を想定)。

いずれもPython 3.x ランタイム、prototype/配下のコードをそのままエントリポイントとして
デプロイできる設計(クラウドSDK呼び出し部分のみ後付けで注入するスタブ構成のため)。

### ステップ5: Cloud Tasks / Cloud Scheduler 設定
- Cloud Tasksキューを1つ作成し、Function Aからのエンキュー先とする
  (make_task_name()による決定的タスク名でLINE再送時の重複排除、webhook-async-processing-design.md通り)。
- Cloud Schedulerジョブを1つ作成し、Function Cを定期起動する。

### ステップ6: LINE公式アカウント・Messaging APIチャネル開設
- LINE Developersでチャネルを作成し、Channel Secret/Channel Access Tokenを取得、
  ステップ3のSecret Managerに登録。
- Webhook URLをFunction AのURLに設定し、Webhook利用をON。
- line-api-pricing.md・line-price-revision-2026-check.mdの最新料金プランを踏まえ、
  MVP検証中はフリープラン(月間メッセージ通数上限内)での運用を基本とする。

### ステップ7: 結合テスト
- schema-validation-report.md・conversation-samples-test-cases.mdのN1〜N4・E1〜E16を、
  実LLM APIに投入して自然文・構造化出力の安定性を確認する
  (これがpending-approval.md記載の「実LLM呼び出しでの安定生成確認」そのもの)。
- テスト用LINEアカウント(オーナー自身の個人アカウント等)からFunction Aへの実Webhookを
  1件流し、Function B→LINE Push応答までのエンドツーエンド疎通を確認する。

### ステップ8: 本番投入前チェックリスト
- data-retention-policy.mdの保存期間設定が反映されているか。
- legal-notices-draft.mdの特定商取引法表記・プライバシーポリシーが実際のLLMプロバイダ名で
  更新されているか(landing-page-copy-draft.mdの残課題)。
- escalation周りの通知先(owner_user_id)が協力店舗ごとに正しく設定されているか
  (owner-notification-channel-design.md)。

## 未確定事項・承認前に決めておきたいこと
- 請求先アカウントの支払い方法(オーナー個人のクレジットカード等)をどれにするかは、
  承認時にオーナーから指定してもらう必要がある(本エージェントは決済手段を選定・登録できない)。
- LLM APIプロバイダ(Claude API等)の選定自体は未確定。schema-validation-report.mdの
  机上検証はプロバイダ非依存の構造化出力設計になっているため、承認後にプロバイダを決めても
  手戻りは小さい見込み。
