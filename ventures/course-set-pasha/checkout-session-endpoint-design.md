# Checkout Session作成HTTPエンドポイントの設計(create_checkout_session)

作成日: 2026-08-24(フェーズ112)

checkout-initiation-flow-design.md(フェーズ98)3節で設計にとどまっていた
`create_checkout_session(request)`エンドポイント本体のうち、実LIFF登録・実Stripe API接続
(いずれもオーナー承認待ち)を要さない範囲――IDトークン検証結果を受け取ってから
`build_checkout_session_params()`(フェーズ98・prototype/checkout_session.py)に橋渡しする
までの処理――を、stripe-webhook-http-entry-point-design.md(フェーズ95)の
`receive_stripe_webhook()`と同じ考え方(検証・解決の実装は外部から注入し、エントリポイント
自体は薄い配線とテスト可能な純粋関数にする)で設計する。

## 1. 方針: `create_checkout_session()`

`prototype/checkout_session.py`に追加する。実LINE Platform API呼び出し
(`verify_id_token`)・実`user_profile`ストア接続(`user_profile_store`)はいずれも呼び出し元
から注入する依存とし、本関数自体は実HTTPリクエスト・実DB接続なしでテスト可能にする。

```python
def create_checkout_session(
    authorization_header: Optional[str],
    *,
    verify_id_token: Callable[[str], Optional[str]],
    user_profile_store: UserProfileStoreProtocol,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> CreateCheckoutSessionResult:
```

`verify_id_token`は「LIFF IDトークン文字列を受け取り、検証成功時はLINEのuserId
(本ventureの`user_id`)、失敗時は`None`を返す」というインターフェースのみを定義し、実装
(LINE Platform APIの`/oauth2/v2.1/verify`相当への実HTTPリクエスト)はLIFFアプリ実登録後の
課題として残す(checkout-initiation-flow-design.md「残課題」3点目と同じ)。
`resolve_user_id`(stripe-webhook-http-entry-point-design.md)を実装本体と切り離して注入した
のと同じ考え方。

## 2. 処理順序

1. `authorization_header`が`None`、または`"Bearer "`で始まらない場合は、
   `verify_id_token`を呼ばずに`status_code=401`・`error="missing_or_malformed_authorization_header"`
   を返す(不正なリクエストへの余計な処理を避ける、stripe版と同じ早期リターン方針)。
2. `"Bearer "`以降を`id_token`として取り出し、`verify_id_token(id_token)`を呼ぶ。空文字列
   (`"Bearer "`のみ)の場合も同様に`verify_id_token`へ渡す(空文字列の妥当性判断は
   `verify_id_token`側の責務とし、エントリポイント側では判定しない)。
3. `verify_id_token`が`None`を返した場合(トークン無効・期限切れ等)は
   `status_code=401`・`error="invalid_id_token"`を返す。
4. 検証成功時は得られた`user_id`で`user_profile_store.get_stripe_customer_id(user_id)`を
   呼び、既存customerの有無を確認する。
5. `build_checkout_session_params(user_id, existing_stripe_customer_id, success_url=success_url,
   cancel_url=cancel_url)`を呼び、`status_code=200`・`checkout_session_params`に結果を格納して
   返す(`user_id`は`verify_id_token`成功時点で非空文字列であることが保証されているため、
   `build_checkout_session_params`の`ValueError`ガードには通常到達しない)。

実Stripe Checkout Session作成API呼び出し自体(`stripe.checkout.Session.create(**params)`
相当)は本関数の範囲外のまま据え置く。`checkout_session_params`を組み立てて返すところまでを
本関数のスコープとし、実際にStripe APIへ渡す処理は実アカウント接続後(オーナー承認待ち)の
配線として残す。

`CreateCheckoutSessionResult`(dataclass)は`status_code: int`・
`checkout_session_params: Optional[dict]`(成功時のみ)・`error: Optional[str]`(失敗時のみ)の
3フィールドとし、`StripeWebhookReceiverResult`と同じ形にする。

## 3. テスト方針

`prototype/test_checkout_session.py`に`CreateCheckoutSessionTest`を新設し、
最低限次のケースをカバーする。

1. `authorization_header=None`は401・`error="missing_or_malformed_authorization_header"`、
   かつ`verify_id_token`が一切呼ばれないこと。
2. `"Bearer "`で始まらないヘッダ(例: `"Basic xxx"`)も同様に401、`verify_id_token`未呼び出し。
3. `verify_id_token`が`None`を返す(無効トークン)場合は401・`error="invalid_id_token"`、
   `user_profile_store`への問い合わせが発生しないこと。
4. 新規ユーザー(既存`stripe_customer_id`なし)は200・`checkout_session_params`に
   `customer`キーが含まれないこと。
5. 既存customerを持つユーザーは200・`checkout_session_params["customer"]`が
   `get_stripe_customer_id()`の返り値と一致すること。
6. `success_url`/`cancel_url`を明示指定した場合、`checkout_session_params`に反映されること。

## 残課題

- `verify_id_token`の実装本体(LINE Platform API `/oauth2/v2.1/verify`への実HTTPリクエスト)は
  LIFFアプリ実登録後(オーナー承認待ち)の課題として残る。
- `main(request)`相当(実Cloud Functionsの`functions_framework`リクエストオブジェクトからの
  `Authorization`ヘッダ取り出し・`user_profile_store`の実インスタンス化配線)は、
  stripe-webhook-http-entry-point-design.mdが残した`main(request)`配線と同様、実接続確定後の
  課題として残す。
- `checkout_session_params`を実際にStripe Checkout Session作成APIへ渡す呼び出し
  (`stripe.checkout.Session.create(**params)`)・返り値のURLをレスポンスとして返す処理は、
  実Stripeアカウント接続(オーナー承認待ち)後の課題として残る。
