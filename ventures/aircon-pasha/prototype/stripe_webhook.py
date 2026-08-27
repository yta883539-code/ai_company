"""Stripe Webhookの署名検証(stripe-webhook-signature-verification-design.md フェーズ125)・
HTTPエントリポイント(stripe-webhook-http-entry-point-design.md フェーズ127)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジック・`dispatch_stripe_event()`への配線のみを切り出したモジュール。
`cloud_function_webhook.py`(LINE側)・`deletion_candidate.py`とは独立した別ファイルとし、
既存コードには一切影響を与えない。

course-set-pasha/prototype/stripe_webhook.py(フェーズ93・95)の`verify_stripe_signature()`・
`receive_stripe_webhook()`と同一のアルゴリズム(design 2節のとおり、venture固有の差異は無い)。

`checkout.session.completed`の受信配線(フェーズ127「残課題」)は
checkout-session-completed-handling-design.mdで設計し、本フェーズで追加した。
user-account-linking-design.md 4節のとおり、本ventureは`client_reference_id`に
既にuser_profile上で判明済みの`user_id`をそのまま設定できる前提のため、
course-set-pashaのような別動線の連携コード方式は不要で、course-set-pashaの
`handle_checkout_session_completed()`とほぼ同じ処理をそのまま踏襲できる。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional

from stripe_dispatch import (
    ProfileDeletionCandidateStoreProtocol,
    StripeDispatchResult,
    dispatch_stripe_event,
)
from user_id_linking import UserProfileStoreProtocol


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """`Stripe-Signature`ヘッダを検証する(design 2節のアルゴリズムどおり)。

    - `sig_header`が無い/空文字列、または`t`・`v1`を含まない不正な形式なら`False`。
    - `v1`が複数含まれる場合(シークレットローテーション中)、いずれか1つでも一致すれば
      検証成功とする。`v0`(旧方式)は一切参照しない。
    - 署名が一致してもタイムスタンプが`tolerance_seconds`(デフォルト300秒)の許容範囲外
      なら`False`とする(リプレイ攻撃対策)。
    """
    if not sig_header:
        return False

    timestamp: Optional[str] = None
    v1_signatures: List[str] = []
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t":
            timestamp = value
        elif key == "v1":
            v1_signatures.append(value)

    if timestamp is None or not v1_signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()

    signature_matches = any(
        hmac.compare_digest(expected, candidate) for candidate in v1_signatures
    )
    if not signature_matches:
        return False

    resolved_now = now if now is not None else time.time()
    if abs(resolved_now - timestamp_int) > tolerance_seconds:
        return False

    return True


@dataclass
class CheckoutSessionLinkResult:
    """handle_checkout_session_completed()の結果
    (checkout-session-completed-handling-design.md 1節)。"""

    linked: bool
    user_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    error: Optional[str] = None


def handle_checkout_session_completed(
    event: dict,
    store: UserProfileStoreProtocol,
) -> CheckoutSessionLinkResult:
    """`checkout.session.completed`イベントから`client_reference_id`(=user_id、
    Checkout Session作成時にuser-account-linking-design.md 4節のとおり既知の値を
    そのまま設定してある)と`customer`(=stripe_customer_id)を取り出し、`store`に
    紐付けを書き込む(checkout-session-completed-handling-design.md 1節)。

    course-set-pashaと異なり、本ventureは決済前に`user_profile`が既に存在している
    前提(design 4節)のため、`client_reference_id`・`customer`の形式が正しくても
    対応する`user_profile`が見つからない場合は異常系として区別し、`store`への
    書き込みは行わない(想定外の順序でCheckout Sessionが作成された場合に、
    存在しないuser_idへ書き込んでデータを汚さないための安全策)。
    """
    data_object = event.get("data", {}).get("object", {})
    user_id = data_object.get("client_reference_id")
    stripe_customer_id = data_object.get("customer")

    if (
        not isinstance(user_id, str)
        or not user_id
        or not isinstance(stripe_customer_id, str)
        or not stripe_customer_id
    ):
        return CheckoutSessionLinkResult(linked=False, error="missing_fields")

    if not store.exists(user_id):
        return CheckoutSessionLinkResult(
            linked=False, user_id=user_id, error="user_profile_not_found"
        )

    store.set_stripe_customer_id(user_id, stripe_customer_id)

    return CheckoutSessionLinkResult(
        linked=True, user_id=user_id, stripe_customer_id=stripe_customer_id
    )


def make_resolve_user_id(
    user_profile_store: UserProfileStoreProtocol,
) -> Callable[[str], Optional[str]]:
    """`dispatch_stripe_event()`の`resolve_user_id`引数の型に合わせた薄いファクトリ
    (checkout-session-completed-handling-design.md 2節、course-set-pashaの
    `make_resolve_user_id()`と同じ位置づけ)。"""
    return user_profile_store.get_user_id_by_stripe_customer_id


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果(stripe-webhook-http-entry-point-design.md 1節、
    checkout-session-completed-handling-design.md 1節で`checkout_link_result`を追加)。"""

    status_code: int
    dispatch_result: Optional[StripeDispatchResult] = None
    checkout_link_result: Optional[CheckoutSessionLinkResult] = None
    error: Optional[str] = None


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    user_profile_store: Optional[UserProfileStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版)。生のリクエストボディ(bytes)を
    受け取り、署名検証(verify_stripe_signature)・JSONパース・イベント種別に応じた
    ディスパッチまでを行う(stripe-webhook-http-entry-point-design.mdで設計した、
    verify_stripe_signature()とdispatch_stripe_event()を結ぶエントリポイントに、
    checkout-session-completed-handling-design.mdで`checkout.session.completed`の
    振り分けを追加)。

    - 署名検証に失敗した場合は401相当を返し、JSONパース以降の配線を一切行わない
      (不正なリクエストへの余計な処理を避ける、LINE側receive_webhook()と同じ方針)。
    - 署名検証後にbodyをJSONとしてパースする。パース失敗、またはパース結果がdictでない
      場合は400相当を返す(Stripeからの実際のリクエストでは通常発生しないはずの異常系だが、
      エントリポイントとして不正な入力にも例外を外に漏らさない設計とする)。
    - イベント種別が`checkout.session.completed`の場合は`dispatch_stripe_event()`
      (`customer.subscription.*`専用)へは渡さず`handle_checkout_session_completed()`へ
      振り分ける(`user_profile_store`が渡されていない場合は何もせず200を返す、
      course-set-pashaのreceive_stripe_webhook()と同じ方針)。
    - それ以外のイベント種別はこれまで通りdispatch_stripe_event()にそのまま委譲し200を
      返す。resolve_user_idが解決できなかった場合・対象外のイベント種別であっても、
      Stripe側の再送ループを避けるためリクエスト自体は200(受理)として扱う。
    """
    resolved_now = now if now is not None else datetime.now(timezone.utc)
    if not verify_stripe_signature(
        body, signature_header, webhook_secret, now=resolved_now.timestamp()
    ):
        return StripeWebhookReceiverResult(status_code=401, error="invalid_signature")

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(parsed, dict):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_event")

    if parsed.get("type") == "checkout.session.completed":
        checkout_link_result = (
            handle_checkout_session_completed(parsed, user_profile_store)
            if user_profile_store is not None
            else CheckoutSessionLinkResult(linked=False, error="store_not_configured")
        )
        return StripeWebhookReceiverResult(
            status_code=200, checkout_link_result=checkout_link_result
        )

    dispatch_result = dispatch_stripe_event(
        parsed, store=store, resolve_user_id=resolve_user_id, now=resolved_now
    )
    return StripeWebhookReceiverResult(status_code=200, dispatch_result=dispatch_result)


def _demo() -> None:
    secret = "whsec_demo_secret"
    payload = b'{"id":"evt_demo","type":"customer.subscription.deleted"}'
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={sig}"
    print("valid signature ->", verify_stripe_signature(payload, header, secret))
    print("missing header ->", verify_stripe_signature(payload, None, secret))


if __name__ == "__main__":
    _demo()
