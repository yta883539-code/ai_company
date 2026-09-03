# Stripe Customer Portalセッション作成HTTPエンドポイントの設計(create_portal_session)

作成日: 2026-09-03(フェーズ148)

payment-failure-dunning-design.md 5節に「次回以降の課題」として残っていた、
「決済失敗からの復旧に必要な、既存サブスクリプションの支払い方法更新用Stripe Customer
Portal(Billing Portal)セッション作成エンドポイント自体の設計」を、
checkout-session-endpoint-design.md(フェーズ112)の`create_checkout_session()`と対称の
考え方(検証・実Stripe接続は外部から注入し、エントリポイント自体は薄い配線とテスト可能な
純粋関数にする)で設計する。

`cloud_function_webhook.py`の`PortalLinkProvider`Protocol(`get_portal_url(user_id) ->
Optional[str]`)は既存だが、その実装本体(実`stripe.billing_portal.Session.create()`
呼び出し)は未設計のまま残っていた。本ドキュメントはその実装本体が内部で使うHTTP
エンドポイント側の設計であり、`PortalLinkProvider`の具体的な実装(`StripePortalLinkProvider`
のようなクラス)自体は実Stripe接続確定後の課題として引き続き残す(6節参照)。

## 1. Checkout Session版との違い

- Checkout Sessionは「新規契約」なので`existing_stripe_customer_id`が無くてもよい
  (`build_checkout_session_params()`は`customer`キー省略で新規顧客作成に対応)。
- Portal Sessionは逆に「既存サブスクリプションの管理」が前提のため、
  `stripe_customer_id`が無いuser_idに対してはセッションを作成しようがない。
  よって`user_profile_store.get_stripe_customer_id(user_id)`が`None`を返す場合は、
  `build_checkout_session_params()`のような「省略して続行」ではなく、
  `status_code=404`・`error="no_stripe_customer"`で早期リターンする(新規会員が
  誤ってポータルリンクを踏んだ場合に不正な状態のセッションを作ろうとしないためのガード)。

## 2. 方針: `create_portal_session()`

`prototype/portal_session.py`(新規)に実装する。`checkout_session.py`と同じ
`verify_id_token`(LIFF IDトークン検証、未実装の間は`NotImplementedError`を送出する
プレースホルダ)・`user_profile_store`(`get_stripe_customer_id`のみを要求する最小限
Protocol、`checkout_session.UserProfileStoreProtocol`と同一の形だが循環インポートを
避けるため別定義とする)を呼び出し元から注入する。

```python
def create_portal_session(
    authorization_header: Optional[str],
    *,
    verify_id_token: Callable[[str], Optional[str]],
    user_profile_store: UserProfileStoreProtocol,
    return_url: str = DEFAULT_RETURN_URL,
) -> CreatePortalSessionResult:
```

`return_url`はポータル操作完了後にLINEへ戻るためのURL(`checkout_session.py`の
`success_url`/`cancel_url`と同じ位置づけの仮プレースホルダ)。

## 3. 処理順序

1. `authorization_header`が`None`、または`"Bearer "`で始まらない場合は、
   `verify_id_token`を呼ばずに`status_code=401`・
   `error="missing_or_malformed_authorization_header"`を返す
   (`create_checkout_session()`と同じ早期リターン方針)。
2. `"Bearer "`以降を`id_token`として取り出し`verify_id_token(id_token)`を呼ぶ。
3. `None`が返った場合は`status_code=401`・`error="invalid_id_token"`を返す。
4. 検証成功時は`user_profile_store.get_stripe_customer_id(user_id)`を呼ぶ。
5. 既存customerが無ければ(1節)`status_code=404`・`error="no_stripe_customer"`を返す
   (`verify_id_token`成功後の分岐であり、`user_id`自体は有効なユーザーである点に注意)。
6. 既存customerがあれば`build_portal_session_params(existing_stripe_customer_id,
   return_url=return_url)`を呼び、`status_code=200`・`portal_session_params`に結果を
   格納して返す。

`build_portal_session_params(stripe_customer_id, *, return_url=DEFAULT_RETURN_URL) -> dict`
は`{"customer": stripe_customer_id, "return_url": return_url}`を返すだけの単純な組み立て
関数(`stripe.billing_portal.Session.create(**params)`へそのまま渡す想定のdict)。
`stripe_customer_id`が空文字列・Noneの場合は`ValueError`(`build_checkout_session_params()`の
`user_id`ガードと同じ位置づけだが、`create_portal_session()`側で4節のガードを既に
通過しているため通常到達しない)。

`CreatePortalSessionResult`(dataclass)は`status_code: int`・
`portal_session_params: Optional[dict]`(成功時のみ)・`error: Optional[str]`(失敗時のみ)の
3フィールドとし、`CreateCheckoutSessionResult`と同じ形にする。

## 4. `main(request)`エントリポイント

`checkout_session.py`の`main(request)`と対称の構成とする。

- `get_portal_runtime_dependencies()`が`user_profile_store`(`InMemoryUserProfileStore()`)・
  `verify_id_token`(`_verify_id_token_not_implemented`、`checkout_session.py`と同一のダミー
  ―呼ばれたら`NotImplementedError`を送出)の既定値を組み立てる。
- `main(request)`は`request.headers.get("Authorization")`を取り出し
  `create_portal_session()`に委譲、`NotImplementedError`発生時は`("verify_id_token_not_implemented",
  501)`を返す。成功時(200)は`portal_session_params`をそのまま返し、失敗時は
  `(error, status_code)`を返す。

## 5. テスト方針

`prototype/test_portal_session.py`に`test_checkout_session.py`と対称のテストを新設する。

1. 認証ヘッダ欠落・非Bearer形式は401、`verify_id_token`未呼び出し。
2. `verify_id_token`が`None`を返す場合は401、`user_profile_store`への問い合わせなし。
3. 検証成功だが`stripe_customer_id`未登録のuser_idは404・`error="no_stripe_customer"`。
4. 検証成功かつ`stripe_customer_id`登録済みのuser_idは200・
   `portal_session_params == {"customer": <該当id>, "return_url": DEFAULT_RETURN_URL}`。
5. `return_url`を明示指定した場合、`portal_session_params`に反映されること。
6. `main(request)`版: 認証ヘッダ欠落は401、Bearer形式だが`verify_id_token`未実装時は501。

## 6. 残課題

- `PortalLinkProvider`(`cloud_function_webhook.py`)の実装本体
  (`StripePortalLinkProvider`のようなクラスで`get_portal_url(user_id)`を実装し、内部で
  本エンドポイントの`create_portal_session()`相当のロジック+実`stripe.billing_portal.
  Session.create()`呼び出しを行う)は、実Stripeアカウント接続(オーナー承認待ち、
  pending-approval.md参照)後の課題として残す。
- `verify_id_token`の実装本体・`main(request)`の実Cloud Functionsデプロイは、
  checkout-session-endpoint-design.md「残課題」と同じくLIFFアプリ実登録・実接続後の
  課題として残る。
- `return_url`のプレースホルダ(`DEFAULT_RETURN_URL`)は、実LPドメイン確定後に
  `checkout_session.py`の`DEFAULT_SUCCESS_URL`/`DEFAULT_CANCEL_URL`と合わせて一括更新する
  想定(個別の暫定対応は不要)。
