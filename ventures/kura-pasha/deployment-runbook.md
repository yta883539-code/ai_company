# デプロイ手順書(GCP/LINE/Stripeアカウント作成承認後に実施)

## 位置づけ

他venture(aircon-pasha・course-set-pasha・line-reservation-ai)には既にあるが本venture
未着手だったdeployment-runbook.md自体のcross-venture parityギャップに対応する。
本ドキュメントは、pending-approval.md記載の「GCPプロジェクト作成・LINE公式アカウント
開設・Stripeアカウント接続(いずれもアカウント作成・支払いが発生するためオーナー承認が
必要なアクション)」が承認された際に、実際に何をどの順番で行うかを事前に整理した
実行手順書である。**本ドキュメント作成自体はアカウント作成・課金を一切伴わない机上整理
であり、承認前に着手してよい範囲内の作業として実施した。** 承認が得られるまでは本手順書の
いずれのステップも実行しない。

これまでの設計(tech-stack.md・pricing-plan.md・subscription-billing-data-model-design.md・
usage-counter-workshop-key-design.md等)とprototype/配下のコード(cloud_function_webhook.py・
checkout_session.py・stripe_webhook.py・daily_scheduler.py)は、以下の手順に沿ってそのまま
接続できる設計にしてある。

## 他venture(aircon-pasha・course-set-pasha)との構成上の違い(本手順書に影響する点)

- 課金・生成回数上限管理の主体が`user_id`単位ではなく`craftsman_workshop/{workshop_id}`
  単位である点が他3venture共通の構造と根本的に異なる(tech-stack.md「4. 課金・契約単位の
  データストア」参照)。そのためStripe Webhookの解決先は`stripe_customer_id → workshop_id`
  であり、ステップ2・4のFirestoreコレクション設計・ステップ6の結合テストは
  `workshop_id`単位の動作確認を中心に行う。
- 複数職人プラン(契約者含め5名まで共同利用、pricing-plan.md)があるため、
  ステップ6ではcraftsman-account-linking-design.md(職人アカウントの紐付け)・
  downgrade-excess-member-handling-design.md(ダウングレード時の余剰メンバー扱い)の
  動作も併せて確認する。
- line-reservation-ai・course-set-pashaと同様、会話状態を保持する双方向のやり取りは
  なく「1メモ受信→LLM呼び出し→3種類のテキスト生成→即時返信」の単純なリクエスト/
  レスポンス型で完結する(tech-stack.md参照)。ただし本venture固有のdaily_scheduler.py
  (トライアル終了リマインド・支払い失敗督促の定期実行、daily-scheduler-design.md・
  payment-failure-dunning-design.md参照)は、line-reservation-aiのFunction C
  (リマインド定期実行)と同種の2つ目のCloud Function(Cloud Scheduler経由の定期実行)
  として別途デプロイが必要な点はline-reservation-aiと共通、course-set-pasha・
  aircon-pashaとは異なる(両者は単一関数構成)。
- market-research.mdの見積もり通り受注頻度自体が他3ventureより低い(低頻度・単発の
  オーダーメイド中心)ため、Cloud Functionsの同時実行数・タイムアウトは
  course-set-pashaの初期値(低頻度想定)をそのまま流用してよいと見込む
  (aircon-pashaのような高頻度想定の余裕設定は不要)。

## 手順

### ステップ0: 前提の確認(承認後、着手前に再確認)

- オーナーが承認したのは「(1)GCPプロジェクト作成、(2)Firestore有効化
  (`craftsman_workshop`・`user_profile`・`usage_counter`用途)、(3)Cloud Functionsの
  有効化(Webhook受信用・日次スケジューラ用の2関数)、(4)LLM APIキー取得、
  (5)LINE公式アカウント・Messaging APIチャネル開設、(6)Stripeアカウント接続」の
  どこまでかを、pending-approval.mdのオーナー回答文言で再確認する。範囲外のステップ
  (例: 本番ドメイン取得)は別途pending-approval.mdに追記して承認を待つ。
