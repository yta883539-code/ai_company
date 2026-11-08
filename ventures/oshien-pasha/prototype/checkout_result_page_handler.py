#!/usr/bin/env python3
"""
stripe-webhook-entry-point-design.md(フェーズ95)3-2節で確定した「決済完了直後の
結果ページ表示」処理本体をコード化したもの(同design 4節・次回候補1で「次回以降に着手」と
されていた分、フェーズ98で実コード化)。

位置づけ:
- Webhookの非同期配信とブラウザのreturn_urlリダイレクトという2経路の完了順序は保証
  されないため、結果ページ表示時点ではまだ`fan_pass`ドキュメントが作成されていない
  (Webhook未到達)場合がある。本モジュールはCheckout Session IDを受け取り、
  (a)Stripe側でSessionを取得して`stripe_subscription_id`を得た上で、
  (b)`fan_pass_store.get_by_stripe_subscription_id()`への問い合わせを短い間隔で
  最大5回まで再試行し、それでも見つからない場合のみ「準備中」を返す。
- 実Stripe API呼び出し・実スリープはいずれもオーナー承認待ちの範囲外(テスト容易性のため)
  としてProtocol/Callableで差し替え可能にし、本フェーズではインメモリの偽実装のみ用意する
  (access_url_resend_handler.pyの`StripeSubscriptionLookupProtocol`と同じ考え方)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from fan_pass_store import FanPass

MAX_POLL_ATTEMPTS = 5
POLL_INTERVAL_SECONDS = 1.0


class StripeCheckoutSessionLookupProtocol(Protocol):
    def get_subscription_id_for_session(self, checkout_session_id: str) -> "str | None":
        """design.md 3-2節(a)参照。Sessionが見つからない、またはsubscriptionフィールドが
        無い場合はNone。"""
        ...


class _FanPassLookupProtocol(Protocol):
    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> "FanPass | None": ...


class CheckoutSessionNotFoundError(Exception):
    """Stripe側にCheckout Session自体が見つからない場合に送出する(URL改ざん・期限切れ等の
    異常系。design.mdはポーリング対象外の即時エラーとして扱う想定)。"""


@dataclass(frozen=True)
class CheckoutResultPageResult:
    status: str  # "ready" | "pending"
    access_token: Optional[str] = None
    poll_attempts_used: int = 0


def resolve_checkout_result(
    stripe_lookup: StripeCheckoutSessionLookupProtocol,
    fan_pass_store: _FanPassLookupProtocol,
    checkout_session_id: str,
    *,
    sleep: Callable[[float], None] = lambda _seconds: None,
    max_attempts: int = MAX_POLL_ATTEMPTS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> CheckoutResultPageResult:
    """design.md 3-2節の処理順序どおりに実行する。(a)Session取得→(b)fan_pass問い合わせを
    `max_attempts`回まで`interval_seconds`間隔で再試行する。"""

    stripe_subscription_id = stripe_lookup.get_subscription_id_for_session(checkout_session_id)
    if stripe_subscription_id is None:
        raise CheckoutSessionNotFoundError(
            f"checkout_session_id={checkout_session_id!r} not found on Stripe side"
        )

    for attempt in range(1, max_attempts + 1):
        fan_pass = fan_pass_store.get_by_stripe_subscription_id(stripe_subscription_id)
        if fan_pass is not None:
            return CheckoutResultPageResult(
                status="ready",
                access_token=fan_pass.access_token,
                poll_attempts_used=attempt,
            )
        if attempt < max_attempts:
            sleep(interval_seconds)

    return CheckoutResultPageResult(status="pending", poll_attempts_used=max_attempts)


@dataclass(frozen=True)
class CheckoutResultHttpResult:
    status_code: int
    result: Optional[CheckoutResultPageResult] = None
    error: Optional[str] = None


def receive_checkout_result_request(
    stripe_lookup: StripeCheckoutSessionLookupProtocol,
    fan_pass_store: _FanPassLookupProtocol,
    checkout_session_id: Optional[str],
    *,
    sleep: Callable[[float], None] = lambda _seconds: None,
    max_attempts: int = MAX_POLL_ATTEMPTS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> CheckoutResultHttpResult:
    """checkout-result-http-entry-point-design.md(フェーズ100)2節の処理順序どおりに
    実行する。`resolve_checkout_result()`の例外(`CheckoutSessionNotFoundError`)を
    404へ変換する、本venture唯一のエントリポイントである。"""

    if checkout_session_id is None or not checkout_session_id.strip():
        return CheckoutResultHttpResult(status_code=400, error="missing_checkout_session_id")

    try:
        result = resolve_checkout_result(
            stripe_lookup,
            fan_pass_store,
            checkout_session_id,
            sleep=sleep,
            max_attempts=max_attempts,
            interval_seconds=interval_seconds,
        )
    except CheckoutSessionNotFoundError:
        return CheckoutResultHttpResult(status_code=404, error="unknown_checkout_session_id")

    return CheckoutResultHttpResult(status_code=200, result=result)


class InMemoryStripeCheckoutSessionLookup:
    """StripeCheckoutSessionLookupProtocolの検証用インメモリ実装。
    `checkout_session_id -> stripe_subscription_id`の対応表を保持し、
    Webhook到達前は未登録のままにしておくことで「未到達」を再現できる。"""

    def __init__(self) -> None:
        self._subscription_id_by_session: dict[str, str] = {}

    def register(self, checkout_session_id: str, stripe_subscription_id: str) -> None:
        self._subscription_id_by_session[checkout_session_id] = stripe_subscription_id

    def get_subscription_id_for_session(self, checkout_session_id: str) -> "str | None":
        return self._subscription_id_by_session.get(checkout_session_id)
