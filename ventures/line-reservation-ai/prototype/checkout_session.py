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
- `verify_checkout_authorization()`/`render_checkout_authorization_error_page()`
  (2026-09-02追記): checkout-initiation-flow-design.md 9節・10節、store-id-resolution-and-
  owner-identity-design.md「残課題」に残っていた、認可チェック(`store_id`から解決した
  `owner_user_id`とLIFF IDトークン検証済みの個人`user_id`の一致確認)不一致時のオーナー向け
  エラー文言・案内先を設計・実装した。
- `create_checkout_session()`/`main()`(2026-09-02追記・フェーズ続き174): design 9節手順1〜4・
  10節の認可チェック・11節のLIFF起動リンクをすべて結ぶCheckout Session作成エンドポイント
  本体(design 10節・11節「残課題」に残っていた配線)を実装した。course-set-pasha/aircon-pasha
  のstripe_webhook.main()/checkout_session.main()と同じ「本体は依存注入でテスト可能、
  `main(request)`だけが実`functions_framework`リクエストオブジェクトを扱う薄い配線」という
  構成を踏襲する。
- プラン選択・`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`(2026-09-03追記・フェーズ続き181):
  checkout-session-plan-selection-design.mdで設計した、Checkout Session作成時に購入プランを
  `line_items`・`metadata.plan`として組み立てる処理(course-set-pashaがフェーズ152で実装した
  同名の仕組みの横展開)。

設計の参照元: checkout-initiation-flow-design.md、checkout-session-plan-selection-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote

from store_profile_store import (
    PLAN_MONTHLY_BOOKING_LIMITS,
    InMemoryStoreProfileStore,
    StoreProfileStoreProtocol,
)

# design 3節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_SUCCESS_URL = "https://example.com/line-reservation-ai/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/line-reservation-ai/checkout/cancel"

# design 11節: 実LIFFアプリ登録(オーナー承認待ち)までの仮のプレースホルダ。
DEFAULT_LIFF_ID = "LIFF_ID_PLACEHOLDER"

# design 4節: LINE公式アカウント開設(オーナー承認待ち、Basic ID確定)までの仮のプレースホルダ。
DEFAULT_LINE_BASIC_ID = "LINE_BASIC_ID_PLACEHOLDER"

# checkout-session-plan-selection-design.md(フェーズ続き181): pricing-plan.mdの3プラン名
# (PLAN_MONTHLY_BOOKING_LIMITSのキーと同一集合、store_profile_store.pyを単一の正とし重複
# 定義を避ける)それぞれに対応するStripe Price IDのプレースホルダ。実Price ID確定(Stripe
# ダッシュボードでの商品・価格作成、オーナー承認待ち・pending-approval.md参照)後に
# 差し替える。
PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER = {
    "スタータープラン": "price_PLACEHOLDER_line_reservation_ai_starter",
    "スタンダードプラン": "price_PLACEHOLDER_line_reservation_ai_standard",
    "プロプラン": "price_PLACEHOLDER_line_reservation_ai_pro",
}

_LINE_UNIVERSAL_LINK_BASE = "https://line.me/R/ti/p/"
_LIFF_LINK_BASE = "https://liff.line.me/"


