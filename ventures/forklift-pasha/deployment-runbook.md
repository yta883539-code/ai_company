# デプロイ手順書(GCPプロジェクト作成・Stripeアカウント開設の承認後に実施)

## 位置づけ

aircon-pasha・course-set-pasha・event-komiguai-pasha・kura-pasha・line-reservation-ai
にはいずれも既にdeployment-runbook.mdがあるが、本venture(forklift-pasha)のみ
未作成だったcross-venture parityギャップに対応する(承認待ち事項が承認された場合に
すぐ着手できる手順を事前に整理したもの)。

**本ドキュメント作成自体はGCPプロジェクト作成・Stripeアカウント開設・課金を一切伴わない
机上整理であり、承認前に着手してよい範囲内の作業として実施した。** tech-stack.md・
vendor-breach-key-rotation-runbook.md記載の承認待ち事項(実GCPプロジェクト作成+
Firestoreデータベース新規作成、実Stripeアカウント開設、LLM APIキー取得)がオーナーから
承認されるまでは、本手順書のいずれのステップも実行しない。

これまでの設計(tech-stack.md・firestore-data-model.md・firestore-security-rules-
draft.md・各Stripe関連設計文書)とprototype/配下のコードは、以下の手順に沿ってそのまま
接続できる設計にしてある。

## 他venture(aircon-pasha等)との構成上の違い(本手順書に影響する点)

- 入力チャネルがLINE公式アカウントではなく、汎用Webフォーム(tech-stack.md フェーズ70、
  URLアクセスのみ・アカウント登録不要)である。対象業種(倉庫業・運送業・建設業の現場)で
  LINE公式アカウント開設の外部依存を追加するメリットが薄いと判断した暫定決定であり、
  LINE Developersでのチャネル開設は不要。
- 課金軸が「生成回数」(course-set-pasha)や「屋号単位」(aircon-pasha)ではなく
  「保有台数」(pricing-plan.mdの3プラン: ライト/スタンダード/複数台)である。Firestore
  データモデル上は`fleet_operator`(契約単位)・`vehicle`(車両単位)・`usage_counter`
  (月間生成回数)の3コレクション構成となる(他venture比で`vehicle`が追加の1コレクション)。
- 課金モデルは継続課金(サブスクリプション)で、Stripe側で待ち受けるイベントは
  `checkout.session.completed`・`customer.subscription.created`・
  `customer.subscription.updated`・`customer.subscription.deleted`・
  `invoice.payment_failed`・`invoice.payment_succeeded`の6種別(stripe-event-
  idempotency-design.md)。kura-pashaと同型の冪等性ガード設計を踏襲済み。
- 点検記録そのもの(inspection_record)はFirestoreに永続化しない方針
  (firestore-data-model.md「設計方針」)のため、他venture群より永続データの範囲が狭い。
- Webフォームの申込・入力フロー自体のHTTPエントリポイント(`functions_framework`の
  `main(request)`ラッパー)は、本venture未着手の部分が残っていたが、フェーズ239で
  `form_submission_flow.py`側の`main(request)`を追加し解消した(下記ステップ4参照、
  `access_url_reissue_handler.py`は本手順書フェーズ237作成時点の記載が既に古く、
  実際には`main(request)`が先行フェーズで実装済みであったこともフェーズ239で確認した)。

## 手順

### ステップ0: 前提の確認(承認後、着手前に再確認)

- オーナーが承認したのは「(1)GCPプロジェクト作成、(2)Firestoreデータベース新規作成、
  (3)Cloud Run functionsの有効化、(4)LLM APIキー取得、(5)Stripeアカウント開設・本番用
  APIキー取得、(6)Webフォームホスティング先の確定」のどこまでかを、pending-approval.md
  のオーナー回答文言で再確認する。
- 他venture(line-reservation-ai・course-set-pasha・aircon-pasha等)と同一GCPプロジェクト
  内で同居させるか、venture単位で別プロジェクトに分けるかは、承認時にオーナーへ確認する
  (課金・アクセス権限の管理単位として別プロジェクトを推奨するのは他ventureと同じ)。

### ステップ1: GCPプロジェクト作成

- 新規GCPプロジェクトを作成(プロジェクトIDは`forklift-pasha-mvp`等)。
- 請求先アカウントを紐づける(=支払い設定。この時点で初めて課金が発生しうるため、承認範囲に
  含まれていることを必ず確認してから実施する)。