- 他3ventureと同一GCPプロジェクト内で同居させるか、venture単位で別プロジェクトに
  分けるかは、承認時にオーナーへ確認する(他3ventureと同じ整理)。

### ステップ1: GCPプロジェクト作成

- 新規GCPプロジェクトを作成(プロジェクトIDは`kura-pasha-mvp`等)。
- 請求先アカウントを紐づける(=支払い設定。この時点で初めて課金が発生しうるため、
  承認範囲に含まれていることを必ず確認してから実施する)。
- 想定コストの参考値: llm-api-cost-estimate.md・unit-economics-estimate.mdの試算。
  低頻度利用のため、他3venture(特にaircon-pasha)より月間の絶対額は小さくなる見込み
  (tech-stack.md「初期投資・ランニングコストの目安」参照)。

### ステップ2: Firestore有効化・コレクション初期設定

- Native modeでFirestoreを有効化。
- `craftsman_workshop/{workshop_id}`(`contractor_user_id`・`member_user_ids`・
  `plan_id`・`stripe_customer_id`・`subscription_status`・`trial_start_at`・
  `current_period_end`等)、`user_profile/{user_id}`(`workshop_id`のみ)、
  `usage_counter/{workshop_id}`(`month`・`count`)の3コレクションは、いずれもコード側の
  初回書き込みで自動作成されるため事前の手動作成は不要。複合インデックスを要する
  クエリは無いため`firestore.indexes.json`の追加設定は不要
  (subscription-billing-data-model-design.md・usage-counter-workshop-key-design.md参照)。
- limit-approaching-notification-design.mdの閾値通知フラグ管理、member-retention-notice-
  design.mdの退会抑止通知フラグ管理も本ステップで併せて初期設定する。

### ステップ3: シークレット管理

- LLM APIキー・LINE Channel Secret/Channel Access Token・Stripe APIキー/Webhook署名
  シークレットは環境変数に直書きせず、Secret Managerに登録し、Cloud Functionsの
  ランタイムから参照する(他3ventureと同じ方針)。
- prototype/配下の各Protocol(LLM呼び出し・返信送信・Stripe API呼び出し)は、
  Secret Manager参照に差し替えるだけで済む引数設計に既にしてある(コード変更不要、
  注入方法の変更のみ)。

### ステップ4: Cloud Functions デプロイ(2関数)

- **関数A: Webhook受信〜生成〜返信**(cloud_function_webhook.py)。LINE Webhookの
  署名検証→受注メモ本文・区分(新規制作/修理)の抽出→FAQコマンド判定
  (owner_faq_router.py、`_is_generation_paused()`等より前)→生成一時停止・決済失敗
  制限モード判定→LLM呼び出し(3出力生成)→usage_counterへの加算・閾値通知判定→
  LINE返信送信、までを同期処理で行う。HTTPトリガー、LINE側のWebhook URLに設定。
  また同一関数内でStripe Webhook(stripe_webhook.py、`verify_stripe_signature()`・
  `receive_stripe_webhook()`)も受け付ける(course-set-pashaと同じ、URLパスで
  LINE/Stripeの2系統を振り分ける構成)。
- **関数B: 日次スケジューラ**(daily_scheduler.py)。Cloud Scheduler経由でHTTPトリガーを
  日次起動し、トライアル終了リマインド(daily-scheduler-design.md参照、
  payment-failure-dunning-design.mdフェーズ120で3日前リマインドの実送信配線が
  完了済み)・支払い失敗督促を行う。line-reservation-aiのFunction C
  (リマインド定期実行)と同種の構成。
- 同時実行数・タイムアウトは、低頻度利用(受注件数自体が少ない)を踏まえ
  course-set-pashaの初期値をそのまま流用する。具体的な数値は実LLM接続後の1件あたり
  処理時間の実測を待って確定する(次の課題として残す)。
- Python 3.x ランタイム、prototype/配下のコードをそのままエントリポイントとして
  デプロイできる設計(クラウドSDK呼び出し部分のみ後付けで注入するスタブ構成のため)。

