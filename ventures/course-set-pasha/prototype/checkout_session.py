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

from application_form_submission_flow import InMemoryUserProfileStore
from cloud_function_webhook import PLAN_MONTHLY_LIMITS

# design 4節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_SUCCESS_URL = "https://example.com/course-set-pasha/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/course-set-pasha/checkout/cancel"

# checkout-session-plan-selection-design.md(フェーズ152): pricing-plan.mdの3プラン名
# (PLAN_MONTHLY_LIMITSのキーと同一集合、cloud_function_webhook.pyを単一の正とし重複定義を
# 避ける)それぞれに対応するStripe Price IDのプレースホルダ。実Price ID確定(Stripe
# ダッシュボードでの商品・価格作成、オーナー承認待ち・pending-approval.md参照)後に
# 差し替える。キー自体はPLAN_MONTHLY_LIMITSと常に同期する(新規プラン追加時はどちらも
# 更新が必要)。
PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER = {
    "ライト": "price_PLACEHOLDER_course_set_pasha_light",
    "スタンダード": "price_PLACEHOLDER_course_set_pasha_standard",
    "セッター複数": "price_PLACEHOLDER_course_set_pasha_multi_setter",
}


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
    plan: Optional[str] = None,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIへ渡すパラメータを組み立てる(design 4節)。

    - `user_id`が空文字列・Noneの場合は`ValueError`。呼び出し元でLIFF IDトークン検証済みの
      認証済みuser_idが必ず先に得られている前提を明示するガード。
    - `existing_stripe_customer_id`が渡された場合のみ`"customer"`キーを追加し、既存の
      Stripe顧客を再利用する(重複顧客レコード防止、design 3節手順3)。
    - `plan`(checkout-session-plan-selection-design.md、フェーズ152で追加)が渡された場合、
      `PLAN_MONTHLY_LIMITS`(pricing-plan.mdの3プラン)にない値は`ValueError`。有効な場合は
      `"line_items"`(選択プランに対応するStripe Priceを1件・数量1)と`"metadata": {"plan":
      plan}`を追加する。`metadata.plan`は`checkout.session.completed`Webhookイベントの
      セッションオブジェクトにそのまま含まれるため、`stripe_webhook.
      handle_checkout_session_completed()`側で追加のAPI呼び出し(line_itemsのexpand等)なしに
      購入プランを特定できる。
    - `plan`を省略した場合(後方互換)は従来通り`line_items`・`metadata`を含めない
      (既存の呼び出し元・テストの挙動を変えない)。
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
    if plan is not None:
        if plan not in PLAN_MONTHLY_LIMITS:
            raise ValueError(f"unknown plan: {plan!r}")
        params["line_items"] = [
            {"price": PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER[plan], "quantity": 1}
        ]
        params["metadata"] = {"plan": plan}

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
    plan: Optional[str] = None,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> CreateCheckoutSessionResult:
    """checkout-session-endpoint-design.md 2節の処理順序を実装する。

    `verify_id_token`(LIFF IDトークン文字列 -> user_id、失敗時None)・
    `user_profile_store`(既存stripe_customer_id問い合わせ)はいずれも呼び出し元から注入する
    依存で、実LINE Platform API・実Firestore接続なしでテスト可能にする。

    `plan`(checkout-session-plan-selection-design.md、フェーズ152で追加)はLIFFフロント
    エンド側のプラン選択UIから渡される想定の文字列。認証成功後・パラメータ組み立て前に
    検証し、`PLAN_MONTHLY_LIMITS`にない値は`status_code=400`・`error="invalid_plan"`を返す
    (認証前に検証しない=未認証ユーザーにプラン名の有効集合を推測させないため、design 2節)。
    省略時(後方互換)は従来通り`build_checkout_session_params()`にも渡さない。
    """
    if authorization_header is None or not authorization_header.startswith(_BEARER_PREFIX):
        return CreateCheckoutSessionResult(
            status_code=401, error="missing_or_malformed_authorization_header"
        )

    id_token = authorization_header[len(_BEARER_PREFIX):]
    user_id = verify_id_token(id_token)
    if user_id is None:
        return CreateCheckoutSessionResult(status_code=401, error="invalid_id_token")

    if plan is not None and plan not in PLAN_MONTHLY_LIMITS:
        return CreateCheckoutSessionResult(status_code=400, error="invalid_plan")

    existing_stripe_customer_id = user_profile_store.get_stripe_customer_id(user_id)
    params = build_checkout_session_params(
        user_id,
        existing_stripe_customer_id,
        plan=plan,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CreateCheckoutSessionResult(status_code=200, checkout_session_params=params)


def _verify_id_token_not_implemented(id_token: str) -> Optional[str]:
    """checkout-session-cloud-function-entry-point-design.md 2節のプレースホルダ。

    LINE Platform APIの`/oauth2/v2.1/verify`相当への実HTTPリクエストは、LIFFアプリの
    実登録(オーナー承認待ち)後に本関数を差し替える。恒久的に失敗を返すダミーだと
    誤って動いているように見えてしまうため、呼ばれたら意図的にNotImplementedErrorを送出する。
    """
    raise NotImplementedError(
        "verify_id_token is not implemented yet: pending LIFF app registration "
        "(owner approval required, see pending-approval.md)"
    )


def get_checkout_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(stripe_webhook.get_stripe_runtime_dependencies()と
    対称の構成、checkout-session-cloud-function-entry-point-design.md 3節)。

    - user_profile_store: InMemoryUserProfileStore()を1つ生成する。実運用ではStripe側
      Cloud Functionと同一Firestoreのuser_profileコレクションを共有する想定だが、本プロセス
      では別プロセス・別インスタンスとして初期化されるため、既存stripe_customer_idの
      引き継ぎは呼び出しをまたいで保持されない(実Firestore接続後に解消される既知の限界)。
    - verify_id_token: _verify_id_token_not_implemented。LIFFアプリ実登録後に実装を
      差し替える(checkout-session-endpoint-design.md「残課題」1点目)。
    """
    return {
        "user_profile_store": InMemoryUserProfileStore(),
        "verify_id_token": _verify_id_token_not_implemented,
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、Checkout Session版)。

    checkout-session-endpoint-design.md「残課題」2点目で未着手のまま残っていた、実リクエスト
    オブジェクトからのAuthorizationヘッダ取り出し配線をここで行い、create_checkout_session()に
    委譲する(stripe_webhook.main()と対称の構成、checkout-session-cloud-function-entry-point-
    design.md 4節)。
    """
    authorization_header = request.headers.get("Authorization")
    # design(checkout-session-plan-selection-design.md フェーズ152): クエリパラメータ`plan`
    # からプラン選択を受け取る。`request`に`args`が無い(既存テストのスタブ等)場合は
    # 空dict扱いとし、`plan=None`(=省略時の従来挙動)にフォールバックする。
    plan = getattr(request, "args", {}).get("plan")
    try:
        result = create_checkout_session(
            authorization_header, plan=plan, **get_checkout_runtime_dependencies()
        )
    except NotImplementedError:
        return "verify_id_token_not_implemented", 501

    if result.status_code == 200:
        return result.checkout_session_params, 200
    return (result.error or "error"), result.status_code