- billing-budget-cap-safeguard-design.mdで設定済みの月間予算**3,000円**(他6venture共通の
  暫定500円より高い理由: 複数台プラン顧客の最大原価約598.4円/月×5件程度を想定)のBilling
  Budgetを本プロジェクトに対して作成し、50%・90%・100%閾値到達時の自動課金停止を有効化する
  (他venture横展開済みの手順をそのまま適用)。
- 想定コストの参考値: llm-api-cost-estimate.md・unit-economics-estimate.mdの試算
  (プラン別のLLM API原価・Stripe決済手数料〈4.3%〉・Firestore原価を合算した粗利率試算)。

### ステップ2: Firestoreデータベース新規作成・コレクション初期設定

- Native modeでFirestoreを有効化。
- firestore-data-model.mdで確定済みの3コレクション(`fleet_operator`・`vehicle`・
  `usage_counter`)はコード側の初回書き込みで自動作成されるため、事前の手動作成は不要。
- firestore-security-rules-draft.mdで確定済みのセキュリティルール(3コレクション
  いずれもdeny-all、Firebase Admin SDK経由のみ許可)をデプロイする。
- firestore-composite-index-plan.mdで整理済みの複合インデックスの要否を、実クエリパターンと
  再度突き合わせて`firestore.indexes.json`に反映する。

### ステップ3: シークレット管理

- LLM APIキー、Stripe本番用APIキー・Webhook署名シークレット(`whsec_...`)は環境変数に
  直書きせず、Secret Managerに登録し、Cloud Run functionsのランタイムから参照する
  (vendor-breach-key-rotation-runbook.mdと同じ方針)。
- Webフォームホスティング先(未確定、tech-stack.md)の管理用トークン・APIキーも同様に
  Secret Managerへ登録する(ホスティング先確定は承認後の次回候補として残る)。
- prototype/配下のStripe関連エントリポイント(checkout_session.py・stripe_webhook.py)は、
  Secret Manager参照に差し替えるだけで済む引数設計に既にしてある(コード変更不要、
  注入方法の変更のみ)。

### ステップ4: Cloud Run functions デプロイ

以下はprototype/配下に`main(request)`形式のHTTPエントリポイントが既にあり、そのまま
デプロイできるもの(いずれも2nd gen、Python 3.xランタイム)。

1. **Checkout Session作成**(POST、アクセストークン経由): stripe-checkout-plan-id-
   design.md・checkout-session-cloud-function-entry-point-design.md相当
   (prototype/checkout_session.py `main()`)。303リダイレクトでStripe Checkout URLへ
   遷移させる設計済み。
2. **Stripe Webhook受信**(POST): stripe-webhook-entry-point-design.md・
   stripe-event-idempotency-design.md相当(prototype/stripe_webhook.py `main()`)。
   署名検証→冪等性チェック→6イベント種別ごとのハンドラ呼び出しの順で処理する。
3. **トライアル終了通知バッチ**(Cloud Scheduler日次トリガー):
   prototype/cloud_function_send_trial_end_emails.py `main()`。
4. **決済失敗リマインドバッチ**(Cloud Scheduler日次トリガー):
   prototype/cloud_function_send_payment_failure_reminders.py `main()`。
5. **削除候補確認通知バッチ**(Cloud Scheduler日次トリガー):
   prototype/cloud_function_send_deletion_confirmations.py `main()`。

以下は個別モジュール(ロジック本体)に加え、`main(request)`形式のHTTPエントリポイントも
フェーズ239時点で実装済み(承認・ホスティング先確定後、そのままデプロイできる):

- **Webフォーム申込・点検記録入力受付**: prototype/form_submission_flow.py
  `process_form_submission()`(オーケストレーション本体)・`receive_form_submission()`
  (access_token解決・HTTPステータス変換)・`main()`(フェーズ239で追加)。
  `llm_generate`は実LLM APIキー取得(オーナー承認待ち)までNoneのままで、
  `receive_form_submission()`が503を返す安全側フォールバックがある(実LLM接続後は
  `get_form_submission_runtime_dependencies()`の戻り値を差し替えるだけで済む)。
- **アクセスURL再発行受付**: prototype/access_url_reissue_handler.py
  `receive_reissue_request()`・`main()`(先行フェーズで実装済み)。

同時実行数・タイムアウトは、低頻度利用(月数件/事業者)を前提とした初期値から開始し、
実運用後の利用ペースを見て調整する。

### ステップ5: Stripeアカウント開設・Webhookエンドポイント登録

- Stripeアカウントを開設し、本人確認・銀行口座登録を行う(オーナー自身の対応が必要な
  範囲)。
