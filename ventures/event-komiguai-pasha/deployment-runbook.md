# デプロイ手順書(GCPプロジェクト作成・Stripeアカウント開設の承認後に実施)

## 位置づけ

aircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・line-reservation-ai・
oshien-pashaにはいずれも既にdeployment-runbook.mdがあるが、本venture
(event-komiguai-pasha)のみ未作成だったcross-venture parityギャップに対応する
(launch-readiness-checklist.mdフェーズ119の次回候補(1)「承認待ち事項が承認された場合は
その着手を最優先」に備え、承認後すぐ着手できる手順を事前に整理したもの)。

**本ドキュメント作成自体はGCPプロジェクト作成・Stripeアカウント開設・課金を一切伴わない
机上整理であり、承認前に着手してよい範囲内の作業として実施した。** launch-readiness-
checklist.md記載の承認待ち事項1(実GCPプロジェクト作成+Firestoreデータベース新規作成)・
2(実Stripeアカウント開設)がオーナーから承認されるまでは、本手順書のいずれのステップも
実行しない。

これまでの設計(tech-stack.md・web-form-hosting-selection.md・firestore-security-
rules-draft.md・各HTTPエントリポイント設計文書)とprototype/配下のコードは、以下の手順に
沿ってそのまま接続できる設計にしてある。

## 他venture(aircon-pasha等)との構成上の違い(本手順書に影響する点)

- 入力チャネルがLINE公式アカウントではなく、シンプルなWebフォーム(URLアクセスのみ、
  アカウント登録不要)である(tech-stack.md・web-form-hosting-selection.md)。そのため
  LINE Developersでのチャネル開設・Channel Secret取得のステップが不要な一方、Stripe
  Checkout(一回払いモード)の導入ステップが新たに必要になる。
- 課金モデルが継続課金(サブスクリプション)ではなく都度決済(1回=1イベント、
  one-time-checkout-no-account-design.md)である。そのためサブスクリプション状態管理
  (`subscription_status`・`current_period_end`等)やWebhookイベント種別の分岐は不要で、
  Stripe側で待ち受けるイベントは`checkout.session.completed`単一種別のみに限定される
  (stripe-webhook-signature-verification-design.md2節)。
- フォーム配信とバックエンド処理を同一Cloud Runサービス内に統合する構成
  (web-form-hosting-selection.md選択肢A)のため、Firebase Hosting等の追加GCPプロダクト
  有効化は不要。
- 会話状態マシンが無く「1フォーム送信=1イベント→LLM呼び出し→4出力生成→画面表示」で
  完結するため、line-reservation-aiのFunction B(Cloud Tasks経由の非同期本処理)・
  Function C(リマインド定期実行)に相当する非同期処理は不要(ただしTTL失効チェック用の
  定期実行は後述ステップ6で扱う)。

## 手順

### ステップ0: 前提の確認(承認後、着手前に再確認)

- オーナーが承認したのは「(1)GCPプロジェクト作成、(2)Firestoreデータベース新規作成、
  (3)Cloud Run functionsの有効化、(4)LLM APIキー取得、(5)Stripeアカウント開設・本番用
  APIキー取得」のどこまでかを、pending-approval.mdのオーナー回答文言で再確認する。範囲外の
  ステップ(例: 独自ドメイン取得〈custom-domain-vs-default-url-decision.mdの通り初回は
  デフォルトURL採用のため当面不要〉)は別途pending-approval.mdに追記して承認を待つ。
- 他venture(line-reservation-ai・course-set-pasha・aircon-pasha等)と同一GCPプロジェクト
  内で同居させるか、venture単位で別プロジェクトに分けるかは、承認時にオーナーへ確認する
  (課金・アクセス権限の管理単位として別プロジェクトを推奨するのは他ventureと同じ)。

### ステップ1: GCPプロジェクト作成

- 新規GCPプロジェクトを作成(プロジェクトIDは`event-komiguai-pasha-mvp`等)。
- 請求先アカウントを紐づける(=支払い設定。この時点で初めて課金が発生しうるため、承認範囲に
  含まれていることを必ず確認してから実施する)。
