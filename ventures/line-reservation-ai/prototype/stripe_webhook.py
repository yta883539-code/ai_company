#!/usr/bin/env python3
"""stripe-webhook-signature-verification-design.md(フェーズ続き158)で設計した、Stripe
Webhook受信時の`Stripe-Signature`ヘッダ署名検証。

位置づけ:
- 実Stripeアカウント作成・Webhookエンドポイント登録・`webhook_secret`の取得はいずれも
  「アカウント作成」に該当し、オーナー承認待ち(pending-approval.md参照)。本モジュールは
  それとは独立に、公開されているStripe公式の署名検証アルゴリズムのみを実HTTPリクエスト
  なしで検証可能にしたもの(aircon-pasha/course-set-pashaの同名モジュールと同一アルゴリズム)。
- 実際のWebhookエンドポイント本体(署名検証〜イベント種別ディスパッチ〜
  `store_profile_store.handle_checkout_session_completed()`等の呼び出しを結ぶ層)は
  design「残課題」のとおり本モジュールのスコープ外で、次回以降の課題として残る。

設計の参照元: stripe-webhook-signature-verification-design.md
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Optional


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """design 2節のアルゴリズムをそのまま実装する。

    未検証時(ヘッダ欠落・形式不正・署名不一致・許容範囲外)はいずれも`False`を返す
    「安全側で拒否」方針(本venture既存の`verify_line_signature()`と同じ考え方)。
    """
    if not sig_header:
        return False

    timestamp: Optional[str] = None
    v1_signatures: list[str] = []
    for part in sig_header.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t" and timestamp is None:
            timestamp = value
        elif key == "v1" and value:
            v1_signatures.append(value)

    if not timestamp or not v1_signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    current_time = time.time() if now is None else now
    if abs(current_time - timestamp_int) > tolerance_seconds:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected_signature = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()

    return any(
        hmac.compare_digest(expected_signature, candidate)
        for candidate in v1_signatures
    )