### ステップ5: LINE公式アカウント・Messaging APIチャネル開設

- LINE Developersでチャネルを作成し、Channel Secret/Channel Access Tokenを取得、
  ステップ3のSecret Managerに登録。
- Webhook URLをステップ4の関数AのURLに設定し、Webhook利用をON。
- line-api-pricing.md(line-reservation-ai)の料金プランを踏まえ、低頻度利用のため
  MVP検証中はフリープラン(月間メッセージ通数上限内)での運用を基本とする
  (course-set-pashaと同じ想定)。

### ステップ6: Stripeアカウント接続

- Stripeアカウントを開設(または既存アカウントに本venture用のプロダクト・価格を追加)。
- pricing-plan.mdの3プラン(ライト/スタンダード/複数職人)に対応するPriceオブジェクトを
  作成。
- Webhook エンドポイントをステップ4の関数AのURL(Stripe振り分けパス)に設定し、
  署名シークレットをステップ3のSecret Managerに登録。
- checkout-initiation-flow-design.md・stripe-webhook-checkout-completed-design.md・
  subscription-canceled-webhook-design.md・subscription-plan-sync-design.mdの各設計に
  沿って発行済みのCheckout Session発行・Webhookイベント処理コードをそのまま接続する。

### ステップ7: 結合テスト

- schema/配下の期待出力・llm-quality-verification-plan.mdのパターンを実LLM APIに
  投入して自然文・構造化出力の安定性を確認する(pending-approval.md記載の「実LLM API
  呼び出しによる自動テスト」に相当)。
- テスト用LINEアカウントからWebhookへ実受注メモを流し、生成〜返信までの
  エンドツーエンド疎通を確認する。
- テスト用Stripeアカウント(テストモード)でCheckout Session発行→決済完了→
  Webhook受信→`craftsman_workshop`ドキュメントの`subscription_status`更新、までの
  一連の流れを確認する。
- 複数職人プランでの職人アカウント紐付け(craftsman-account-linking-design.md)・
  ダウングレード時の余剰メンバー扱い(downgrade-excess-member-handling-design.md)を
  テストモードで確認する。
- usage_counterの加算・閾値通知が実際のFirestore書き込みと連動して動作するかを
  確認する。
- 関数Bの日次スケジューラが、テスト用に短縮した日付条件でトライアル終了リマインド・
  支払い失敗督促を正しく起動するかを確認する。

### ステップ8: 本番投入前チェックリスト

- legal-notices-draft.mdの特定商取引法表記・プライバシーポリシーが実際のLLMプロバイダ名・
  Stripeの決済代行事業者名で更新されているか。
- owner-operation-self-service-faq.md・owner-faq-routing-design.mdのFAQコマンドが
  実LINE接続後も期待通り動作するか。
- unfollow-billing-faq.md記載の、契約中にLINEをブロック/unfollowした場合の挙動
  (blocked-but-billing-detection-design.md等)が実環境で機能するか。

## 未確定事項・承認前に決めておきたいこと

- 請求先アカウントの支払い方法(オーナー個人のクレジットカード等)をどれにするかは、
  承認時にオーナーから指定してもらう必要がある(本エージェントは決済手段を選定・
  登録できない)。
- LLM APIプロバイダ(Claude API等)の選定自体は未確定。schema/配下の構造化出力設計は
  プロバイダ非依存であるため、承認後にプロバイダを決めても手順への影響はない
  (他3ventureと同じ整理)。
- ステップ4の同時実行数の具体的な数値、ステップ5のLINEメッセージ通数消費の実測は、
  いずれも承認・実接続後でなければ確定できない。

最終更新: 2026-09-17 22:00 UTC(フェーズ127: 他3ventureには既にあるが本venture未着手
だったdeployment-runbook.md自体のcross-venture parityギャップを解消。本venture固有の
workshop単位課金・複数職人プラン・2関数構成(Webhook受信+日次スケジューラ)を反映)
