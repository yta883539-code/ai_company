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
from one_time_pass_store import OneTimePass

MAX_POLL_ATTEMPTS = 5
POLL_INTERVAL_SECONDS = 1.0


class StripeCheckoutSessionLookupProtocol(Protocol):
    def get_subscription_id_for_session(self, checkout_session_id: str) -> "str | None":
        """design.md 3-2節(a)参照。Sessionが見つからない、またはsubscriptionフィールドが
        無い場合はNone。"""
        ...


class _FanPassLookupProtocol(Protocol):
    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> "FanPass | None": ...


class StripeCheckoutSessionModeLookupProtocol(Protocol):
    def get_mode_for_session(self, checkout_session_id: str) -> "str | None":
        """one-time-plan-access-token-design.md 3節参照。Checkout Sessionの`mode`
        ("subscription" | "payment")を返す。Session自体が見つからない場合はNone
        (既存のStripeCheckoutSessionLookupProtocol.get_subscription_id_for_sessionと同じ
        「見つからない」の表現方法を踏襲する)。"""
        ...


class _OneTimePassLookupProtocol(Protocol):
    def get_by_checkout_session_id(
        self, stripe_checkout_session_id: str
    ) -> "OneTimePass | None": ...


@dataclass(frozen=True)
class PassLookupResult:
    """design.md 3節が定義する、月額フリーパス(fan_pass)・都度プラン(one_time_pass)の
    いずれであってもCombinedPassLookupProtocolの戻り値として正規化された共通表現。
    `consumed`は都度プランのみ意味を持ち(design.md 4節の1回使用後の失効判定は次回候補の
    receive_generation_request側の責務であり、本モジュールはpoll結果への素通し以上の
    分岐は行わない)、月額フリーパス側は常にFalseとする。"""

    access_token: str
    consumed: bool = False


class CombinedPassLookupProtocol(Protocol):
    def get_by_checkout_session(self, checkout_session_id: str) -> "PassLookupResult | None":
        """design.md 3節参照。mode=="subscription"ならfan_pass_store経由、
        mode=="payment"ならone_time_pass_store経由で解決し、共通のPassLookupResultに
        正規化する。該当するドキュメントがまだ存在しない(Webhook未到達)場合はNone。"""
        ...


class CombinedPassLookup:
    """CombinedPassLookupProtocolの検証用実装。design.md 3節のとおり、Checkout Sessionの
    modeで`fan_pass_store`経由(mode=="subscription")と`one_time_pass_store`経由
    (mode=="payment")を振り分ける。既存のStripeCheckoutSessionLookupProtocol・
    _FanPassLookupProtocolはフェーズ100の実装を変更せずそのまま再利用する
    (design.md 3節が明記する「破壊的変更を避ける」方針)。"""

    def __init__(
        self,
        mode_lookup: StripeCheckoutSessionModeLookupProtocol,
        stripe_lookup: StripeCheckoutSessionLookupProtocol,
        fan_pass_store: _FanPassLookupProtocol,
        one_time_pass_store: _OneTimePassLookupProtocol,
    ) -> None:
        self._mode_lookup = mode_lookup
        self._stripe_lookup = stripe_lookup
        self._fan_pass_store = fan_pass_store
        self._one_time_pass_store = one_time_pass_store

    def get_by_checkout_session(self, checkout_session_id: str) -> "PassLookupResult | None":
        mode = self._mode_lookup.get_mode_for_session(checkout_session_id)
        if mode == "subscription":
            stripe_subscription_id = self._stripe_lookup.get_subscription_id_for_session(
                checkout_session_id
            )
            if stripe_subscription_id is None:
                return None
            fan_pass = self._fan_pass_store.get_by_stripe_subscription_id(stripe_subscription_id)
            if fan_pass is None:
                return None
            return PassLookupResult(access_token=fan_pass.access_token)

        if mode == "payment":
            one_time_pass = self._one_time_pass_store.get_by_checkout_session_id(
                checkout_session_id
            )
            if one_time_pass is None:
                return None
            return PassLookupResult(
                access_token=one_time_pass.access_token,
                consumed=one_time_pass.consumed_at is not None,
            )

        return None


