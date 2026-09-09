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


DEFAULT_CHECKOUT_PLAN = "standard"

# trial-end-notification-design.md 3節・6節(フェーズ61)対応: トライアル終了通知メッセージの
# 「▼ 有料プランへ進む」postbackボタンに埋め込むdata文字列。aircon-pashaの
# trial-end-condition-a-cta-design.md(フェーズ137)と同じ形式(`"action=start_checkout"`、
# プラン別に絞り込みたい場合は`"&plan=<plan_id>"`を付加)を踏襲する。
START_CHECKOUT_POSTBACK_DATA = "action=start_checkout"


def build_start_checkout_postback_data(plan_id: str) -> str:
    """プラン別のpostbackボタンに埋め込むdata文字列を組み立てる(例:
    `"action=start_checkout&plan=standard"`)。未知のplan_idはbuild_checkout_session_params()
    と同じ安全側の方針で`ValueError`。"""
    if plan_id not in VALID_PLAN_IDS:
        raise ValueError(f"unknown plan_id: {plan_id!r}")
    return f"{START_CHECKOUT_POSTBACK_DATA}&plan={plan_id}"


def parse_start_checkout_postback_data(data: Optional[str]) -> Optional[str]:
    """postbackイベントの`data`がstart_checkout系アクションかどうかを判定し、選択された
    plan_idを返す。

    - 完全一致`START_CHECKOUT_POSTBACK_DATA`(プラン未指定、trial-end-notification-design.md
      3節の汎用「▼ 有料プランへ進む」ボタン用)の場合は`DEFAULT_CHECKOUT_PLAN`を返す。
    - `build_start_checkout_postback_data()`が組み立てた`"action=start_checkout&plan=<plan_id>"`
      形式で、`<plan_id>`が既知のプランの場合はそのplan_idを返す。
    - それ以外(start_checkout系ではない、または未知のplan_id)は`None`を返す。呼び出し元は
      Noneの場合、未知のpostbackを不正なCheckout Session作成に繋げないため素通りする想定。
    """
    if data == START_CHECKOUT_POSTBACK_DATA:
        return DEFAULT_CHECKOUT_PLAN
    prefix = f"{START_CHECKOUT_POSTBACK_DATA}&plan="
    if data is not None and data.startswith(prefix):
        plan_id = data[len(prefix):]
        if plan_id in VALID_PLAN_IDS:
            return plan_id
    return None


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