- 本番用APIキー・Webhook署名シークレットを取得し、ステップ3のSecret Managerに登録する。
- StripeダッシュボードでWebhookエンドポイントを登録し、ステップ4-2の関数URLを宛先に設定、
  購読イベントは`checkout.session.completed`・`customer.subscription.created`・
  `customer.subscription.updated`・`customer.subscription.deleted`・
  `invoice.payment_failed`・`invoice.payment_succeeded`の6種別を選択する
  (stripe-event-idempotency-design.md)。
- pricing-plan.mdの3プラン(ライト/スタンダード/複数台)に対応するStripe Price IDを作成し、
  plan_id_resolution.pyの解決ロジックと紐づける。

### ステップ6: Webフォームホスティング先の確定・接続

- tech-stack.mdで未確定のままになっているWebフォームホスティング先(Cloud Run統合配信か、
  別ホスティングサービスか)を、承認時にオーナーへ確認する(他venture
  〈event-komiguai-pasha〉のCloud Run統合配信〈選択肢A〉を参考にできる)。
- 確定後、ステップ4のHTTPエントリポイント(form_submission_flow.py・
  access_url_reissue_handler.py、いずれもフェーズ239時点で実装済み)をデプロイする。

### ステップ7: 結合テスト

- schema/output.schema.json・output-samples-validation.mdのパターンを、実LLM APIに
  投入して構造化出力(`generated`/`out_of_scope`/`insufficient_input`)の安定性を
  確認する。
- テスト用のStripeテストモードAPIキーでCheckout Session発行〜Webhook受信〜
  `fleet_operator`ドキュメント更新までのエンドツーエンド疎通を確認する(本番キーへの
  切替前)。
- post_generation_checks.pyの機械チェックが実LLM出力に対して誤検知・見落としなく
  機能しているかを実出力例で確認する。
- prototype/run_all_tests.pyの全テストを、実Firestore接続(エミュレータ経由)でも
  再確認する(現状はモック/スタブ経由のみで確認済み)。

### ステップ8: 本番投入前チェックリスト

- legal-notices-draft.mdの特定商取引法表記・プライバシーポリシーが実際のLLMプロバイダ名・
  Stripeアカウント名・Webフォームホスティング先名で更新されているか。
- vendor-breach-key-rotation-runbook.mdの保有キー一覧(Stripe・LLM API・GCPサービス
  アカウント鍵・Webフォームホスティング先)に変更が無いか最終確認する。
- 初回ローンチはCloud RunデフォルトURL(`*.run.app`)等、独自ドメイン取得を伴わない構成で
  進める(他venture同様の方針)。

## 未確定事項・承認前に決めておきたいこと

- 請求先アカウントの支払い方法(オーナー個人のクレジットカード等)をどれにするかは、
  承認時にオーナーから指定してもらう必要がある(本エージェントは決済手段を選定・登録
  できない)。
- LLM APIプロバイダ(Claude API等)の選定自体は未確定だが、schema/配下の構造化出力設計は
  プロバイダ非依存であるため、承認後にプロバイダを決めても手順への影響はない(他venture
  と同じ整理)。
- Webフォームホスティング先(ステップ6)が未確定のため、ステップ4のHTTPエントリポイント
  (実装済み)の実デプロイ自体は承認・ホスティング先確定後の着手となる。
- ステップ2の複合インデックス要否の具体的な結論、ステップ4の同時実行数の具体的な数値は、
  いずれも承認・実接続後の実測を待って確定する。

最終更新: 2026-11-15 15:00 UTC(フェーズ239: フェーズ237作成時点で「HTTPエントリポイント
化未着手」と記載していた2件のうち、access_url_reissue_handler.pyは実際には先行フェーズで
`main()`が実装済みであった記載の古さをまず確認し、残るform_submission_flow.pyに
`receive_form_submission()`・`get_form_submission_runtime_dependencies()`・`main()`を
新規実装した(prototype/test_form_submission_flow.pyにテスト20件追加)。実LLM API未接続
(オーナー承認待ち)の間は`llm_generate=None`により503を返す安全側フォールバックとした。
本手順書は上記実装状況の反映のみ(ステップ4・6・未確定事項)。新規テスト20件追加、
test_form_submission_flow.py単体44件(旧24件)・run_all_tests.py全24ファイル・
schema検証11件いずれもパス(回帰なし)。実GCPプロジェクト作成・Stripeアカウント開設・
課金設定等は一切行っていない。)
