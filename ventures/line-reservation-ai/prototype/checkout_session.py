#!/usr/bin/env python3
"""checkout-initiation-flow-design.md(フェーズ続き139)で設計した、Stripe Checkout Session
作成APIへ渡すパラメータ、およびLINEへ戻る導線のリンクを組み立てるロジック。

位置づけ:
- 実LIFF(LINE Front-end Framework)のIDトークン検証、実Stripe Checkout Session作成API
  呼び出し、LINE公式アカウント開設(Basic ID確定)はいずれも実アカウント接続後の話であり、
  外部サービスへの設定・実HTTPリクエスト送信を伴うためオーナー承認待ち(pending-approval.md
  参照)。
- 本モジュールはそれとは独立に、認証済みuser_id(呼び出し元でLIFF IDトークン検証済みの
  前提)と既存stripe_customer_idの有無からCheckout Session作成APIへ渡すパラメータを組み立てる
  部分、および公式アカウントのBasic IDからLINEへ戻るユニバーサルリンクを組み立てる部分のみを、
  実HTTPリクエストなしで検証可能にしたもの。

設計の参照元: checkout-initiation-flow-design.md
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

# design 3節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_SUCCESS_URL = "https://example.com/line-reservation-ai/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/line-reservation-ai/checkout/cancel"

_LINE_UNIVERSAL_LINK_BASE = "https://line.me/R/ti/p/"


def build_checkout_session_params(
    user_id: str,
    existing_stripe_customer_id: Optional[str] = None,
    *,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIへ渡すパラメータを組み立てる(design 3節・5節)。

    - `user_id`は店舗オーナーのLINE user_id(design 0節)。空文字列・Noneの場合は
      `ValueError`。呼び出し元でLIFF IDトークン検証済みの認証済みuser_idが必ず先に
      得られている前提を明示するガード。
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


def build_line_return_link(basic_id: str) -> str:
    """LINE公式アカウントのトーク画面へ戻るユニバーサルリンクを組み立てる(design 4節)。

    `https://line.me/R/ti/p/{basic_id}`形式。LINEアプリが端末にインストールされていれば
    アプリを起動しトーク画面へ、未インストールならブラウザでLINEのダウンロード誘導ページへ
    遷移する(design 4節で比較した3案のうち、ユニバーサルリンク案を採用)。

    `basic_id`が空文字列・Noneの場合は`ValueError`(公式アカウント開設〈オーナー承認待ち〉
    前に誤ったリンクを組み立てて掲載してしまう事故を防ぐガード)。
    """
    if not basic_id:
        raise ValueError("basic_id must be a non-empty string")

    return _LINE_UNIVERSAL_LINK_BASE + quote(basic_id)
