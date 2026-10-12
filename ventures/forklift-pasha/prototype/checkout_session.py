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

plan-selection-submission-wiring-design.md(フェーズ143)「4. 残課題」の1点目を受け、
main(request)のレスポンス方式をJSON返却からStripe Checkout URLへのHTTPリダイレクト
(303 See Other)返却に変更する部分を、実Stripe接続(オーナー承認待ち)より先行して実装した
(フェーズ144)。`CheckoutSessionCreatorProtocol`を新設し、実Stripe接続後は
`stripe.checkout.sessions.create(**params)`を呼ぶ実装に差し替えられる形にしつつ、
現時点では`build_checkout_session_params()`の出力からダミーのCheckout URLを組み立てる
`MockCheckoutSessionCreator`を既定の依存として使う。
"""

from dataclasses import dataclass
from typing import Optional, Protocol

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


class CheckoutSessionCreatorProtocol(Protocol):
    def create(self, params: dict) -> "CreatedCheckoutSession": ...


@dataclass(frozen=True)
class CreatedCheckoutSession:
    """`stripe.checkout.sessions.create(**params)`の戻り値(Stripeの`Session`オブジェクト)の
    うち、本venture(リダイレクト方式)が必要とする`url`属性のみを持つ最小の値オブジェクト。"""

    url: str


class MockCheckoutSessionCreator:
    """実Stripe接続(オーナー承認待ち)前に`main(request)`のリダイレクト方式を先行実装・
    テストするための仮実装(plan-selection-submission-wiring-design.md「4. 残課題」1点目)。

    実Stripe APIを呼ばず、`client_reference_id`(internal_id)を含むダミーURLを組み立てる
    だけなので、課金・外部送信は一切発生しない。実Stripe接続後は、本クラスと同じ
    `create(params) -> CreatedCheckoutSession`形式で`stripe.checkout.sessions.create(**params)`
    を呼ぶ実装に差し替える(本クラスはその際削除せず、テスト用依存として残す想定)。
    """

    def create(self, params: dict) -> CreatedCheckoutSession:
        internal_id = params["client_reference_id"]
        return CreatedCheckoutSession(
            url=f"https://checkout.stripe.com/mock-session/{internal_id}"
        )


@dataclass(frozen=True)
class CheckoutSessionResult:
    status_code: int
    checkout_session_params: Optional[dict] = None
    redirect_url: Optional[str] = None
    error: Optional[str] = None


def create_checkout_session(
    access_token: Optional[str],
    plan_id: Optional[str],
    *,
    access_token_store: AccessTokenStoreProtocol,
    operator_store: FleetOperatorStoreProtocol,
    checkout_session_creator: CheckoutSessionCreatorProtocol,
) -> CheckoutSessionResult:
    """checkout-session-cloud-function-entry-point-design.md 2節・3節の方式どおり、
    LIFF IDトークンではなく既存のaccess_token機構(settings.html・access-token-reissue-
    design.md)でinternal_idを解決し、build_checkout_session_params()へ橋渡しする。

    `access_token`が空・未知の場合は、`internal_id`が実在するかどうか以上の情報を
    返さないためstatus_code=404とする(同design 2節)。`plan_id`が既知の値
    (plan_id_resolution.KNOWN_PLAN_IDS)でない場合はstatus_code=400とする。

    正常系では`checkout_session_creator.create(params)`が返す`url`を`redirect_url`に
    設定する(plan-selection-submission-wiring-design.md 1.2節: `main(request)`は
    この`redirect_url`への303リダイレクトを返す)。
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
    session = checkout_session_creator.create(params)
    return CheckoutSessionResult(
        status_code=200, checkout_session_params=params, redirect_url=session.url
    )


def get_checkout_runtime_dependencies() -> dict:
    """stripe_webhook.get_stripe_runtime_dependencies()と対称の構成。実Firestore接続後は
    同一プロセス内で共有される実ストアに差し替える(他venture既知の限界と同様、本プロセス内
    では呼び出しをまたいで状態が保持されない)。

    `checkout_session_creator`は実Stripe接続(オーナー承認待ち)までの間、
    `MockCheckoutSessionCreator`を使う。"""

    return {
        "access_token_store": InMemoryAccessTokenStore(),
        "operator_store": InMemoryFleetOperatorStore(),
        "checkout_session_creator": MockCheckoutSessionCreator(),
    }


def main(request, *, runtime_dependencies: Optional[dict] = None):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、checkout-session-
    cloud-function-entry-point-design.md 4節・plan-selection-submission-wiring-design.md
    1.2節)。`request.args.get("access_token")`でアクセスURL
    (`https://<ドメイン>/f/{accessToken}`)経由のトークンを、`request.args.get("plan")`で
    プラン選択ページが送るplan_idを、それぞれクエリパラメータから取り出して
    create_checkout_session()に委譲する。

    正常系(status_code=200)では、Stripe Checkout URL(`redirect_url`)への303リダイレクト
    (`Location`ヘッダ)を返す。`plan-selection.html`側はプレーンな`<a href>`で本エンドポイント
    へ遷移するだけでよく、JSによるレスポンス受信・画面遷移制御は不要(plan-selection-
    submission-wiring-design.md 1節)。

    `runtime_dependencies`省略時は`get_checkout_runtime_dependencies()`の戻り値
    (呼び出しごとに新規の空ストア)を使う。フェーズ145で判明した「簡易ローカルサーバー経由では
    事前にaccess_tokenを登録する手段が無く200/303応答に到達できない」という限界(同
    フェーズのテストコメント参照)に対応するため、本引数を通じて呼び出し元(テスト・簡易
    ローカルサーバー)が事前にaccess_token・operatorを登録済みのストアを注入できるようにした。
    実Cloud Functions環境ではキーワード引数を渡さない限り従来どおりの挙動のまま変わらない。
    """
    access_token = request.args.get("access_token")
    plan_id = request.args.get("plan")
    result = create_checkout_session(
        access_token,
        plan_id,
        **(runtime_dependencies if runtime_dependencies is not None else get_checkout_runtime_dependencies()),
    )
    if result.status_code == 200:
        return "", 303, {"Location": result.redirect_url}
    return (result.error or "error"), result.status_code
