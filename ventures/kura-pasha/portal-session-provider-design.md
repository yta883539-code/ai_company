# Stripe Customer Portalリンク提供(PortalLinkProvider)実装本体の設計

作成日: 2026-09-18(フェーズ129)

`prototype/cloud_function_webhook.py`の`PortalLinkProvider`Protocol(`get_portal_url(user_id)
-> Optional[str]`)は既存だが、その実装本体(実`stripe.billing_portal.Session.create()`
呼び出し)は未設計のまま、`InMemoryPortalLinkProvider`(検証用の固定URLスタブ)のみが
存在していた。payment-failure-dunning-design.md 1節・6節、subscription-cancellation-
scheduled-notification-design.md 5節がいずれも「本venture側にはCustomer Portal相当のURL
発行(`PortalLinkProvider`)が未実装」を前提として通知文言へのURL差し込みを見送っていた
制約に対応し、aircon-pasha(portal-session-provider-design.md、フェーズ176)・course-set-
pashaと同じ考え方で、本venture向けの実装本体を設計する。

## 1. 他venture3件との違い(2ホップ解決・契約者限定)

- 他venture3件は`stripe_customer_id`を`user_profile/{user_id}`(またはそれに相当する
  ユーザー単位のストア)に直接持つため、`user_id`から1ホップで解決できる。
- 本ventureはsubscription-billing-data-model-design.md 1節の設計通り、`stripe_customer_id`は
  `craftsman_workshop/{workshop_id}`側のフィールドであり、`user_profile/{user_id}`には
  `workshop_id`しか持たない。そのため`user_id → workshop_id`
  (`UserProfileStoreProtocol.get_workshop_id`)→`workshop_id → stripe_customer_id`
  (`WorkshopStoreProtocol.get_stripe_customer_id`)という2ホップの解決が必要になる。
- 本ventureはcraftsman-account-linking-design.mdの通り1つのworkshopに契約者
  (`contractor_user_id`)1名と複数の共同利用メンバー(`member_user_ids`)が同居しうる。
  Billing Portalは支払い方法の変更・プラン変更・解約操作を行える画面であり、
  checkout-initiation-flow-design.md 3節手順3が「契約者本人以外からのCheckout開始要求は
  `CONTRACTOR_ONLY_CHECKOUT_NOTICE`で打ち切る」と定めているのと同じ権限モデルを、
  Billing Portalリンクの発行自体にも適用する必要がある(他venture3件は契約者=ユーザー本人が
  常に一致するため、この判定が不要だった)。したがって`StripePortalLinkProvider`は
  `user_id`が対象workshopの`contractor_user_id`と一致しない場合、URLを発行せず`None`を
  返す。

## 2. `StripePortalLinkProvider`の設計

`prototype/portal_session.py`(新規)に実装する。他venture3件と同様、循環インポートを
避けるため`usage_counter_workshop.UserProfileStoreProtocol`/`WorkshopStoreProtocol`を
直接importせず、`StripePortalLinkProvider`が必要とする最小限のメソッドのみを持つ別
Protocolをここに新設する(structural typingにより、同一のストアインスタンスを
そのまま渡せる)。

```python
class UserProfileStoreProtocol(Protocol):
    def get_workshop_id(self, user_id: str) -> Optional[str]: ...

class WorkshopStoreProtocol(Protocol):
    def get_contractor_user_id(self, workshop_id: str) -> str: ...
    def get_stripe_customer_id(self, workshop_id: str) -> Optional[str]: ...

def build_portal_session_params(
    stripe_customer_id: str, *, return_url: str = DEFAULT_RETURN_URL
) -> dict:
    """{"customer": stripe_customer_id, "return_url": return_url} を返す。
    stripe_customer_idが空文字列・NoneならValueError。"""

class StripePortalLinkProvider:
    def __init__(
        self,
        user_profile_store: UserProfileStoreProtocol,
        workshop_store: WorkshopStoreProtocol,
        *,
        session_creator: Callable[[dict], Optional[str]] = (
            _create_billing_portal_session_not_implemented
        ),
        return_url: str = DEFAULT_RETURN_URL,
    ) -> None: ...

    def get_portal_url(self, user_id: str) -> Optional[str]:
        workshop_id = self._user_profile_store.get_workshop_id(user_id)
        if workshop_id is None:
            return None
        if self._workshop_store.get_contractor_user_id(workshop_id) != user_id:
            return None
        stripe_customer_id = self._workshop_store.get_stripe_customer_id(workshop_id)
        if stripe_customer_id is None:
            return None
        params = build_portal_session_params(stripe_customer_id, return_url=self._return_url)
        return self._session_creator(params)
```

解決順序は「workshop未紐付け→契約者不一致→stripe_customer_id未登録」の順とする。
契約者不一致を先に判定することで、共同利用メンバーが誤って(トライアル中等で)
`stripe_customer_id`が存在しないworkshopに属していても、常に同じ理由(`None`)で
URL非発行となり、呼び出し元(`render_subscription_procedure_notice()`)が原因を区別
できなくても安全側の挙動(`PORTAL_LINK_UNAVAILABLE_FALLBACK`)に倒れる。

- `_create_billing_portal_session_not_implemented`は`checkout_session.py`等、本venture
  一貫の「未実装は呼ばれたら意図的に`NotImplementedError`を送出するプレースホルダ」方針を
  踏襲する(恒久的に失敗を返すダミーだと誤って動いているように見えてしまうため)。
- `DEFAULT_RETURN_URL`は`checkout_session.py`の`DEFAULT_SUCCESS_URL`/`DEFAULT_CANCEL_URL`と
  同じ、実LPドメイン確定までの仮プレースホルダ。

## 3. 構造的に`PortalLinkProvider`を満たすことの確認

`cloud_function_webhook.PortalLinkProvider`は`get_portal_url(user_id) -> Optional[str]`の
みを要求するProtocolであり、`StripePortalLinkProvider`はstructural typing(duck typing)に
よりこれを満たす(`cloud_function_webhook.py`を直接importしないため循環インポートも
起きない)。

## 4. 実装状況

`prototype/portal_session.py`に`UserProfileStoreProtocol`・`WorkshopStoreProtocol`・
`build_portal_session_params()`・`StripePortalLinkProvider`・
`_create_billing_portal_session_not_implemented()`を実装した。`prototype/test_portal_session.py`
に契約者一致/不一致・workshop未紐付け・stripe_customer_id未登録・デフォルトsession_creator
未実装の各ケースを検証するテストを追加した。

## 5. 今後の課題

- 実`stripe.billing_portal.Session.create()`呼び出し(`session_creator`差し替え)・
  呼び出し元(`get_runtime_dependencies()`等)を実際に`InMemoryPortalLinkProvider`から
  `StripePortalLinkProvider`へ差し替える配線は、実Stripeアカウント接続(オーナー承認待ち、
  pending-approval.md参照)後の課題として残る。
- payment-failure-dunning-design.md 4節の決済失敗通知文言、subscription-cancellation-
  scheduled-notification-design.md等、現時点で「PortalLinkProvider相当が未実装のため
  URLを差し込まない」としている各通知文言への実際のURL差し込みは、上記の実Stripe接続後、
  本設計の`StripePortalLinkProvider`を差し替えるのと同じタイミングでまとめて対応する
  (個別の暫定対応は不要)。
- `return_url`のプレースホルダ(`DEFAULT_RETURN_URL`)は、実LPドメイン確定後に
  `checkout_session.py`の`DEFAULT_SUCCESS_URL`/`DEFAULT_CANCEL_URL`と合わせて一括更新する
  想定(個別の暫定対応は不要)。
