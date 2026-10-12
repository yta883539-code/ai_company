#!/usr/bin/env python3
"""stripe-checkout-plan-id-design.md(フェーズ124)「7. 次の課題」で残課題として記録された
Checkout Session作成エントリポイントのうち、Stripe Checkout Session作成APIに渡すパラメータを
組み立てる部分だけを純粋関数として切り出す(kura-pasha/prototype/checkout_session.pyの
build_checkout_session_params()と同型、payment-identity-verification-design.md 3節の
client_reference_id = internal_id方式を踏襲)。

checkout-session-cloud-function-entry-point-design.md(フェーズ142)で、access_token
(settings.html等と同じ`accessToken`機構)からinternal_idを解決して
build_checkout_session_params()へ橋渡しするcreate_checkout_session()・Cloud Functions
エントリポイントmain(request)を追加した。

実Stripe API呼び出し・実Webフォームのプラン選択UI自体(main(request)への実際の配線)は
本venture未着手のまま次回以降の課題として残る。
"""

from dataclasses import dataclass
from typing import Optional

from access_token_store import AccessTokenStoreProtocol, InMemoryAccessTokenStore
from plan_id_resolution import KNOWN_PLAN_IDS
from trial_management import FleetOperatorStoreProtocol, InMemoryFleetOperatorStore

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


@dataclass(frozen=True)
class CheckoutSessionResult:
    status_code: int
    checkout_session_params: Optional[dict] = None
    error: Optional[str] = None


def create_checkout_session(
    access_token: Optional[str],
    plan_id: Optional[str],
    *,
    access_token_store: AccessTokenStoreProtocol,
    operator_store: FleetOperatorStoreProtocol,
) -> CheckoutSessionResult:
    """checkout-session-cloud-function-entry-point-design.md 2節・3節の方式どおり、
    LIFF IDトークンではなく既存のaccess_token機構(settings.html・access-token-reissue-
    design.md)でinternal_idを解決し、build_checkout_session_params()へ橋渡しする。

    `access_token`が空・未知の場合は、`internal_id`が実在するかどうか以上の情報を
    返さないためstatus_code=404とする(同design 2節)。`plan_id`が既知の値
    (plan_id_resolution.KNOWN_PLAN_IDS)でない場合はstatus_code=400とする。
    """
    if not access_token:
        return CheckoutSessionResult(status_code=404, error="access_token_not_found")
    internal_id = access_token_store.get_internal_id_by_access_token(access_token)
    if internal_id is None:
        return CheckoutSessionResult(status_code=404, error="access_token_not_found")
    if plan_id not in KNOWN_PLAN_IDS:
        return CheckoutSessionResult(status_code=400, error="unknown_plan_id")

    params = build_checkout_session_params(
        internal_id,
        plan_id,
        email=operator_store.get_email(internal_id),
        existing_stripe_customer_id=operator_store.get_stripe_customer_id(internal_id),
    )
    return CheckoutSessionResult(status_code=200, checkout_session_params=params)


def get_checkout_runtime_dependencies() -> dict:
    """stripe_webhook.get_stripe_runtime_dependencies()と対称の構成。実Firestore接続後は
    同一プロセス内で共有される実ストアに差し替える(他venture既知の限界と同様、本プロセス内
    では呼び出しをまたいで状態が保持されない)。"""

    return {
        "access_token_store": InMemoryAccessTokenStore(),
        "operator_store": InMemoryFleetOperatorStore(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、checkout-session-
    cloud-function-entry-point-design.md 4節)。`request.args.get("access_token")`で
    アクセスURL(`https://<ドメイン>/f/{accessToken}`)経由のトークンを、
    `request.args.get("plan")`でプラン選択ページが送るplan_idを、それぞれクエリ
    パラメータから取り出してcreate_checkout_session()に委譲する。
    """
    access_token = request.args.get("access_token")
    plan_id = request.args.get("plan")
    result = create_checkout_session(
        access_token,
        plan_id,
        **get_checkout_runtime_dependencies(),
    )
    if result.status_code == 200:
        return result.checkout_session_params, 200
    return (result.error or "error"), result.status_code
