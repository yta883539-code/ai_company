#!/usr/bin/env python3
"""customer-portal-session-endpoint-design.md(フェーズ148)で設計した、Stripe Customer
Portal(Billing Portal)セッション作成APIへ渡すパラメータを組み立てるロジック。

位置づけ:
- 実LIFF(LINE Front-end Framework)のIDトークン検証、実Stripe Billing Portalセッション
  作成API呼び出しはいずれも実アカウント接続後の話であり、外部サービスへの設定・実HTTP
  リクエスト送信を伴うためオーナー承認待ち(pending-approval.md参照)。
- 本モジュールはそれとは独立に、認証済み`user_id`(呼び出し元でLIFF IDトークン検証済みの
  前提)と既存`stripe_customer_id`の有無から、Billing Portalセッション作成APIへ渡す
  パラメータのdictを組み立てる部分のみを実HTTPリクエストなしで検証可能にしたもの。
  `checkout_session.py`と対称の構成(Checkout Session版は新規契約用、本モジュールは
  既存サブスクリプションの支払い方法更新用)。

設計の参照元: customer-portal-session-endpoint-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from application_form_submission_flow import InMemoryUserProfileStore

# design 3節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_RETURN_URL = "https://example.com/course-set-pasha/portal/return"


class UserProfileStoreProtocol(Protocol):
    """create_portal_session()が必要とする部分のみを表す最小限のProtocol。

    実体はapplication_form_submission_flow.UserProfileStoreProtocol
    (get_stripe_customer_id実装済み)を満たすストアを想定するが、循環インポートを避けるため
    ここでは`get_stripe_customer_id`のみを持つ最小限の別Protocolとして定義する
    (checkout_session.UserProfileStoreProtocolと同一の形、structural typingのため同一
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

    `stripe_customer_id`が空文字列・Noneの場合は`ValueError`。Checkout Session版と異なり
    Portal Sessionは既存customerが前提のため、`customer`キーは常に含まれる
    (`create_portal_session()`側で4節のガードを既に通過している前提で、通常このガードには
    到達しない)。
    """
    if not stripe_customer_id:
        raise ValueError("stripe_customer_id must be a non-empty string")

    return {
        "customer": stripe_customer_id,
        "return_url": return_url,
    }


@dataclass
class CreatePortalSessionResult:
    """customer-portal-session-endpoint-design.md 3節。CreateCheckoutSessionResultと
    同じ形(status_code必須、他はどちらか一方のみ埋まる)。"""

    status_code: int
    portal_session_params: Optional[dict] = None
    error: Optional[str] = None


_BEARER_PREFIX = "Bearer "


def create_portal_session(
    authorization_header: Optional[str],
    *,
    verify_id_token: Callable[[str], Optional[str]],
    user_profile_store: UserProfileStoreProtocol,
    return_url: str = DEFAULT_RETURN_URL,
) -> CreatePortalSessionResult:
    """customer-portal-session-endpoint-design.md 3節の処理順序を実装する。

    `verify_id_token`(LIFF IDトークン文字列 -> user_id、失敗時None)・
    `user_profile_store`(既存stripe_customer_id問い合わせ)はいずれも呼び出し元から注入する
    依存で、実LINE Platform API・実Firestore接続なしでテスト可能にする。
    """
    if authorization_header is None or not authorization_header.startswith(_BEARER_PREFIX):
        return CreatePortalSessionResult(
            status_code=401, error="missing_or_malformed_authorization_header"
        )

    id_token = authorization_header[len(_BEARER_PREFIX):]
    user_id = verify_id_token(id_token)
    if user_id is None:
        return CreatePortalSessionResult(status_code=401, error="invalid_id_token")

    existing_stripe_customer_id = user_profile_store.get_stripe_customer_id(user_id)
    if existing_stripe_customer_id is None:
        return CreatePortalSessionResult(status_code=404, error="no_stripe_customer")

    params = build_portal_session_params(existing_stripe_customer_id, return_url=return_url)
    return CreatePortalSessionResult(status_code=200, portal_session_params=params)


def _verify_id_token_not_implemented(id_token: str) -> Optional[str]:
    """checkout_session._verify_id_token_not_implementedと同じプレースホルダ。

    LINE Platform APIの`/oauth2/v2.1/verify`相当への実HTTPリクエストは、LIFFアプリの
    実登録(オーナー承認待ち)後に本関数を差し替える。恒久的に失敗を返すダミーだと
    誤って動いているように見えてしまうため、呼ばれたら意図的にNotImplementedErrorを送出する。
    """
    raise NotImplementedError(
        "verify_id_token is not implemented yet: pending LIFF app registration "
        "(owner approval required, see pending-approval.md)"
    )


def get_portal_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(checkout_session.get_checkout_runtime_
    dependencies()と対称の構成、customer-portal-session-endpoint-design.md 4節)。

    - user_profile_store: InMemoryUserProfileStore()を1つ生成する。checkout_session.py側と
      同様、本プロセスでは別プロセス・別インスタンスとして初期化されるため、既存
      stripe_customer_idの引き継ぎは呼び出しをまたいで保持されない(実Firestore接続後に
      解消される既知の限界)。
    - verify_id_token: _verify_id_token_not_implemented。LIFFアプリ実登録後に実装を
      差し替える(customer-portal-session-endpoint-design.md「残課題」参照)。
    """
    return {
        "user_profile_store": InMemoryUserProfileStore(),
        "verify_id_token": _verify_id_token_not_implemented,
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、Portal Session版)。

    checkout_session.main()と対称の構成(customer-portal-session-endpoint-design.md 4節)。
    """
    authorization_header = request.headers.get("Authorization")
    try:
        result = create_portal_session(
            authorization_header, **get_portal_runtime_dependencies()
        )
    except NotImplementedError:
        return "verify_id_token_not_implemented", 501

    if result.status_code == 200:
        return result.portal_session_params, 200
    return (result.error or "error"), result.status_code