def build_checkout_session_params(
    user_id: str,
    existing_stripe_customer_id: Optional[str] = None,
    *,
    plan: Optional[str] = None,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIへ渡すパラメータを組み立てる(design 3節・5節)。

    - `user_id`は店舗オーナーのLINE user_id(design 0節、本ventureは`store_id`をそのまま
      `user_id`として扱う)。空文字列・Noneの場合は`ValueError`。呼び出し元でLIFF IDトークン
      検証済みの認証済みuser_idが必ず先に得られている前提を明示するガード。
    - `existing_stripe_customer_id`が渡された場合のみ`"customer"`キーを追加し、既存の
      Stripe顧客を再利用する(重複顧客レコード防止、design 3節手順3)。
    - `plan`(checkout-session-plan-selection-design.md、フェーズ続き181で追加)が渡された
      場合、`PLAN_MONTHLY_BOOKING_LIMITS`(pricing-plan.mdの3プラン)にない値は
      `ValueError`。有効な場合は`"line_items"`(選択プランに対応するStripe Priceを1件・
      数量1)と`"metadata": {"plan": plan}`を追加する。`metadata.plan`は
      `checkout.session.completed`Webhookイベントのセッションオブジェクトにそのまま
      含まれるため、`store_profile_store.handle_checkout_session_completed()`側で追加の
      API呼び出し(line_itemsのexpand等)なしに購入プランを特定できる。
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
        if plan not in PLAN_MONTHLY_BOOKING_LIMITS:
            raise ValueError(f"unknown plan: {plan!r}")
        params["line_items"] = [
            {"price": PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER[plan], "quantity": 1}
        ]
        params["metadata"] = {"plan": plan}

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


def build_liff_checkout_link(store_id: str, *, liff_id: str = DEFAULT_LIFF_ID) -> str:
    """決済導線への入口となるLIFF起動リンクを組み立てる(design 11節、
    store-id-resolution-and-owner-identity-design.md「残課題」対応)。

    `https://liff.line.me/{liff_id}?store_id={store_id}`形式。design 9節手順1
    (「クエリパラメータからstore_id受領」)がこの`store_id`クエリパラメータを読み取る
    前提。trial-end-report・オンボーディング完了メッセージいずれも送信時点で対象店舗の
    `store_id`を把握済みのため、送信直前にこの関数で個別リンクを組み立てて埋め込む。

    改ざん検知(署名付与等)は行わない。store-id-resolution-and-owner-identity-design.md
    「残課題」の結論どおり、`store_id`が改ざん・誤入力されても最終的には
    `verify_checkout_authorization()`(design 10節、`owner_user_id`との一致確認)が
    防波堤になるため、現時点では過剰な防御と判断した。

    `store_id`が空文字列・Noneの場合は`ValueError`(送信前に必ず対象店舗のstore_idが
    解決済みであるべきという呼び出し側の実装ミスを早期に検知するガード)。
    """
    if not store_id:
        raise ValueError("store_id must be a non-empty string")

    return f"{_LIFF_LINK_BASE}{liff_id}?store_id={quote(store_id)}"


# design 9節手順3の認可チェック不一致理由(design 10節)。
AUTHORIZATION_DENIED_OWNER_NOT_SET = "owner_user_id_not_set"
AUTHORIZATION_DENIED_USER_ID_MISMATCH = "user_id_mismatch"


@dataclass
class AuthorizationResult:
    """`verify_checkout_authorization()`の結果(design 10節)。

    `authorized`がFalseの場合、`denied_reason`は
    `AUTHORIZATION_DENIED_OWNER_NOT_SET`(store_idに紐づく`owner_user_id`が
    未設定=接続テスト未実施)か`AUTHORIZATION_DENIED_USER_ID_MISMATCH`
    (検証済み個人user_idが`owner_user_id`と一致しない)のいずれかを保持する。
    """

    authorized: bool
    denied_reason: Optional[str] = None


def verify_checkout_authorization(
    store_id: str,
    requester_user_id: str,
    store: StoreProfileStoreProtocol,
) -> AuthorizationResult:
    """checkout-initiation-flow-design.md 9節手順3の認可チェック本体(design 10節で新設)。

    `store_id`・`requester_user_id`(LIFF IDトークン検証済みの個人user_id、呼び出し元で
    検証済みの前提)がいずれも空文字列・Noneの場合は`ValueError`(検証前の値を渡す呼び出し側の
    実装ミスを早期に検知するガードであり、`AuthorizationResult`では表現しない)。

    `store.get_owner_user_id(store_id)`が`None`(店舗が接続テストを未実施でowner_user_id
    未設定)の場合、`requester_user_id`と`owner_user_id`が一致しない場合のいずれも
    `authorized=False`を返し、決済(Checkout Session作成)を続行させない。
    """
    if not store_id:
        raise ValueError("store_id must be a non-empty string")
    if not requester_user_id:
        raise ValueError("requester_user_id must be a non-empty string")

    owner_user_id = store.get_owner_user_id(store_id)
    if owner_user_id is None:
        return AuthorizationResult(
            authorized=False, denied_reason=AUTHORIZATION_DENIED_OWNER_NOT_SET
        )
    if owner_user_id != requester_user_id:
        return AuthorizationResult(
            authorized=False, denied_reason=AUTHORIZATION_DENIED_USER_ID_MISMATCH
        )
    return AuthorizationResult(authorized=True)


# design 10節: success_urlページと同じ「単一トーン(standard相当)で統一する」方針
# (checkout-initiation-flow-design.md 4節)を踏襲し、エラーページもトーン分岐しない。
_AUTHORIZATION_ERROR_MESSAGES = {
    AUTHORIZATION_DENIED_OWNER_NOT_SET: (
        "お支払い手続きを開始できませんでした。\n"
        "このお店ではまだ【予約とれる君】の接続テストが完了していないため、"
        "オーナー様の確認が取れていません。\n"
        "お手数ですが、まずはLINEのトーク画面で接続テストメッセージを送信のうえ、"
        "あらためて手続きをお試しください。"
    ),
    AUTHORIZATION_DENIED_USER_ID_MISMATCH: (
        "お支払い手続きを開始できませんでした。\n"
        "このお店のお支払い手続きは、接続テストを行ったオーナー様のLINEアカウントからのみ"
        "行っていただけます。\n"
        "オーナー様ご本人のLINEアカウントで、あらためて手続きをお試しください。"
    ),
}

_AUTHORIZATION_ERROR_TITLE = "お支払い手続きを続けられません"


def render_checkout_authorization_error_page(
    denied_reason: str, line_return_link: str
) -> str:
    """認可チェック不一致時にsuccess_url/cancel_urlと同じWeb静的ページとして表示する
    エラー文言を組み立てる(design 10節)。

    `denied_reason`は`AUTHORIZATION_DENIED_OWNER_NOT_SET`/
    `AUTHORIZATION_DENIED_USER_ID_MISMATCH`のいずれか(未知の値は`ValueError`、
    `AuthorizationResult.denied_reason`以外の値を誤って渡す実装ミスを早期に検知する)。
    `line_return_link`は`build_line_return_link()`の返り値をそのまま渡す想定で、
    success_urlページ(design 4節)と同じ「LINEに戻る」導線をエラー時にも用意する。
    """
    if denied_reason not in _AUTHORIZATION_ERROR_MESSAGES:
        raise ValueError(f"unknown denied_reason: {denied_reason!r}")
    if not line_return_link:
        raise ValueError("line_return_link must be a non-empty string")

    body = _AUTHORIZATION_ERROR_MESSAGES[denied_reason]
    return (
        f"{_AUTHORIZATION_ERROR_TITLE}\n\n"
        f"{body}\n\n"
        f"▼ LINEに戻る\n"
        f"{line_return_link}"
    )


@dataclass
class CreateCheckoutSessionResult:
    """`create_checkout_session()`の結果(design 9節手順1〜4・10節を結んだ最終結果、
    course-set-pasha/checkout_session.CreateCheckoutSessionResultと同じ形の
    status_code必須・他はいずれか一方のみ埋まる構成に、認可チェック不一致時専用の
    `error_page`〈design 10節のWeb静的ページ文言〉を追加したもの)。"""

    status_code: int
    checkout_session_params: Optional[dict] = None
    error: Optional[str] = None
    error_page: Optional[str] = None


_BEARER_PREFIX = "Bearer "


def create_checkout_session(
    store_id: Optional[str],
    authorization_header: Optional[str],
    *,
    verify_id_token: Callable[[str], Optional[str]],
    store: StoreProfileStoreProtocol,
    line_return_link: str,
    plan: Optional[str] = None,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> CreateCheckoutSessionResult:
    """design 9節手順1〜4・10節の処理順序をすべて結ぶエンドポイント本体(design 9節「訂正」・
    10節「残課題」・11節「残課題」に残っていた配線、フェーズ続き174で新設)。

    `verify_id_token`(LIFF IDトークン文字列 -> 個人user_id、失敗時None)・`store`
    (`owner_user_id`・既存`stripe_customer_id`の問い合わせ)・`line_return_link`
    (`build_line_return_link()`の返り値をそのまま渡す想定)はいずれも呼び出し元から注入する
    依存で、実LINE Platform API・実Firestore接続なしでテスト可能にする。

    処理順序(design 9節手順1〜4):
    1. `store_id`(design 11節の`build_liff_checkout_link()`が埋め込んだクエリパラメータ)が
       空文字列・Noneの場合は400を返す(design 9節手順1、LIFF起動リンク自体の破損・改ざんを
       検知する最初の防波堤。10節の認可チェックより前段のガード)。
    2. `authorization_header`が`Bearer `形式でない場合は401を返す(design 9節手順2の前段、
       course-set-pashaの`create_checkout_session()`と同じガード)。
    3. `verify_id_token(id_token)`で個人`user_id`を取得する(design 9節手順2)。`None`が
       返れば401(`NotImplementedError`はここでは捕捉せず、呼び出し元〈`main()`〉に伝播させる。
       courseset-pasha版と同じ「未実装は501で明示する」方針)。
    4. `plan`(checkout-session-plan-selection-design.md、フェーズ続き181で追加)が
       `PLAN_MONTHLY_BOOKING_LIMITS`にない値の場合は400を返す(design 9節手順3の認可
       チェックより前。未認証ユーザーにプラン名の有効集合を推測させないため、`verify_id_token`
       成功後・認可チェック前のこの時点で検証する)。
    5. `verify_checkout_authorization(store_id, requester_user_id, store)`(design 9節手順3・
       10節)で不一致なら403+`error_page`(`render_checkout_authorization_error_page()`)を
       返し、Checkout Sessionは作成しない。
    6. 認可を通過した場合のみ、`store.get_stripe_customer_id(store_id)`(design 9節手順3で
       `store_id`をキーとする想定に読み替え済み)で既存Stripe顧客を確認し、design 3節・5節の
       `build_checkout_session_params()`で200を返す。
    """
    if not store_id:
        return CreateCheckoutSessionResult(status_code=400, error="missing_store_id")

    if authorization_header is None or not authorization_header.startswith(_BEARER_PREFIX):
        return CreateCheckoutSessionResult(
            status_code=401, error="missing_or_malformed_authorization_header"
        )

    id_token = authorization_header[len(_BEARER_PREFIX):]
    requester_user_id = verify_id_token(id_token)
    if requester_user_id is None:
        return CreateCheckoutSessionResult(status_code=401, error="invalid_id_token")

    if plan is not None and plan not in PLAN_MONTHLY_BOOKING_LIMITS:
        return CreateCheckoutSessionResult(status_code=400, error="invalid_plan")

    authorization_result = verify_checkout_authorization(store_id, requester_user_id, store)
    if not authorization_result.authorized:
        error_page = render_checkout_authorization_error_page(
            authorization_result.denied_reason, line_return_link
        )
        return CreateCheckoutSessionResult(status_code=403, error_page=error_page)

    existing_stripe_customer_id = store.get_stripe_customer_id(store_id)
    params = build_checkout_session_params(
        store_id,
        existing_stripe_customer_id,
        plan=plan,
        success_url=success_url,
        cancel_url=cancel_url,
    )
    return CreateCheckoutSessionResult(status_code=200, checkout_session_params=params)


def _verify_id_token_not_implemented(id_token: str) -> Optional[str]:
    """course-set-pasha/checkout_session._verify_id_token_not_implementedと同じ位置づけの
    プレースホルダ。LINE Platform APIの`/oauth2/v2.1/verify`相当への実HTTPリクエストは、
    LIFFアプリの実登録(オーナー承認待ち)後に本関数を差し替える。恒久的に失敗を返すダミーだと
    誤って動いているように見えてしまうため、呼ばれたら意図的に`NotImplementedError`を送出する。
    """
    raise NotImplementedError(
        "verify_id_token is not implemented yet: pending LIFF app registration "
        "(owner approval required, see pending-approval.md)"
    )


def get_checkout_runtime_dependencies() -> dict:
    """`main()`が使う依存の既定値を組み立てる(course-set-pasha/checkout_session.
    get_checkout_runtime_dependencies()と対称の構成)。

    - `store`: `InMemoryStoreProfileStore()`を1つ生成する。実運用ではCloud Function A/B・
      Stripe Webhook側と同一Firestoreの`stores`コレクションを共有する想定だが、本プロセスでは
      別プロセス・別インスタンスとして初期化されるため、`owner_user_id`・既存
      `stripe_customer_id`の引き継ぎは呼び出しをまたいで保持されない(実Firestore接続後に
      解消される既知の限界、course-set-pasha側と同種)。
    - `verify_id_token`: `_verify_id_token_not_implemented`。LIFFアプリ実登録後に実装本体へ
      差し替える(design 9節「残課題」)。
    - `line_return_link`: `build_line_return_link(DEFAULT_LINE_BASIC_ID)`。LINE公式アカウント
      開設(オーナー承認待ち、Basic ID確定)後に`DEFAULT_LINE_BASIC_ID`プレースホルダから
      差し替える(design 4節)。
    """
    return {
        "store": InMemoryStoreProfileStore(),
        "verify_id_token": _verify_id_token_not_implemented,
        "line_return_link": build_line_return_link(DEFAULT_LINE_BASIC_ID),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、design 9節手順1〜4・
    10節・11節を結ぶCheckout Session作成エンドポイント本体)。

    `request.args.get("store_id")`でLIFF起動リンク(design 11節)のクエリパラメータから
    `store_id`を取り出し、`request.headers.get("Authorization")`と合わせて
    `create_checkout_session()`に委譲する(course-set-pasha/checkout_session.main()と対称の
    構成)。`verify_id_token`が`NotImplementedError`を送出した場合は501を返し、LIFFアプリ
    未登録による未実装であることを呼び出し元(LIFFフロントエンド)が判別しやすくする。
    """
    store_id = request.args.get("store_id")
    authorization_header = request.headers.get("Authorization")
    # checkout-session-plan-selection-design.md(フェーズ続き181): クエリパラメータ`plan`
    # からプラン選択を受け取る(LIFFフロントエンド側のプラン選択UIは未実装、実LIFF登録後の
    # 課題として残る)。
    plan = request.args.get("plan")
    try:
        result = create_checkout_session(
            store_id,
            authorization_header,
            plan=plan,
            **get_checkout_runtime_dependencies(),
        )
    except NotImplementedError:
        return "verify_id_token_not_implemented", 501

    if result.status_code == 200:
        return result.checkout_session_params, 200
    if result.error_page is not None:
        return result.error_page, result.status_code
    return (result.error or "error"), result.status_code
