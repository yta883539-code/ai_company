#!/usr/bin/env python3
"""checkout-initiation-flow-design.md(フェーズ98)で設計した、Stripe Checkout Session
作成APIへ渡すパラメータを組み立てるロジック。

位置づけ:
- 実LIFF(LINE Front-end Framework)のIDトークン検証、実Stripe Checkout Session作成API
  呼び出しはいずれも実アカウント接続後の話であり、外部サービスへの設定・実HTTPリクエスト
  送信を伴うためオーナー承認待ち(pending-approval.md参照)。
- 本モジュールはそれとは独立に、認証済み`user_id`(呼び出し元でLIFF IDトークン検証済みの
  前提)と既存`stripe_customer_id`の有無から、Checkout Session作成APIへ渡すパラメータの
  dictを組み立てる部分のみを実HTTPリクエストなしで検証可能にしたもの。

設計の参照元: checkout-initiation-flow-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

# design 4節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_SUCCESS_URL = "https://example.com/course-set-pasha/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/course-set-pasha/checkout/cancel"


class UserProfileStoreProtocol(Protocol):
    """create_checkout_session()が必要とする部分のみを表す最小限のProtocol。

    実体はapplication_form_submission_flow.UserProfileStoreProtocol
    (get_stripe_customer_id実装済み)を満たすストアを想定するが、循環インポートを避けるため
    ここでは`get_stripe_customer_id`のみを持つ最小限の別Protocolとして定義する
    (structural typingのため、同ストアインスタンスをそのまま渡せる)。
    """

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        ...


def build_checkout_session_params(
    user_id: str,
    existing_stripe_customer_id: Optional[str] = None,
    *,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIへ渡すパラメータを組み立てる(design 4節)。

    - `user_id`が空文字列・Noneの場合は`ValueError`。呼び出し元でLIFF IDトークン検証済みの
      認証済みuser_idが必ず先に得られている前提を明示するガード。
    - `existing_stripe_customer_id`が渡された場合のみ`"customer"`キーを追加し、既存の
      Stripe顧客を再利用する(重複顧客レコード防止、design 3節手順3)。
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")

    params: dict = {
        "mode": "subscription",
        "client_reference_id": user_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if existing_stripe_customer_id:
        params["customer"] = existing_stripe_customer_id

    return params


@dataclass
class CreateCheckoutSessionResult:
    """checkout-session-endpoint-design.md(フェーズ112)2節。stripe_webhook.pyの
    StripeWebhookReceiverResultと同じ形(status_code必須、他はどちらか一方のみ埋まる)。"""

    status_code: int
    checkout_session_params: Optional[dict] = None
    error: Optional[str] = None


_BEARER_PREFIX = "Bearer "


def create_checkout_session(
    authorization_header: Optional[str],
    *,
    verify_id_token: Callable[[str], Optional[str]],
    user_profile_store: UserProfileStoreProtocol,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> CreateCheckoutSessionResult:
    """checkout-session-endpoint-design.md 2節の処理順序を実装する。

    `verify_id_token`(LIFF IDトークン文字列 -> user_id、失敗時None)・
    `user_profile_store`(既存stripe_customer_id問い合わせ)はいずれも呼び出し元から注入する
    依存で、実LINE Platform API・実Firestore接続なしでテスト可能にする。
    """
    if authorization_header is None or not authorization_header.startswith(_BEARER_PREFIX):
        return CreateCheckoutSessionResult(
            status_code=401, error="missing_or_malformed_authorization_header"
        )

    id_token = authorization_header[len(_BEARER_PREFIX):]
    user_id = verify_id_token(id_token)
    if user_id is None:
        return CreateCheckoutSessionResult(status_code=401, error="invalid_id_token")

    existing_stripe_customer_id = user_profile_store.get_stripe_customer_id(user_id)
    params = build_checkout_session_params(
        user_id,
        existing_stripe_customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CreateCheckoutSessionResult(status_code=200, checkout_session_params=params)