class CheckoutSessionNotFoundError(Exception):
    """Stripe側にCheckout Session自体が見つからない場合に送出する(URL改ざん・期限切れ等の
    異常系。design.mdはポーリング対象外の即時エラーとして扱う想定)。"""


@dataclass(frozen=True)
class CheckoutResultPageResult:
    status: str  # "ready" | "pending"
    access_token: Optional[str] = None
    poll_attempts_used: int = 0
    consumed: bool = False


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


def resolve_checkout_result_combined(
    mode_lookup: StripeCheckoutSessionModeLookupProtocol,
    combined_lookup: CombinedPassLookupProtocol,
    checkout_session_id: str,
    *,
    sleep: Callable[[float], None] = lambda _seconds: None,
    max_attempts: int = MAX_POLL_ATTEMPTS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> CheckoutResultPageResult:
    """design.md 3節のとおり、`resolve_checkout_result()`のルックアップ手順を
    `CombinedPassLookupProtocol`に差し替えた版。都度プラン(mode=="payment")・
    月額フリーパス(mode=="subscription")のいずれにも対応する。

    Session自体が見つからない(URL改ざん・期限切れ等)場合の即時エラー判定は、
    既存の`resolve_checkout_result()`と同じく、ポーリングループの外で一度だけ行う
    (`mode_lookup.get_mode_for_session()`がNoneを返す場合。Webhook未到達による
    「まだ準備中」とは区別する、design.md 3節の方針を踏襲)。"""

    mode = mode_lookup.get_mode_for_session(checkout_session_id)
    if mode is None:
        raise CheckoutSessionNotFoundError(
            f"checkout_session_id={checkout_session_id!r} not found on Stripe side"
        )

    for attempt in range(1, max_attempts + 1):
        pass_result = combined_lookup.get_by_checkout_session(checkout_session_id)
        if pass_result is not None:
            return CheckoutResultPageResult(
                status="ready",
                access_token=pass_result.access_token,
                poll_attempts_used=attempt,
                consumed=pass_result.consumed,
            )
        if attempt < max_attempts:
            sleep(interval_seconds)

    return CheckoutResultPageResult(status="pending", poll_attempts_used=max_attempts)


def receive_checkout_result_request_combined(
    mode_lookup: StripeCheckoutSessionModeLookupProtocol,
    combined_lookup: CombinedPassLookupProtocol,
    checkout_session_id: Optional[str],
    *,
    sleep: Callable[[float], None] = lambda _seconds: None,
    max_attempts: int = MAX_POLL_ATTEMPTS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> CheckoutResultHttpResult:
    """`receive_checkout_result_request()`の`CombinedPassLookupProtocol`版。
    都度プラン・月額フリーパス両対応のエントリポイントとして、こちらを新規導入する
    (既存の`receive_checkout_result_request()`は月額フリーパス専用の呼び出し元
    〈既存テスト〉への破壊的変更を避けるため変更しない)。"""

    if checkout_session_id is None or not checkout_session_id.strip():
        return CheckoutResultHttpResult(status_code=400, error="missing_checkout_session_id")

    try:
        result = resolve_checkout_result_combined(
            mode_lookup,
            combined_lookup,
            checkout_session_id,
            sleep=sleep,
            max_attempts=max_attempts,
            interval_seconds=interval_seconds,
        )
    except CheckoutSessionNotFoundError:
        return CheckoutResultHttpResult(status_code=404, error="unknown_checkout_session_id")

    return CheckoutResultHttpResult(status_code=200, result=result)


class InMemoryStripeCheckoutSessionModeLookup:
    """StripeCheckoutSessionModeLookupProtocolの検証用インメモリ実装。
    `checkout_session_id -> mode`の対応表を保持する。既存の
    `InMemoryStripeCheckoutSessionLookup`(subscription_id専用)とは別個の対応表とし、
    実Stripe側ではSession取得時に両フィールド(`mode`・`subscription`)が同時に
    返ってくる1回のAPI呼び出しに相当する(インメモリ実装では検証のしやすさのため
    分離している)。"""

    def __init__(self) -> None:
        self._mode_by_session: dict[str, str] = {}

    def register(self, checkout_session_id: str, mode: str) -> None:
        self._mode_by_session[checkout_session_id] = mode

    def get_mode_for_session(self, checkout_session_id: str) -> "str | None":
        return self._mode_by_session.get(checkout_session_id)


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
