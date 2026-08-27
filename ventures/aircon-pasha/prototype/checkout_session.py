#!/usr/bin/env python3
"""checkout-initiation-flow-design.md(フェーズ131)で設計した、Stripe Checkout Session
作成APIへ渡すパラメータを組み立てるロジック。

位置づけ:
- 本ventureはuser-account-linking-design.md 4節の前提(Checkout Session作成時点で
  user_idは`user_profile`上で判明済み)と、決済導線をLINEのpostbackアクションとして
  提供する設計(checkout-initiation-flow-design.md 1〜2節)により、course-set-pashaが
  必要としたLIFF IDトークン検証を経由しない。postbackイベントの`source.userId`は
  webhook-http-entry-point-design.mdの署名検証を経た`events`配列由来のためLINE
  プラットフォーム自身が認証済みの値であることが前提となる。
- 実Stripe Checkout Session作成API呼び出しは実アカウント接続後の話であり、外部サービスへの
  設定・実HTTPリクエスト送信を伴うためオーナー承認待ち(pending-approval.md参照)。
- 本モジュールはそれとは独立に、認証済み`user_id`(呼び出し元でpostbackイベントから
  取得済みの前提)と既存`stripe_customer_id`の有無から、Checkout Session作成APIへ渡す
  パラメータのdictを組み立てる部分のみを実HTTPリクエストなしで検証可能にしたもの。

設計の参照元: checkout-initiation-flow-design.md
"""

from __future__ import annotations

from typing import Optional

# design 4節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_SUCCESS_URL = "https://example.com/aircon-pasha/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/aircon-pasha/checkout/cancel"

# design 2節: トライアル終了通知メッセージ内のpostbackボタンに埋め込む固定データ。
START_CHECKOUT_POSTBACK_DATA = "action=start_checkout"


def build_checkout_session_params(
    user_id: str,
    existing_stripe_customer_id: Optional[str] = None,
    *,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIへ渡すパラメータを組み立てる(design 4節)。

    - `user_id`が空文字列・Noneの場合は`ValueError`。呼び出し元でpostbackイベントの
      `source.userId`取得が必ず先に成功している認証済みuser_idである前提を明示するガード。
    - `existing_stripe_customer_id`が渡された場合のみ`"customer"`キーを追加し、既存の
      Stripe顧客を再利用する(重複顧客レコード防止、course-set-pashaと同じ理由)。
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
