#!/usr/bin/env python3
"""portal-session-provider-design.md(フェーズ176)で設計した、`cloud_function_webhook.
PortalLinkProvider`Protocol(`get_portal_url(user_id) -> Optional[str]`)の実装本体。

位置づけ:
- 実LIFF IDトークン検証は本ventureのCheckout Session作成と同様に不要(postbackイベントの
  `source.userId`がLINEプラットフォーム自身に認証済みのため)。本モジュールはLIFF検証を
  伴うHTTPエンドポイントではなく、既に解決済みのuser_idからBilling Portalセッション作成API
  へ渡すパラメータを組み立て、実`stripe.billing_portal.Session.create()`呼び出し自体のみを
  外部から差し替え可能にしたもの(course-set-pasha/prototype/portal_session.pyの
  `StripePortalLinkProvider`と同じ位置づけだが、LIFF検証を伴う`create_portal_session()`
  エンドポイントは本ventureには存在しない)。
- 実Stripe Billing Portalセッション作成API呼び出しは実アカウント接続後の話であり、外部
  サービスへの設定・実HTTPリクエスト送信を伴うためオーナー承認待ち(pending-approval.md参照)。

設計の参照元: portal-session-provider-design.md
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

# design 3節: 実LPドメイン確定までの仮のプレースホルダ。checkout_session.pyの
# DEFAULT_SUCCESS_URL/DEFAULT_CANCEL_URLと合わせて実LPドメイン確定後に一括更新する想定。
DEFAULT_RETURN_URL = "https://example.com/aircon-pasha/portal/return"


class UserProfileStoreProtocol(Protocol):
    """StripePortalLinkProviderが必要とする部分のみを表す最小限のProtocol。

    実体はuser_id_linking.UserProfileStoreProtocol(get_stripe_customer_id実装済み、
    design 2節)を満たすストアを想定するが、循環インポートを避けるためここでは
    `get_stripe_customer_id`のみを持つ最小限の別Protocolとして定義する(course-set-pasha
    のportal_session.UserProfileStoreProtocolと同一の形、structural typingのため同一
    ストアインスタンスをそのまま渡せる)。
    """

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        ...


def build_portal_session_params(
    stripe_customer_id: str,
    *,
    return_url: str = DEFAULT_RETURN_URL,
) -> dict:
    """Stripe Billing Portalセッション作成APIへ渡すパラメータを組み立てる(design 3節)。

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
    Optional[str]`)の実装本体(design 3節)。

    `stripe_customer_id`の有無判定・`build_portal_session_params()`によるパラメータ
    組み立てまでを本クラスに集約し、実`stripe.billing_portal.Session.create()`呼び出し
    自体のみを`session_creator`として外部から差し替え可能にする(`checkout_session.py`と
    同じ注入パターン)。

    Structural typing(Protocol)により`cloud_function_webhook.PortalLinkProvider`を
    直接importせずとも構造的に満たせるため、本venture一貫の「循環インポートを避けるため
    再定義する」方針をここでも踏襲する。
    """

    def __init__(
        self,
        user_profile_store: UserProfileStoreProtocol,
        *,
        session_creator: Callable[[dict], Optional[str]] = (
            _create_billing_portal_session_not_implemented
        ),
        return_url: str = DEFAULT_RETURN_URL,
    ) -> None:
        self._user_profile_store = user_profile_store
        self._session_creator = session_creator
        self._return_url = return_url

    def get_portal_url(self, user_id: str) -> Optional[str]:
        stripe_customer_id = self._user_profile_store.get_stripe_customer_id(user_id)
        if stripe_customer_id is None:
            return None
        params = build_portal_session_params(stripe_customer_id, return_url=self._return_url)
        return self._session_creator(params)


def _demo() -> None:
    class _StubUserProfileStore:
        def __init__(self) -> None:
            self._stripe_customer_ids = {"u1": "cus_123"}

        def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
            return self._stripe_customer_ids.get(user_id)

    def _fake_session_creator(params: dict) -> Optional[str]:
        return f"https://billing.stripe.com/p/session/fake?customer={params['customer']}"

    provider = StripePortalLinkProvider(
        _StubUserProfileStore(), session_creator=_fake_session_creator
    )
    print(f"u1 -> {provider.get_portal_url('u1')}")
    print(f"u2 (no stripe_customer_id) -> {provider.get_portal_url('u2')}")


if __name__ == "__main__":
    _demo()
