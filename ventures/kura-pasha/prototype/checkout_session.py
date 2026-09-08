"""checkout-initiation-flow-design.md(フェーズ50)3〜4節のプロトタイプ実装。

実LINE Messaging API・実Stripe API呼び出しは対象外とし、Stripe Checkout Session作成APIに
渡すパラメータを組み立てる部分だけを純粋関数として切り出す。
"""

from typing import Optional

# pricing-plan.mdの3プラン。usage_counter_workshop.PLAN_LIMITSのキーと同一だが、
# 本モジュールをusage_counter_workshop.pyに依存させないため独立して定義する。
VALID_PLAN_IDS = ("light", "standard", "multi_craftsman")

# 実Stripeダッシュボードでの商品登録後に差し替える仮のプレースホルダ(checkout-initiation-
# flow-design.md 4節)。
DEFAULT_SUCCESS_URL = "https://example.com/kura-pasha/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/kura-pasha/checkout/cancel"

# plan_id→Stripe Price IDの対応表。実Stripeダッシュボードでの商品登録後に差し替える仮の
# プレースホルダ(checkout-initiation-flow-design.md 4節)。
PLAN_ID_TO_STRIPE_PRICE_ID = {
    "light": "price_kura_pasha_light_PLACEHOLDER",
    "standard": "price_kura_pasha_standard_PLACEHOLDER",
    "multi_craftsman": "price_kura_pasha_multi_craftsman_PLACEHOLDER",
}


def build_checkout_session_params(
    workshop_id: str,
    plan_id: str,
    existing_stripe_customer_id: Optional[str] = None,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIに渡すパラメータdictを組み立てる。

    checkout-initiation-flow-design.md 3節手順2〜3(workshop特定・契約者本人確認)が
    必ず先に成功している前提のガードとして、workshop_idの空文字列・Noneはエラーとする。
    """
    if not workshop_id:
        raise ValueError("workshop_id must be a non-empty string")
    if plan_id not in VALID_PLAN_IDS:
        raise ValueError(f"unknown plan_id: {plan_id!r}")

    params: dict = {
        "mode": "subscription",
        "client_reference_id": workshop_id,
        "line_items": [
            {"price": PLAN_ID_TO_STRIPE_PRICE_ID[plan_id], "quantity": 1},
        ],
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if existing_stripe_customer_id:
        params["customer"] = existing_stripe_customer_id
    return params
