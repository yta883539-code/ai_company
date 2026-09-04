#!/usr/bin/env python3
"""portal-session-provider-design.md(フェーズ続き192)で発見した設計ギャップに対応する、
`PortalLinkProvider`Protocol(`get_portal_url(store_id) -> Optional[str]`)の定義と実装本体
(フェーズ続き193)。

位置づけ:
- aircon-pasha/course-set-pashaの`PortalLinkProvider`パターン(stateに保存せず、
  必要になった瞬間に都度URLを生成するコールバック)を本ventureにも導入する。design 3節の
  通り、本venture固有の事情(LIFF IDトークン検証を経由しないaircon-pasha方式が
  そのまま当てはまる)を踏まえ、aircon-pasha/prototype/portal_session.pyの設計をほぼ
  そのまま流用した。
- 本ventureにはaircon-pashaのような一元管理場所(`cloud_function_webhook.py`)が
  無いため、`PortalLinkProvider`Protocol自体もここで新規定義する(store_profile_store.
  PLAN_MONTHLY_BOOKING_LIMITSの docstring と同じ判断)。
- 実Stripe Billing Portalセッション作成API呼び出しは実アカウント接続後の話であり、外部
  サービスへの設定・実HTTPリクエスト送信を伴うためオーナー承認待ち(pending-approval.md参照)。

設計の参照元: portal-session-provider-design.md
"""

from __future__ import annotations

from typing import Callable, Optional, Protocol

# design 4節: 実LPドメイン確定までの仮のプレースホルダ。checkout_session.pyの
# 成功/キャンセルURL(実装時に確定予定)と合わせて実LPドメイン確定後に一括更新する想定。
DEFAULT_RETURN_URL = "https://example.com/line-reservation-ai/portal/return"


class PortalLinkProvider(Protocol):
    """Stripe Billing Portalのセッション作成(顧客ごとに都度発行される一時URL)を表す
    差し替え可能なProtocol(aircon-pasha/course-set-pashaの同名Protocolと同じ契約)。
    取得できない場合はNoneを返す契約とする。"""

    def get_portal_url(self, store_id: str) -> Optional[str]:
        ...


class InMemoryPortalLinkProvider:
    """実Stripe接続の代わりに固定URL(またはNone)を返す検証用スタブ。"""

    def __init__(self, url: Optional[str] = "https://billing.stripe.com/p/session/stub") -> None:
        self._url = url

    def get_portal_url(self, store_id: str) -> Optional[str]:
        return self._url


class StoreProfileStoreProtocol(Protocol):
    """`StripePortalLinkProvider`が必要とする部分のみを表す最小限のProtocol。

    実体は`store_profile_store.StoreProfileStoreProtocol`(`get_stripe_customer_id`実装済み)
    を満たすストアを想定するが、循環インポートを避けるためここでは`get_stripe_customer_id`
    のみを持つ最小限の別Protocolとして定義する(aircon-pasha/course-set-pashaの
    portal_session.UserProfileStoreProtocolと同じ形、structural typingのため同一
    ストアインスタンスをそのまま渡せる)。
    """

    def get_stripe_customer_id(self, store_id: str) -> Optional[str]:
        ...


def build_portal_session_params(
    stripe_customer_id: str,
    *,
    return_url: str = DEFAULT_RETURN_URL,
) -> dict:
    """Stripe Billing Portalセッション作成APIへ渡すパラメータを組み立てる(design 4節)。

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
    """`PortalLinkProvider`実装本体が内部で使う、実`stripe.billing_portal.Session.
    create(**params)`呼び出しのプレースホルダ。

    checkout_session.py等、本venture一貫の「未実装は呼ばれたら意図的に
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
    """`PortalLinkProvider`Protocol(`get_portal_url(store_id) -> Optional[str]`)の
    実装本体(design 4節)。

    `stripe_customer_id`の有無判定・`build_portal_session_params()`によるパラメータ
    組み立てまでを本クラスに集約し、実`stripe.billing_portal.Session.create()`呼び出し
    自体のみを`session_creator`として外部から差し替え可能にする(`checkout_session.py`と
    同じ注入パターン)。
    """

    def __init__(
        self,
        store_profile_store: StoreProfileStoreProtocol,
        *,
        session_creator: Callable[[dict], Optional[str]] = (
            _create_billing_portal_session_not_implemented
        ),
        return_url: str = DEFAULT_RETURN_URL,
    ) -> None:
        self._store_profile_store = store_profile_store
        self._session_creator = session_creator
        self._return_url = return_url

    def get_portal_url(self, store_id: str) -> Optional[str]:
        stripe_customer_id = self._store_profile_store.get_stripe_customer_id(store_id)
        if stripe_customer_id is None:
            return None
        params = build_portal_session_params(stripe_customer_id, return_url=self._return_url)
        return self._session_creator(params)


def _demo() -> None:
    class _StubStoreProfileStore:
        def __init__(self) -> None:
            self._stripe_customer_ids = {"store-1": "cus_123"}

        def get_stripe_customer_id(self, store_id: str) -> Optional[str]:
            return self._stripe_customer_ids.get(store_id)

    def _fake_session_creator(params: dict) -> Optional[str]:
        return f"https://billing.stripe.com/p/session/fake?customer={params['customer']}"

    provider = StripePortalLinkProvider(
        _StubStoreProfileStore(), session_creator=_fake_session_creator
    )
    print(f"store-1 -> {provider.get_portal_url('store-1')}")
    print(f"store-2 (no stripe_customer_id) -> {provider.get_portal_url('store-2')}")


if __name__ == "__main__":
    _demo()