- billing-budget-cap-safeguard-design.md(フェーズ118)で設定済みの月間予算500円のBilling
  Budgetを本プロジェクトに対して作成し、閾値到達時の自動課金停止を有効化する(他6venture
  横展開済みの手順をそのまま適用)。
- 想定コストの参考値: llm-api-cost-estimate.md・unit-economics-estimate.mdの試算
  (都度決済1回あたりのLLM API原価・Stripe決済手数料〈4.3%〉・Firestore原価を合算した
  粗利率試算)。

### ステップ2: Firestoreデータベース新規作成・コレクション初期設定

- Native modeでFirestoreを有効化。
- firestore-security-rules-draft.mdで確定済みの3コレクション(`one_time_draft`・
  `inquiry`・`idempotency_key_index`)はコード側の初回書き込みで自動作成されるため、
  事前の手動作成は不要。
- `one_time_draft`コレクションのTTL24時間自動失効(ttl-expiry-result-delivery-
  refund-design.md)は、Firestore TTLポリシー(`expireAt`フィールド基準)をコレクション
  単位で設定する。`idempotency_key_index`側は`one_time_draft`用途(24時間)と`inquiry`
  用途(永続)が1コレクション内に共存するため、TTLポリシーは`expireAt`フィールドが
  設定されているドキュメントのみに適用される(Firestore TTLの既定動作通り、フィールド
  未設定のドキュメントは対象外)ことを有効化後に確認する。
- firestore-security-rules-draft.mdで確定済みのセキュリティルール(deny-all、Firebase
  Admin SDK経由のみ許可)をデプロイする。
- idempotency-key-duplicate-detection-firestore-query-design.mdが要求する複合インデックス
  の有無を確認する(他venture(aircon-pasha等)のfirestore-composite-index-plan.mdに
  相当する整理は本venture未着手のため、実クエリパターンを再点検した上で必要に応じて
  `firestore.indexes.json`を追加する。次回候補として残す)。

### ステップ3: シークレット管理

- LLM APIキー、Stripe本番用APIキー・Webhook署名シークレット(`whsec_...`)は環境変数に
  直書きせず、Secret Managerに登録し、Cloud Run functionsのランタイムから参照する
  (他venture・vendor-breach-key-rotation-runbook.mdと同じ方針)。
- prototype/配下の各エントリポイント(checkout_session_creation.py・stripe_webhook.py・
  draft_generation_fn.py等)は、Secret Manager参照に差し替えるだけで済む引数設計に
  既にしてある(コード変更不要、注入方法の変更のみ)。

### ステップ4: Cloud Run functions デプロイ(4関数)

web-form-hosting-selection.md選択肢Aの方針通り、フォーム配信(GET)と各処理(POST)を
同一Cloud Runサービス内の別ルートとして実装し、以下4つのHTTPエントリポイントをデプロイする
(いずれも2nd gen、Python 3.xランタイム、prototype/配下のコードをそのままエントリポイント
として使える設計)。

1. **申込フォーム**(GET `/`・POST `/submit-event`): inquiry-form-http-entry-point-
   design.md・submit-event-form-http-entry-point-design.md相当
   (prototype/inquiry_form_http_entry.py・cloud_function_submit_event_form.py)。
2. **問い合わせフォーム**(POST `/inquiry`): inquiry-form-http-entry-point-design.md相当
   (prototype/cloud_function_submit_inquiry.py)。
3. **Stripe Webhook受信**(POST `/webhook/stripe`): handle-stripe-webhook-http-entry-
   point-design.md(prototype/cloud_function_handle_stripe_webhook.py・
   stripe_webhook.py)。署名検証(ステップ3のWebhook署名シークレット使用)→冪等性チェック
   (`idempotency_key_index`参照)→`one_time_draft`への書き込み→LLM生成トリガーの順で
   処理する。
4. **結果ページ**(GET `/result/{draft_id}`): get-result-page-http-entry-point-design.md
   (prototype/cloud_function_get_result_page.py・result_page_entry.py)。TTL24時間以内
   かつ`page_state`に応じた表示切り替え(フェーズ116実装済みのJS切り替えとの結合)。

