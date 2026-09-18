#!/usr/bin/env python3
"""portal-session-provider-design.md(フェーズ129)で設計した、`cloud_function_webhook.
PortalLinkProvider`Protocol(`get_portal_url(user_id) -> Optional[str]`)の実装本体。

位置づけ:
- 本ventureは`stripe_customer_id`が`craftsman_workshop/{workshop_id}`側のフィールドで
  あるため、他venture3件(user_id単位で1ホップ解決)と異なり`user_id → workshop_id →
  stripe_customer_id`の2ホップ解決が必要になる(design 1節)。
- Billing Portalは支払い方法変更・解約等を行える画面であり、checkout-initiation-flow-
  design.mdのCheckout Session開始と同じ「契約者本人限定」の権限モデルを適用する
  (design 1節)。共同利用メンバーや未紐付けのuser_idはURLを取得できず`None`を返す。
- 実Stripe Billing Portalセッション作成API呼び出しは実アカウント接続後の話であり、外部
  サービスへの設定・実HTTPリクエスト送信を伴うためオーナー承認待ち(pending-approval.md参照)。

設計の参照元: portal-session-provider-design.md
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

# design 2節: 実LPドメイン確定までの仮のプレースホルダ。checkout_session.pyの
# DEFAULT_SUCCESS_URL/DEFAULT_CANCEL_URLと合わせて実LPドメイン確定後に一括更新する想定。
DEFAULT_RETURN_URL = "https://example.com/kura-pasha/portal/return"


class UserProfileStoreProtocol(Protocol):
    """StripePortalLinkProviderが必要とする部分のみを表す最小限のProtocol。

    実体はusage_counter_workshop.UserProfileStoreProtocol(get_workshop_id実装済み)を
    満たすストアを想定するが、循環インポートを避けるためここでは`get_workshop_id`のみを
    持つ最小限の別Protocolとして定義する(structural typingのため同一ストアインスタンスを
    そのまま渡せる)。
    """

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        ...


class WorkshopStoreProtocol(Protocol):
    """StripePortalLinkProviderが必要とする部分のみを表す最小限のProtocol。

    実体はusage_counter_workshop.WorkshopStoreProtocol(get_contractor_user_id・
    get_stripe_customer_id実装済み)を満たすストアを想定するが、循環インポートを避けるため
    ここでは必要な2メソッドのみを持つ最小限の別Protocolとして定義する。
    """

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...

    def get_stripe_customer_id(self, workshop_id: str) -> Optional[str]:
        ...


def build_portal_session_params(
    stripe_customer_id: str,
    *,
    return_url: str = DEFAULT_RETURN_URL,
) -> dict:
    """Stripe Billing Portalセッション作成APIへ渡すパラメータを組み立てる(design 2節)。

    `stripe_customer_id`が空文字列・Noneの場合は`ValueError`。`StripePortalLinkProvider.
    get_portal_url()`側で既にNoneガードを通過している前提で、通常このガードには到達しない。
    """
    if not stripe_customer_id:
        raise ValueError("stripe_customer_id must be a non-empty string")

    return {
        "customer": stripe_customer_id,
        "return_url": return_url,
    }


def _create_billing_portal_session_not_implemented(params: dict) -> Optional[str]:
    """`cloud_function_webhook.PortalLinkProvider`実装本体が内部で使う、実
    `stripe.billing_portal.Session.create(**params)`呼び出しのプレースホルダ。

    `checkout_session.py`等、本venture一貫の「未実装は呼ばれたら意図的に
    `NotImplementedError`を送出するプレースホルダ」方針を踏襲する(恒久的に失敗を返す
    ダミーだと誤って動いているように見えてしまうため)。実Stripeアカウント接続(オーナー
    承認待ち、pending-approval.md参照)後、この関数を実API呼び出しへ差し替えるだけで
    `StripePortalLinkProvider`がそのまま動く設計とする。
    """
    raise NotImplementedError(
        "billing_portal_session_creator is not implemented yet: pending real Stripe "
        "account connection (owner approval required, see pending-approval.md)"
    )


class StripePortalLinkProvider:
    """`cloud_function_webhook.PortalLinkProvider`Protocol(`get_portal_url(user_id) ->
    Optional[str]`)の実装本体(design 2節)。

    `user_id → workshop_id`解決・契約者本人確認・`stripe_customer_id`の有無判定・
    `build_portal_session_params()`によるパラメータ組み立てまでを本クラスに集約し、実
    `stripe.billing_portal.Session.create()`呼び出し自体のみを`session_creator`として
    外部から差し替え可能にする(`checkout_session.py`と同じ注入パターン)。

    Structural typing(Protocol)により`cloud_function_webhook.PortalLinkProvider`を
    直接importせずとも構造的に満たせるため、本venture一貫の「循環インポートを避けるため
    再定義する」方針をここでも踏襲する。
    """

    def __init__(
        self,
        user_profile_store: UserProfileStoreProtocol,
        workshop_store: WorkshopStoreProtocol,
        *,
        session_creator: Callable[[dict], Optional[str]] = (
            _create_billing_portal_session_not_implemented
        ),
        return_url: str = DEFAULT_RETURN_URL,
    ) -> None:
        self._user_profile_store = user_profile_store
        self._workshop_store = workshop_store
        self._session_creator = session_creator
        self._return_url = return_url

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


def _demo() -> None:
    class _StubUserProfileStore:
        def __init__(self) -> None:
            self._workshop_ids = {"u_contractor": "w1", "u_member": "w1"}

        def get_workshop_id(self, user_id: str) -> Optional[str]:
            return self._workshop_ids.get(user_id)

    class _StubWorkshopStore:
        def __init__(self) -> None:
            self._contractor_user_ids = {"w1": "u_contractor"}
            self._stripe_customer_ids = {"w1": "cus_123"}

        def get_contractor_user_id(self, workshop_id: str) -> str:
            return self._contractor_user_ids[workshop_id]

        def get_stripe_customer_id(self, workshop_id: str) -> Optional[str]:
            return self._stripe_customer_ids.get(workshop_id)

    def _fake_session_creator(params: dict) -> Optional[str]:
        return f"https://billing.stripe.com/p/session/fake?customer={params['customer']}"

    provider = StripePortalLinkProvider(
        _StubUserProfileStore(), _StubWorkshopStore(), session_creator=_fake_session_creator
    )
    print(f"u_contractor -> {provider.get_portal_url('u_contractor')}")
    print(f"u_member (契約者ではない) -> {provider.get_portal_url('u_member')}")
    print(f"u_unknown (未紐付け) -> {provider.get_portal_url('u_unknown')}")


if __name__ == "__main__":
    _demo()
