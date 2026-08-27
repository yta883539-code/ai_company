"""Stripe Webhookの署名検証(stripe-webhook-signature-verification-design.md フェーズ125)・
HTTPエントリポイント(stripe-webhook-http-entry-point-design.md フェーズ127)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジック・`dispatch_stripe_event()`への配線のみを切り出したモジュール。
`cloud_function_webhook.py`(LINE側)・`deletion_candidate.py`とは独立した別ファイルとし、
既存コードには一切影響を与えない。

course-set-pasha/prototype/stripe_webhook.py(フェーズ93・95)の`verify_stripe_signature()`・
`receive_stripe_webhook()`と同一のアルゴリズム(design 2節のとおり、venture固有の差異は無い。
ただし本ventureは`checkout.session.completed`の受信配線は未着手のため、design「残課題」の
とおりその部分は含まない)。
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

    - 署名検証に失敗した場合は401相当を返し、JSONパース以降の配線を一切行わない
      (不正なリクエストへの余計な処理を避ける、LINE側receive_webhook()と同じ方針)。
    - 署名検証後にbodyをJSONとしてパースする。パース失敗、またはパース結果がdictでない
      場合は400相当を返す(Stripeからの実際のリクエストでは通常発生しないはずの異常系だが、
      エントリポイントとして不正な入力にも例外を外に漏らさない設計とする)。
    - それ以外のイベント種別はdispatch_stripe_event()にそのまま委譲し200を返す。
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
