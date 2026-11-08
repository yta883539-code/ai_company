#!/usr/bin/env python3
"""Stripe Webhook受信エントリポイント(フェーズ97)。

stripe-webhook-entry-point-design.md(フェーズ95)で設計した、署名検証+4イベント種別
(`checkout.session.completed`〈mode=subscriptionのみ〉・`customer.subscription.deleted`・
`customer.subscription.created`・`customer.subscription.updated`)のディスパッチを
実コード化したもの。実Stripeアカウント接続・実Cloud Functionsデプロイ・実Firestore接続は
いずれもオーナー承認待ち(pending-approval.md参照)のため、本モジュールでは行わない。

`verify_stripe_signature()`はaircon-pasha/course-set-pasha/forklift-pasha等の
`prototype/stripe_webhook.py`と同一のアルゴリズム(design 2節のとおりvemture固有の差異は
無い)をそのまま踏襲する。

design 3節のとおり、本ventureは他venture(LINE Webhook前提)と異なりWeb単体・会員登録なし
(payment-method-design.md 2節、monthly-pass-identity-design.md)のため、通知送信(LINE
Push等)は行わない。`fan_pass_store.update_subscription_status()`等のデータ更新のみを
扱う、他venture群より薄いディスパッチとなる。

design 4節の`event_time`引数(配信順序入れ替わりガード)はフェーズ96で`fan_pass_store.py`
側に実装済みのため、本モジュールは`event["created"](Unixエポック秒)をそのまま
`event_time`としてdispatchする(他venture同様の`event.created`採用、design 3-5節)。

design 3-5節のステータスマッピング(フェーズ99で見直し: `active`・`trialing`・`past_due`→
`active`、`unpaid`・`canceled`・`incomplete_expired`→`canceled`)を
`_map_stripe_status_to_fan_pass_status()`として実コード化した。
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import List, Optional

from fan_pass_store import FanPass, InMemoryFanPassStore


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """`Stripe-Signature`ヘッダを検証する(design 2節のアルゴリズムどおり、他venture完全同一)。"""
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


# design 3-5節(フェーズ99見直し): Stripeサブスクリプションステータスの2値マッピング。
# `past_due`はStripe Billingのスマートリトライ(最大2週間、line-reservation-aiの
# payment-failure-dunning-design.mdで確認済みの一次情報)がまだ進行中の状態であり、
# カード会社側の再試行で自動的に"active"へ戻る可能性が高い。これを即座に"canceled"扱いに
# していた旧マッピングは、aircon-pasha等の決済失敗ドキュメント(猶予期間を設ける前提)を
# 踏まえて再検討した結果、月額フリーパス利用者(本ventureで唯一の継続課金対象、
# pricing-plan.md「月2回以上現場参加する頻度の高いファン」)に対してはStripe側の
# リトライが尽きる前に不要なアクセス遮断を行ってしまう設計上の誤りと判断した。
# "unpaid"(リトライ尽き)・"canceled"(解約)・"incomplete_expired"(初回決済失敗で確定しな
# かった)の3状態のみを"canceled"とし、"past_due"はStripeのリトライ期間中として"active"を
# 維持する(aircon-pasha同等の専用スケジューラ・タイムスタンプフィールドを新設せず、
# Stripe自身のリトライ機構をそのまま猶予期間として利用する軽量な設計。残課題の詳細は
# subscription-updated-past-due-grace-period-reconsideration.md参照)。
_ACTIVE_STRIPE_STATUSES = {"active", "trialing", "past_due"}


def _map_stripe_status_to_fan_pass_status(stripe_status: str) -> str:
    return "active" if stripe_status in _ACTIVE_STRIPE_STATUSES else "canceled"


@dataclass
class StripeDispatchResult:
    """dispatch_stripe_event()の結果。"""

    handled: bool
    action: Optional[str] = None
    internal_id: Optional[str] = None
    error: Optional[str] = None


def dispatch_stripe_event(
    event: dict,
    store: InMemoryFanPassStore,
    *,
    now: Optional[float] = None,
) -> StripeDispatchResult:
    """design 3節の4イベント種別のディスパッチ。対象外の種別は`handled=False`
    (`ignored_type`)を返すのみで200扱いとする(他venture同様の安全策)。"""
    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {})
    created = event.get("created")
    event_time = int(created) if isinstance(created, (int, float)) and not isinstance(created, bool) else None

    if event_type == "checkout.session.completed":
        return _handle_checkout_session_completed(data_object, store)

    if event_type == "customer.subscription.deleted":
        return _handle_subscription_status_change(
            data_object, store, status="canceled", event_time=event_time, action="subscription_deleted"
        )

    if event_type == "customer.subscription.created":
        # design 3-4節: 解約済み利用者の再加入のみを対象とする。新規契約相当(既存
        # ドキュメントが見つからない)は3-1(checkout.session.completed)側で処理済みの
        # はずという前提で、本ハンドラは何もしない(重複処理の回避)。
        stripe_subscription_id = data_object.get("subscription") or data_object.get("id")
        if not isinstance(stripe_subscription_id, str) or not store.get_by_stripe_subscription_id(
            stripe_subscription_id
        ):
            return StripeDispatchResult(handled=False, action="ignored_new_contract")
        return _handle_subscription_status_change(
            data_object, store, status="active", event_time=event_time, action="subscription_reactivated"
        )

    if event_type == "customer.subscription.updated":
        stripe_status = data_object.get("status")
        if not isinstance(stripe_status, str):
            return StripeDispatchResult(handled=False, error="missing_status")
        mapped_status = _map_stripe_status_to_fan_pass_status(stripe_status)
        return _handle_subscription_status_change(
            data_object, store, status=mapped_status, event_time=event_time, action="subscription_updated"
        )

    return StripeDispatchResult(handled=False, action="ignored_type")


def _handle_checkout_session_completed(
    data_object: dict, store: InMemoryFanPassStore
) -> StripeDispatchResult:
    # design 3-1節: mode=subscriptionのみを対象とし、mode=payment(都度プラン)は
    # 本ハンドラの対象外として無視する。
    if data_object.get("mode") != "subscription":
        return StripeDispatchResult(handled=False, action="ignored_mode")

    stripe_customer_id = data_object.get("customer")
    stripe_subscription_id = data_object.get("subscription")
    customer_details = data_object.get("customer_details") or {}
    email = customer_details.get("email")

    if (
        not isinstance(stripe_customer_id, str)
        or not stripe_customer_id
        or not isinstance(stripe_subscription_id, str)
        or not stripe_subscription_id
        or not isinstance(email, str)
        or not email
    ):
        return StripeDispatchResult(handled=False, error="missing_fields")

    internal_id, _access_token = store.create(
        email=email,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    return StripeDispatchResult(handled=True, action="fan_pass_created", internal_id=internal_id)


def _handle_subscription_status_change(
    data_object: dict,
    store: InMemoryFanPassStore,
    *,
    status: str,
    event_time: Optional[int],
    action: str,
) -> StripeDispatchResult:
    stripe_subscription_id = data_object.get("id") or data_object.get("subscription")
    if not isinstance(stripe_subscription_id, str) or not stripe_subscription_id:
        return StripeDispatchResult(handled=False, error="missing_subscription_id")

    fan_pass: Optional[FanPass] = store.get_by_stripe_subscription_id(stripe_subscription_id)
    if fan_pass is None:
        # design 3-3節: 該当ドキュメントが見つからない場合は異常系としてログに残すのみとし
        # 200を返す(他venture同型の安全策)。本プロトタイプではログ出力は行わない。
        return StripeDispatchResult(handled=False, error="fan_pass_not_found")

    store.update_subscription_status(fan_pass.internal_id, status, event_time=event_time)
    return StripeDispatchResult(handled=True, action=action, internal_id=fan_pass.internal_id)


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果。"""

    status_code: int
    dispatch_result: Optional[StripeDispatchResult] = None
    error: Optional[str] = None


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: InMemoryFanPassStore,
    now: Optional[float] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版)。署名検証に失敗した場合は401、
    JSONパース失敗・非dictの場合は400を返す(他venture同様の方針)。"""
    import json

    resolved_now = now if now is not None else time.time()
    if not verify_stripe_signature(body, signature_header, webhook_secret, now=resolved_now):
        return StripeWebhookReceiverResult(status_code=401, error="invalid_signature")

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(parsed, dict):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_event")

    dispatch_result = dispatch_stripe_event(parsed, store, now=resolved_now)
    return StripeWebhookReceiverResult(status_code=200, dispatch_result=dispatch_result)


def _demo() -> None:
    secret = "whsec_demo_secret"
    payload = b'{"id":"evt_demo","type":"customer.subscription.deleted","data":{"object":{"id":"sub_demo"}}}'
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={sig}"
    print("valid signature ->", verify_stripe_signature(payload, header, secret))
    print("missing header ->", verify_stripe_signature(payload, None, secret))


if __name__ == "__main__":
    _demo()
