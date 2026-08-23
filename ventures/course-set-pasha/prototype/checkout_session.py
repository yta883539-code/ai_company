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

from typing import Optional

# design 4節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_SUCCESS_URL = "https://example.com/course-set-pasha/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/course-set-pasha/checkout/cancel"


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