同時実行数・タイムアウトは、低頻度利用(月数件/主催者)を前提とした初期値から開始し、
実運用後の利用ペースを見て調整する(他venture比で利用頻度が低いため、初期値を保守的に
絞ってよい)。

### ステップ5: Stripeアカウント開設・Webhookエンドポイント登録

- Stripeアカウントを開設し、本人確認・銀行口座登録を行う(オーナー自身の対応が必要な
  範囲)。
- 本番用APIキー・Webhook署名シークレットを取得し、ステップ3のSecret Managerに登録する。
- StripeダッシュボードでWebhookエンドポイントを登録し、ステップ4-3の関数URLを宛先に設定、
  購読イベントは`checkout.session.completed`のみを選択する(stripe-webhook-signature-
  verification-design.md2節の通り、本ventureは都度決済1種別のみで完結するため他イベント
  種別の購読は不要)。
- stripe-checkout-session-params-design.md・checkout-session-success-cancel-url-
  design.mdの設計通り、Checkout Session発行時の`success_url`/`cancel_url`をステップ4の
  結果ページURLに合わせて設定する。

### ステップ6: TTL失効・返金判定の定期実行設定

- ttl-expiry-result-delivery-refund-design.mdが想定する「TTL24時間超過時の配信失敗・
  返金判定」処理は、Firestore TTLによる自動削除とは別に、削除前に判定ロジックを走らせる
  必要があるかを確認する(TTLポリシーはドキュメントを削除するだけで判定ロジックを呼ばない
  ため)。判定が必要な場合は、Cloud Scheduler+Cloud Run functionsによる定期実行
  (例: 1時間おき)を追加する。本ステップの具体的な実行頻度・判定ロジックの呼び出し方式は
  承認・実デプロイ後に確定する(次回候補として残す)。

### ステップ7: 結合テスト

- schema/output.schema.json・output-samples-validation.mdのパターンを、実LLM APIに
  投入して構造化出力(`generated`/`out_of_scope`/`insufficient_input`)の安定性を
  確認する。
- テスト用のStripeテストモードAPIキーでCheckout Session発行〜Webhook受信〜結果ページ
  表示までのエンドツーエンド疎通を確認する(本番キーへの切替前)。
- `one_time_draft`のTTL24時間失効・`idempotency_key_index`による重複検知が、実際の
  Firestore書き込みと連動して動作するかを確認する。
- post_generation_checks.pyの機械チェックが実LLM出力に対して誤検知・見落としなく
  機能しているかを実出力例で確認する。

### ステップ8: 本番投入前チェックリスト

- legal-notices-draft.mdの特定商取引法表記・プライバシーポリシーが実際のLLMプロバイダ名・
  Stripeアカウント名で更新されているか。
- data-retention-policy.md・vendor-breach-key-rotation-runbook.mdの保有キー一覧
  (Stripe・LLM API・GCPサービスアカウント鍵)に変更が無いか最終確認する。
- custom-domain-vs-default-url-decision.md(フェーズ50)の通り、初回ローンチはCloud Run
  デフォルトURL(`*.run.app`)のまま進める。

## 未確定事項・承認前に決めておきたいこと

- 請求先アカウントの支払い方法(オーナー個人のクレジットカード等)をどれにするかは、
  承認時にオーナーから指定してもらう必要がある(本エージェントは決済手段を選定・登録
  できない)。
- LLM APIプロバイダ(Claude API等)の選定自体は未確定だが、schema/配下の構造化出力設計は
  プロバイダ非依存であるため、承認後にプロバイダを決めても手順への影響はない(他venture
  と同じ整理)。
- ステップ2の複合インデックス要否の具体的な結論、ステップ4の同時実行数の具体的な数値、
  ステップ6の定期実行頻度は、いずれも承認・実接続後の実測を待って確定する。

最終更新: 2026-11-14 20:00 UTC(フェーズ120: 他6venture既存のdeployment-runbook.mdの
cross-venture parityギャップを解消し、本venture(都度決済・Webフォーム・LINE非採用という
他venture群と異なる構成)向けに新規作成した。コード変更なし、実行(GCPプロジェクト作成・
Stripeアカウント開設・課金設定等)は一切行っていない。)
