"""Stripe Webhookの署名検証(stripe-webhook-signature-verification-design.md フェーズ125)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジックのみを切り出したモジュール。`cloud_function_webhook.py`(LINE側)・
`deletion_candidate.py`とは独立した別ファイルとし、既存コードには一切影響を与えない。

course-set-pasha/prototype/stripe_webhook.py(フェーズ93)の`verify_stripe_signature()`と
同一のアルゴリズム(design 2節のとおり、venture固有の差異は無い)。
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import List, Optional


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
