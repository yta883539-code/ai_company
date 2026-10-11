#!/usr/bin/env python3
"""stripe-checkout-plan-id-design.md(フェーズ124)「7. 次の課題」で残課題として記録された
Checkout Session作成エントリポイントのうち、Stripe Checkout Session作成APIに渡すパラメータを
組み立てる部分だけを純粋関数として切り出す(kura-pasha/prototype/checkout_session.pyの
build_checkout_session_params()と同型、payment-identity-verification-design.md 3節の
client_reference_id = internal_id方式を踏襲)。

実Stripe API呼び出し・実Webフォームのプラン選択UI自体は本venture未着手のまま次回以降の
課題として残る。
"""

from typing import Optional

from plan_id_resolution import KNOWN_PLAN_IDS

# 実Stripeダッシュボードでの商品登録後に差し替える仮のプレースホルダ
# (payment-identity-verification-design.md「3. Checkout Session発行・Webhook紐付け」)。
DEFAULT_SUCCESS_URL = "https://example.com/forklift-pasha/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/forklift-pasha/checkout/cancel"

# plan_id→Stripe Price IDの対応表。実Stripeダッシュボードでの商品登録後に差し替える仮の
# プレースホルダ(kura-pasha/prototype/checkout_session.pyと同型)。
PLAN_ID_TO_STRIPE_PRICE_ID = {
    "light": "price_forklift_pasha_light_PLACEHOLDER",
    "standard": "price_forklift_pasha_standard_PLACEHOLDER",
    "fleet": "price_forklift_pasha_fleet_PLACEHOLDER",
}


def build_checkout_session_params(
    internal_id: str,
    plan_id: str,
    *,
    email: Optional[str] = None,
    existing_stripe_customer_id: Optional[str] = None,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIに渡すパラメータdictを組み立てる。

    payment-identity-verification-design.md 3節の方式どおり、`client_reference_id`には
    `internal_id`(Firestore自動生成・不変ID、ユーザー配布用の再発行可能な`accessToken`とは
    別の値)を設定する。`internal_id`の空文字列・Noneはガードとしてエラーとする
    (本関数呼び出し前にfleet_operatorの特定が成功している前提)。

    `metadata.plan`には既知のplan_id("light"/"standard"/"fleet")をそのまま埋め込む
    (stripe-checkout-plan-id-design.md 2節: 他ventureと異なり日本語プラン名の変換表を
    持たずに済む簡略化方針)。`checkout.session.completed`受信時はこの値を
    `plan_id_resolution.write_plan_id_from_checkout_session_metadata()`へそのまま渡せる。

    `existing_stripe_customer_id`指定時(再契約等、既存のStripe顧客が判明している場合)は
    `customer`パラメータを設定し、`email`は無視する(Stripe側は`customer`指定時、顧客の
    既存メールアドレスをCheckout画面に表示するため`customer_email`との併用は不要)。
    未指定時かつ`email`指定時は`customer_email`を設定する(識別子としては使わず、
    Checkout画面上での本人確認表示用。payment-identity-verification-design.md 3節)。
    """
    if not internal_id:
        raise ValueError("internal_id must be a non-empty string")
    if plan_id not in KNOWN_PLAN_IDS:
        raise ValueError(f"unknown plan_id: {plan_id!r}")

    params: dict = {
        "mode": "subscription",
        "client_reference_id": internal_id,
        "line_items": [
            {"price": PLAN_ID_TO_STRIPE_PRICE_ID[plan_id], "quantity": 1},
        ],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "metadata": {"plan": plan_id},
    }
    if existing_stripe_customer_id:
        params["customer"] = existing_stripe_customer_id
    elif email:
        params["customer_email"] = email
    return params
