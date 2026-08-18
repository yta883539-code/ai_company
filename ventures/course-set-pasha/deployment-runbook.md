# デプロイ手順書(GCPアカウント作成承認後に実施)

## 位置づけ
本ドキュメントは、pending-approval.md記載の「GCPプロジェクト作成・APIキー取得(アカウント作成・
支払いが発生するためオーナー承認が必要なアクション)」が承認された際に、実際に何をどの順番で
行うかを事前に整理した実行手順書である。**本ドキュメント作成自体はアカウント作成・課金を一切
伴わない机上整理であり、承認前に着手してよい範囲内の作業として実施した。** 承認が得られるまでは
本手順書のいずれのステップも実行しない。line-reservation-ai/deployment-runbook.mdと同じ位置づけの
ドキュメントを本venture向けに作成したもの(line-reservation-aiには既存、本ventureには未着手
だったため今回新規作成)。

これまでの設計(tech-stack.md・hosting-platform-selection.md〈line-reservation-ai流用〉・
webhook-processing-flow-design.md・limit-approaching-notification-design.md等)とprototype/配下の
コード(cloud_function_webhook.py・history_export.py・post_generation_checks.py)は、以下の手順に
沿ってそのまま接続できる設計にしてある。

## line-reservation-aiとの構成上の違い(本手順書に影響する点)
- 会話状態を保持する双方向のやり取りがなく、「1メモ受信→LLM呼び出し→3種類のテキスト生成→
  即時返信」の単純なリクエスト/レスポンス型で完結する(tech-stack.md参照)。そのため
  line-reservation-aiのFunction B(Cloud Tasks経由の非同期本処理)・Function C(リマインド
  定期実行)に相当するものは不要で、デプロイするCloud Functionsは1関数のみ。
- 永続データストア(Firestore)は、月間生成回数カウント(`usage_counter`、コレクション
  「ユーザー1人=1ドキュメント、フィールドはmonth・countのみ」)専用の最小構成に限られる。
  予約枠・会話状態・通知ログ等の複雑なコレクションは存在しない。

## 手順

### ステップ0: 前提の確認(承認後、着手前に再確認)
- オーナーが承認したのは「(1)GCPプロジェクト作成、(2)Firestore有効化(usage_counter用途のみ)、
  (3)Cloud Functionsの有効化、(4)LLM APIキー取得、(5)LINE公式アカウント・Messaging API
  チャネル開設」のどこまでかを、pending-approval.mdのオーナー回答文言で再確認する。範囲外の
  ステップ(例: 本番ドメイン取得、決済代行サービス契約等)は別途pending-approval.mdに追記して
  承認を待つ。

### ステップ1: GCPプロジェクト作成
- 新規GCPプロジェクトを作成(プロジェクトIDは`course-set-pasha-mvp`等、本README「概要」の
  サービス名と紐づく命名を想定)。line-reservation-aiと同一GCPプロジェクト内で別リソースとして
  同居させるか、venture単位で別プロジェクトに分けるかは、承認時にオーナーへ確認する
  (どちらでも設計上は動作するが、課金・アクセス権限の管理単位として別プロジェクトを推奨)。
- 請求先アカウントを紐づける(=支払い設定。この時点で初めて課金が発生しうるため、承認範囲に
  含まれていることを必ず確認してから実施する)。
- 想定コストの参考値: subscription-billing-cost-estimate.md・llm-api-cost-estimate.mdの試算。
  月間生成回数の想定規模であれば当面ほぼ無料枠内〜低額に収まる見込み(詳細は各ドキュメント参照)。

### ステップ2: Firestore有効化・usage_counter初期設定
- limit-approaching-notification-design.md・tech-stack.md「6. 月間生成回数カウントの保存先」の
  設計通り、Native modeでFirestoreを有効化。
- コレクションはコード側の初回書き込みで自動作成されるため、事前の手動作成は不要。
  line-reservation-aiのような複合インデックスを要するクエリは無いため、
  `firestore.indexes.json`の追加設定は不要(最小構成のメリット)。

