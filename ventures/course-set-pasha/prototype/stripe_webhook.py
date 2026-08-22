"""Stripe Webhookの署名検証・イベント種別ディスパッチ
(stripe-webhook-signature-verification-design.md フェーズ93、
stripe-webhook-event-dispatch-design.md フェーズ94)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジック・イベント種別ディスパッチロジックを切り出したモジュール。
`cloud_function_webhook.py`(LINE側)とは独立した別ファイルとし、既存のLINE側コードには
一切影響を与えない。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional

from deletion_candidate import (
    ProfileDeletionCandidateStoreProtocol,
    clear_deletion_candidate_on_subscription_reactivated,
    mark_deletion_candidate_on_subscription_deleted,
)


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
    v1_signatures: list[str] = []
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


_HANDLED_EVENT_TYPES = frozenset(
    {
        "customer.subscription.deleted",
        "customer.subscription.created",
        "customer.subscription.updated",
    }
)

_REACTIVATED_STATUSES = frozenset({"active", "trialing"})


@dataclass
class StripeDispatchResult:
    """stripe-webhook-event-dispatch-design.md 2節。"""

    marked_user_ids: list = field(default_factory=list)
    cleared_user_ids: list = field(default_factory=list)
    ignored_types: list = field(default_factory=list)
    unresolved_customers: list = field(default_factory=list)
    invalid_events: list = field(default_factory=list)


def dispatch_stripe_event(
    event: dict,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    now: Optional[datetime] = None,
) -> StripeDispatchResult:
    """stripe-webhook-event-dispatch-design.md 1節のとおり、Stripe Webhookイベント1件を
    種別に応じて`prototype/deletion_candidate.py`の関数へ振り分ける。
    """
    result = StripeDispatchResult()

    event_type = event.get("type")
    if event_type not in _HANDLED_EVENT_TYPES:
        if event_type is not None:
            result.ignored_types.append(event_type)
        return result

    data_object = event.get("data", {}).get("object", {})
    customer = data_object.get("customer")
    user_id = resolve_user_id(customer) if customer is not None else None
    if user_id is None:
        result.unresolved_customers.append(customer)
        return result

    if event_type == "customer.subscription.deleted":
        created = event.get("created")
        if not isinstance(created, (int, float)) or isinstance(created, bool):
            result.invalid_events.append(event_type)
            return result
        event_time = datetime.fromtimestamp(created, tz=timezone.utc)
        mark_deletion_candidate_on_subscription_deleted(store, user_id, event_time)
        result.marked_user_ids.append(user_id)
        return result

    if event_type == "customer.subscription.created":
        clear_deletion_candidate_on_subscription_reactivated(store, user_id)
        result.cleared_user_ids.append(user_id)
        return result

    # customer.subscription.updated: active/trialing 以外への変化は対象外(design 1節5.)。
    # 記録すべき異常があるわけではないので、result には何も追加せず終える。
    if data_object.get("status") in _REACTIVATED_STATUSES:
        clear_deletion_candidate_on_subscription_reactivated(store, user_id)
        result.cleared_user_ids.append(user_id)

    return result


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果(stripe-webhook-http-entry-point-design.md 1節)。"""

    status_code: int
    dispatch_result: Optional[StripeDispatchResult] = None
    error: Optional[str] = None


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版)。生のリクエストボディ(bytes)を
    受け取り、署名検証(verify_stripe_signature)・JSONパース・dispatch_stripe_event()への
    配線までを行う(stripe-webhook-http-entry-point-design.mdで設計した、
    verify_stripe_signature()とdispatch_stripe_event()を結ぶエントリポイント)。

    - 署名検証に失敗した場合は401相当を返し、JSONパース・dispatch_stripe_event()への
      配線を一切行わない(不正なリクエストへの余計な処理を避ける、LINE側receive_webhook()と
      同じ方針)。
    - 署名検証後にbodyをJSONとしてパースする。パース失敗、またはパース結果がdictでない
      場合は400相当を返す(Stripeからの実際のリクエストでは通常発生しないはずの異常系だが、
      エントリポイントとして不正な入力にも例外を外に漏らさない設計とする)。
    - 検証・パースに成功した場合はdispatch_stripe_event()にそのまま委譲し200を返す。
      resolve_user_idが解決できなかった場合・対象外のイベント種別であっても、Stripe側の
      再送ループを避けるためリクエスト自体は200(受理)として扱う。
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

    dispatch_result = dispatch_stripe_event(
        parsed, store=store, resolve_user_id=resolve_user_id, now=resolved_now
    )
    return StripeWebhookReceiverResult(status_code=200, dispatch_result=dispatch_result)
