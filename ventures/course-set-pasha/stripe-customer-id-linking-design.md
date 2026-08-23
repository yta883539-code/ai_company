# Stripe customer_id ↔ user_id 紐付け設計

作成日: 2026-08-23(フェーズ97)

stripe-webhook-cloud-function-entry-point-design.md(フェーズ96)「残課題」1点目だった、
`resolve_user_id`(`stripe_customer_id → user_id`変換)の実装本体を設計する。

## 1. 前提・方針

- `dispatch_stripe_event()`(フェーズ94)は`customer.subscription.*`イベントの
  `data.object.customer`(StripeカスタマーオブジェクトのID、`cus_...`形式)を
  `resolve_user_id(customer) -> Optional[str]`で内部`user_id`(LINE友だち追加時に
  発行されるID、line-user-id-linking-design.md参照)へ変換する必要があるが、
  この変換テーブル自体がまだどこにも書き込まれていなかった(フェーズ96時点では
  常に`None`を返す暫定実装)。
- 変換テーブルへの書き込みタイミングは「ユーザーがStripe Checkoutで決済を完了した瞬間」
  とする。Stripe Checkout Session作成時に`client_reference_id`へ内部`user_id`を
  埋め込んでおけば(Checkout Session作成自体は本ventureの決済導線設計としてapplication
  -form-submission-flow-design.mdの延長線上にあるが、Checkout Session作成のUI・導線
  自体は未設計のため別課題として残す。本ドキュメントはWebhook受信側のみを扱う)、
  Stripeが送ってくる`checkout.session.completed`イベントの
  `data.object.client_reference_id`(=user_id)と`data.object.customer`
  (=新規発行されたstripe_customer_id)が1つのイベントに揃って届く。この2つを
  `user_profile`ストアへ書き込むだけで変換テーブルが完成する。

## 2. データモデル

- `application_form_submission_flow.UserProfileStoreProtocol`を拡張し、
  `set_stripe_customer_id(user_id, stripe_customer_id)`(順引き)・
  `get_user_id_by_stripe_customer_id(stripe_customer_id) -> Optional[str]`
  (逆引き)を追加する(`gym_area_pairs`の読み書きと同じ`user_profile/{user_id}`
  ドキュメントに同居させる想定。実Firestoreでは逆引き用に別コレクション
  `stripe_customer_index/{stripe_customer_id} = {user_id}`を用意し、
  `set_stripe_customer_id()`内で2箇所へのバッチ書き込みとして実装する想定)。
- `InMemoryUserProfileStore`は順引き・逆引き両方の辞書を保持するスタブとして実装する。

## 3. Webhookイベント処理

- 新規関数`handle_checkout_session_completed(event, store)`
  (`stripe_webhook.py`)を追加する。`event["data"]["object"]`から
  `client_reference_id`・`customer`を取り出し、両方が非空文字列の場合のみ
  `store.set_stripe_customer_id(client_reference_id, customer)`を呼ぶ。
  いずれかが欠落・非文字列・空文字列の場合は書き込みを行わない
  (`customer.subscription.*`側の`resolve_user_id`が引き続き`None`を返すだけで、
  実害は生じない安全側の設計)。
- `receive_stripe_webhook()`に新しい省略可能引数`user_profile_store`を追加する。
  イベント種別が`checkout.session.completed`の場合、`dispatch_stripe_event()`
  (`customer.subscription.*`専用)へは渡さず、`handle_checkout_session_completed()`
  へ振り分ける。`user_profile_store`が渡されていない場合は何もせず200を返す
  (フェーズ94の「対象外のイベント種別は無視して200」という既存方針を踏襲)。
  署名検証・JSONパースの分岐(401/400)はこれまで通り共通。
- `make_resolve_user_id(user_profile_store) -> Callable[[str], Optional[str]]`を
  新設し、`user_profile_store.get_user_id_by_stripe_customer_id`をそのまま返す薄い
  ファクトリとする(`dispatch_stripe_event()`の`resolve_user_id`引数の型と一致させる
  ため)。

## 4. `get_stripe_runtime_dependencies()`の更新

- 1つの`InMemoryUserProfileStore()`インスタンスを生成し、`resolve_user_id`と
  `user_profile_store`の両方に同じインスタンスを渡す(`checkout.session.completed`で
  書き込んだ内容を同一プロセス内の`customer.subscription.*`解決で読めるようにするため)。
- 従来通りプロセス起動ごとに初期化されるため、実Cloud Functions環境では
  呼び出しをまたいで紐付けが保持されない(フェーズ96で`store`について指摘した限界と
  同じ)。実Firestore接続までは、同一Webhookエンドポイントへの呼び出し順序
  (`checkout.session.completed`が先に届き、後続の`customer.subscription.*`が
  同一コールドスタート内で処理される場合)にのみ機能する暫定実装である。

## 残課題

- Stripe Checkout Session作成時に`client_reference_id`へ内部`user_id`を設定する
  導線(決済ボタン設置・Checkout Session作成API呼び出し)自体は本ドキュメントの
  範囲外で未設計。申込フォーム提出後の決済導線として別途設計が必要。
- `user_profile`をFirestore版に差し替える作業(フェーズ96からの持ち越し)。
- 本設計の導入前に決済済みだった既存顧客(もしいた場合)の`stripe_customer_id`は
  遡って紐付けられない。実運用開始前(実Stripeアカウント接続はオーナー承認待ち)の
  設計段階であるため現時点では影響なし。
