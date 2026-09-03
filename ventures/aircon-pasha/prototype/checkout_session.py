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

# checkout-session-plan-selection-design.md(フェーズ179): pricing-plan.md「プラン案」表と
# 同じ3プラン名(cloud_function_webhook.PLAN_MONTHLY_LIMITS・
# subscription_plan_sync.LOOKUP_KEY_TO_PLAN_IDと同じキー集合)を、Stripe Price ID
# (実アカウント接続後に確定、それまでのプレースホルダ)へ対応付ける。
# `cloud_function_webhook.py`が既に本モジュールをインポートしているため、循環インポートを
# 避けるためここから逆にインポートすることはできない(3モジュールでプラン名リテラルを
# 個別に保持する、本venture既存の重複パターンを踏襲する)。
PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER = {
    "スモール": "price_PLACEHOLDER_AIRCON_PASHA_SMALL",
    "スタンダード": "price_PLACEHOLDER_AIRCON_PASHA_STANDARD",
    "繁忙期対応": "price_PLACEHOLDER_AIRCON_PASHA_BUSY",
}

# design 1節: 本ventureの決済導線は単一ボタン(start_checkout)のみでプラン選択UIを
# 提供しないため、全ユーザーをこのプランで開始する。market-research.mdの標準的な利用量
# (月60〜100件)に最も近い「想定顧客像」を持つプランを既定値とした。開始後のプラン変更は
# 既存のStripe Customer Portal導線(update_payment_methodポストバック→portal_session.py)
# で行う想定(portal-session-provider-design.md)。
DEFAULT_CHECKOUT_PLAN = "スタンダード"


def build_checkout_session_params(
    user_id: str,
    existing_stripe_customer_id: Optional[str] = None,
    *,
    plan: str = DEFAULT_CHECKOUT_PLAN,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIへ渡すパラメータを組み立てる(design 4節)。

    - `user_id`が空文字列・Noneの場合は`ValueError`。呼び出し元でpostbackイベントの
      `source.userId`取得が必ず先に成功している認証済みuser_idである前提を明示するガード。
    - `existing_stripe_customer_id`が渡された場合のみ`"customer"`キーを追加し、既存の
      Stripe顧客を再利用する(重複顧客レコード防止、course-set-pashaと同じ理由)。
    - `plan`は`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の既知のキーでなければ`ValueError`
      (checkout-session-plan-selection-design.md 1節)。`mode="subscription"`のCheckout
      Sessionは`line_items`なしでは作成できないため、常に1件の`line_items`を含める。
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    if plan not in PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER:
        raise ValueError(f"unknown plan: {plan!r}")

    params: dict = {
        "mode": "subscription",
        "client_reference_id": user_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [
            {"price": PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER[plan], "quantity": 1}
        ],
    }
    if existing_stripe_customer_id:
        params["customer"] = existing_stripe_customer_id

    return params
