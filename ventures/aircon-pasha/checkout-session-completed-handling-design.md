# `checkout.session.completed`受信配線の設計

作成日: 2026-08-27(フェーズ128)

フェーズ127・stripe-webhook-http-entry-point-design.mdの「残課題」に明記していた、
`checkout.session.completed`イベントの受信配線を設計・実装する。course-set-pashaの
stripe-customer-id-linking-design.md(フェーズ97)・stripe-webhook-http-entry-point-design.md
(フェーズ95)と同じ位置づけだが、本ventureはuser-account-linking-design.md 4節のとおり
「Checkout Session作成時点で既にuser_idが判明している」という前提の違いがあるため、
その簡素化がどこに効くかを整理する。

## 1. `handle_checkout_session_completed()`

`prototype/stripe_webhook.py`に新設。`event.data.object.client_reference_id`
(=`user_id`、Checkout Session作成時に既知の値をそのまま設定してある)と
`event.data.object.customer`(=`stripe_customer_id`)を取り出し、
`UserProfileStoreProtocol.set_stripe_customer_id()`で`user_profile/{user_id}`へ
書き込む。course-set-pashaの`handle_checkout_session_completed()`とほぼ同じ処理だが、
以下の1点を追加した。

- course-set-pashaは決済(Checkout Session作成)時点でまだ`user_id`が確定していない
  ケースを前提に設計されているため、`store.set_stripe_customer_id()`はどんな`user_id`
  文字列でも書き込みを受け付ける(実質「新規`user_profile`の暗黙作成」も許容する)設計。
- 本ventureは逆に「Checkout Session作成時点で`user_profile`が既に存在している」ことを
  前提にしている(design 4節)ため、対応する`user_profile`が存在しない場合は想定外の
  順序(例: フォーム送信・LINE連携を経ずにStripeへ直接アクセスした等)とみなし、
  書き込みを行わず`error="user_profile_not_found"`として区別する。安全側に倒すことで、
  存在しない`user_id`へのゴミデータ書き込みを防ぐ。

`client_reference_id`・`customer`のいずれかが欠落・非文字列・空文字列の場合は
`error="missing_fields"`として何も書き込まない(course-set-pasha版と同じ安全側判定)。

## 2. `make_resolve_user_id()`

`customer.subscription.*`系イベント(`dispatch_stripe_event()`)が必要とする
`resolve_user_id: Callable[[str], Optional[str]]`を、`UserProfileStoreProtocol`の
`get_user_id_by_stripe_customer_id()`から作る薄いファクトリ。course-set-pashaの同名関数と
同じ位置づけ。これにより`checkout.session.completed`で書き込んだ紐付けを、後続の
`customer.subscription.deleted`等が正しく逆引きできることを
`test_stripe_webhook.py`の`ReceiveStripeWebhookCheckoutSessionCompletedTest.
test_subsequent_subscription_event_resolves_via_linked_profile`で一気通貫確認した。

## 3. `receive_stripe_webhook()`への配線

`user_profile_store`(省略可、`Optional[UserProfileStoreProtocol]`)引数を追加。
`event.type == "checkout.session.completed"`の場合は`dispatch_stripe_event()`へは
渡さず`handle_checkout_session_completed()`へ振り分け、`user_profile_store`が
渡されていなければ`error="store_not_configured"`のまま何もせず200を返す
(course-set-pashaと同じ「未接続でもリクエスト自体は受理する」方針)。それ以外の
イベント種別は従来通り`dispatch_stripe_event()`にそのまま委譲する。

## 4. 本venture固有の留意点(再掲・design 4節)

- Checkout Session作成時に`client_reference_id`パラメータへ既知の`user_id`を設定する
  処理自体(Stripe SDK呼び出し)は、実Stripeアカウント接続後の課題として引き続き残る。
  本フェーズはWebhook受信側(サーバー起点)の処理のみを対象とした。
- `stripe_customer_id → user_id`の逆引きストア実装(実Firestoreクエリ)も、実Stripe/
  実Firestore接続後の課題として残る。`InMemoryUserProfileStore`は検証用スタブ。

## 未検証・残課題

- `resolve_linking_code()`(LINE友だち追加時の連携コード解決)と`set_stripe_customer_id()`
  がどちらも同じ`user_profile/{user_id}`ドキュメントを更新する経路であり、実Firestore
  接続後は書き込み順序・競合(理論上は稀だが、LINE連携完了前にStripe決済が完了する
  レースコンディション)の検討が必要。MVPの想定顧客動線(onboarding-guide.mdステップ6の
  とおりLINE連携完了後にプラン選択)では発生しないため、本フェーズでは対応不要と判断し
  次回以降の課題として残す。
- `usage_counter`側の`upgraded_at`書き込み配線(course-set-pashaのtrial-end-scheduler-design.md
  2節相当)は、本venture側にまだ`usage_counter`のトライアル終了通知の実装自体が無いため
  今回は対象外。トライアル関連の実装に着手する際にあわせて検討する。
