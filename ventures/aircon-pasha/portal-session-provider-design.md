# Stripe Customer Portalリンク提供(PortalLinkProvider)実装本体の設計

作成日: 2026-09-03(フェーズ176)

`cloud_function_webhook.py`の`PortalLinkProvider`Protocol(`get_portal_url(user_id) ->
Optional[str]`)は既存だが、その実装本体(実`stripe.billing_portal.Session.create()`
呼び出し)は未設計のまま、`InMemoryPortalLinkProvider`(検証用の固定URLスタブ)のみが
存在していた。course-set-pashaがフェーズ148・149で実装した
`customer-portal-session-endpoint-design.md`/`StripePortalLinkProvider`と同じ考え方で、
本venture向けの実装本体を設計する。

## 1. course-set-pasha版との違い

本ventureのCheckout Session作成は、course-set-pasha・line-reservation-aiと異なりLIFF
IDトークン検証を経由しない。LINEのpostbackイベント(`source.userId`はLINEプラットフォーム
自身が認証済みの値)をuser_idの取得元とする設計(`checkout_session.py`冒頭コメント参照)。
Billing Portalリンクの取得(`PortalLinkProvider.get_portal_url`)も同様に、呼び出し元
(`render_subscription_procedure_notice()`等、webhook処理の中で既に解決済みのuser_idを
渡す)であり、LIFF IDトークン検証を伴うHTTPエンドポイント(course-set-pashaの
`create_portal_session()`)は本ventureには不要と判断した。したがって本ドキュメントは
`PortalLinkProvider`の実装本体(`StripePortalLinkProvider`クラス)のみを設計対象とし、
HTTPエンドポイント自体は設計しない。

## 2. `get_stripe_customer_id`の追加

`StripePortalLinkProvider`がstripe_customer_idの有無判定に使う順引きgetter
(`user_id_linking.UserProfileStoreProtocol.get_stripe_customer_id(user_id) ->
Optional[str]`)は、`UserProfileStoreProtocol`のdocstringに「現時点でどこからも呼ばれない
ため未追加」と明記されていた通り存在しなかった。本フェーズで`user_id_linking.py`の
`UserProfileStoreProtocol`/`InMemoryUserProfileStore`に追加した(既存の
`UserProfile.stripe_customer_id`フィールドをそのまま読むだけの単純なgetter、未知の
`user_id`に対しては`None`を返す)。

## 3. `StripePortalLinkProvider`の設計

`prototype/portal_session.py`(新規)に実装する。course-set-pasha版と同様、循環インポートを
避けるため`user_id_linking.UserProfileStoreProtocol`を直接importせず、
`get_stripe_customer_id(user_id)`のみを要求する最小限のProtocolを別定義する
(`checkout_session.py`は本venture側にProtocol定義自体を持たないため、course-set-pashaの
`portal_session.UserProfileStoreProtocol`と同じ形を新設する)。

```python
class UserProfileStoreProtocol(Protocol):
    def get_stripe_customer_id(self, user_id: str) -> Optional[str]: ...

def build_portal_session_params(
    stripe_customer_id: str, *, return_url: str = DEFAULT_RETURN_URL
) -> dict:
    """{"customer": stripe_customer_id, "return_url": return_url} を返す。
    stripe_customer_idが空文字列・NoneならValueError。"""

class StripePortalLinkProvider:
    def __init__(
        self,
        user_profile_store: UserProfileStoreProtocol,
        *,
        session_creator: Callable[[dict], Optional[str]] = (
            _create_billing_portal_session_not_implemented
        ),
        return_url: str = DEFAULT_RETURN_URL,
    ) -> None: ...

    def get_portal_url(self, user_id: str) -> Optional[str]:
        stripe_customer_id = self._user_profile_store.get_stripe_customer_id(user_id)
        if stripe_customer_id is None:
            return None
        params = build_portal_session_params(stripe_customer_id, return_url=self._return_url)
        return self._session_creator(params)
```

- `_create_billing_portal_session_not_implemented`は`checkout_session.py`等、本venture
  一貫の「未実装は呼ばれたら意図的に`NotImplementedError`を送出するプレースホルダ」方針を
  踏襲する(恒久的に失敗を返すダミーだと誤って動いているように見えてしまうため)。
- `DEFAULT_RETURN_URL`は`checkout_session.py`の`DEFAULT_SUCCESS_URL`/`DEFAULT_CANCEL_URL`と
  同じ、実LPドメイン確定までの仮プレースホルダ。

## 4. 構造的に`PortalLinkProvider`を満たすことの確認

`cloud_function_webhook.PortalLinkProvider`は`get_portal_url(user_id) -> Optional[str]`の
みを要求するProtocolであり、`StripePortalLinkProvider`はstructural typing(duck typing)に
よりこれを満たす(`cloud_function_webhook.py`を直接importしないため循環インポートも
起きない)。

## 5. 実装状況

`prototype/portal_session.py`に`UserProfileStoreProtocol`・`build_portal_session_params()`・
`StripePortalLinkProvider`・`_create_billing_portal_session_not_implemented()`を実装した。
`user_id_linking.py`に`get_stripe_customer_id`を追加した(2節)。テスト追加、venture全体
テストパスを確認済み(詳細はREADME.md本フェーズ参照)。

## 6. 今後の課題

- 実`stripe.billing_portal.Session.create()`呼び出し(`session_creator`差し替え)・
  呼び出し元(`get_runtime_dependencies()`等)を実際に`InMemoryPortalLinkProvider`から
  `StripePortalLinkProvider`へ差し替える配線は、実Stripeアカウント接続(オーナー承認待ち、
  pending-approval.md参照)後の課題として残る。
- `return_url`のプレースホルダ(`DEFAULT_RETURN_URL`)は、実LPドメイン確定後に
  `checkout_session.py`の`DEFAULT_SUCCESS_URL`/`DEFAULT_CANCEL_URL`と合わせて一括更新する
  想定(個別の暫定対応は不要)。