### ステップ3: シークレット管理
- LLM APIキー・LINE Channel Secret/Channel Access Tokenは環境変数に直書きせず、
  Secret Managerに登録し、Cloud Functionsのランタイムから参照する
  (line-reservation-aiと同じ方針)。
- prototype/cloud_function_webhook.pyの`LlmCallClient`・`ReplyClient`の各Protocolは、
  Secret Manager参照に差し替えるだけで済む引数設計に既にしてある(コード変更不要、
  注入方法の変更のみ)。

### ステップ4: Cloud Functions デプロイ(1関数)
- **Webhook受信〜生成〜返信を1関数で完結**(`process_memo_event`, cloud_function_webhook.py)。
  署名検証→メモ本文の抽出→LLM呼び出し(3出力生成)→post_generation_checks.pyによる
  機械チェック→usage_counterへの加算・上限接近通知判定→LINE返信送信、までを同期処理で行う。
  HTTPトリガー、LINE側のWebhook URLに設定。
- line-reservation-aiのようなCloud Tasksへのエンキュー・非同期化は、本venture単発処理では
  応答時間の見込み(LLM呼び出し1回分)がLINE Webhookのタイムアウト内に収まる想定のため、
  現時点では不要と判断(応答遅延が実測で問題になった場合は、Function A/Bへの分割を再検討)。
- Python 3.x ランタイム、prototype/配下のコードをそのままエントリポイントとしてデプロイ
  できる設計(クラウドSDK呼び出し部分のみ後付けで注入するスタブ構成のため)。

### ステップ5: LINE公式アカウント・Messaging APIチャネル開設
- LINE Developersでチャネルを作成し、Channel Secret/Channel Access Tokenを取得、
  ステップ3のSecret Managerに登録。
- Webhook URLをステップ4の関数URLに設定し、Webhook利用をON。
- line-api-pricing.mdの料金プランを踏まえ、MVP検証中はフリープラン(月間メッセージ通数上限内)
  での運用を基本とする(line-reservation-aiと同一の料金体系を参照)。

### ステップ6: 結合テスト
- schema/validate_test_cases.py・output-samples-validation.mdのstatus別5パターンを、
  実LLM APIに投入して自然文・構造化出力の安定性を確認する
  (これがpending-approval.md記載の「実LLM API呼び出しによる自動テスト」に相当)。
- テスト用LINEアカウント(オーナー自身の個人アカウント等)からWebhookへ実メモを1件流し、
  生成〜返信までのエンドツーエンド疎通を確認する。
- usage_counterの加算・limit-approaching-notification-design.mdで設計した上限接近通知が、
  実際のFirestore書き込みと連動して動作するかを確認する。

### ステップ7: 本番投入前チェックリスト
- legal-notices-draft.mdの特定商取引法表記・プライバシーポリシーが実際のLLMプロバイダ名で
  更新されているか(landing-page-copy-draft.mdの残課題)。
- post_generation_checks.pyの機械チェック(厳守事項2・3・4・5・7・9)が実LLM出力に対して
  誤検知・見落としなく機能しているか(実LLM接続後に生成文の実例で確認、README「残る未解決
  事項」参照)。
- pricing-plan.md・subscription-cancellation-flow-design.mdの決済代行サービス選定・契約自体は
  本ステップの範囲外(別途オーナー承認・契約が必要)。

## 未確定事項・承認前に決めておきたいこと
- 請求先アカウントの支払い方法(オーナー個人のクレジットカード等)をどれにするかは、
  承認時にオーナーから指定してもらう必要がある(本エージェントは決済手段を選定・登録できない)。
- LLM APIプロバイダ(Claude API等)の選定自体は未確定。schema/output.schema.jsonの
  机上検証はプロバイダ非依存の構造化出力設計になっているため、承認後にプロバイダを決めても
  手戻りは小さい見込み(line-reservation-aiと同様)。
- line-reservation-aiと同一GCPプロジェクトに同居させるか別プロジェクトに分けるかは
  ステップ1の通り未確定。
