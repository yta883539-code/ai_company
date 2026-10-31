#!/usr/bin/env python3
"""
access-url-resend-api-design.md(フェーズ42)で確定した「アクセスURLを再送する」ページ
(monthly-pass-identity-design.md 3節)の処理本体をコード化したもの。

位置づけ:
- fan_pass_store.pyに続く本venture3本目のprototype/コード。実Stripe接続・実メール送信は
  いずれもオーナー承認待ちの範囲(pending-approval.md参照)のため、本モジュールでは行わない。
- `StripeSubscriptionLookupProtocol`は`customers.list(email=...)`→
  `subscriptions.list(customer=..., status="active")`の実呼び出しを1回の問い合わせに
  集約した抽象で、本フェーズではインメモリの偽実装のみを用意する。
- 「見つからない」をどう見せるか(design.md 4節)は本モジュールの責務外とし、
  `found: bool`を含む`ResendRequestResult`を返すところまでを担う
  (HTTPエントリポイント側で常に同一レスポンスに畳み込む想定)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol

from fan_pass_store import FanPass


class _FanPassLookupAndReissueProtocol(Protocol):
    """fan_pass_store.InMemoryFanPassStoreのうち、本モジュールが使う2メソッドのみを
    束ねた最小Protocol(forklift-pashaの`_EmailFieldStoreProtocol`と同じ考え方)。
    fan-pass-store-protocol-design.mdの`FanPassStoreProtocol`本体はコード化されていない
    (ドキュメント内のインターフェース定義のみ)ため、実装クラスから直接構造的に合致させる。
    """

    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> "FanPass | None": ...

    def reissue_access_token(self, internal_id: str, *, new_access_token: str) -> None: ...


class MultipleActiveSubscriptionsError(Exception):
    """同一メールアドレスに対し複数の有効なサブスクリプションが見つかった場合に送出する
    (fan-pass-store-protocol-design.md 3節の単一プラン前提が崩れた異常系)。"""


class FanPassNotFoundForSubscriptionError(Exception):
    """Stripe側に有効なサブスクリプションがあるのに、対応するfan_passドキュメントが
    Firestore側に見つからない場合に送出する(Webhook処理の未完了・不整合を示す異常系)。"""


class StripeSubscriptionLookupProtocol(Protocol):
    def find_active_subscription_id_by_email(self, email: str) -> "str | None":
        """design.md 2節参照。見つからない場合はNone。"""
        ...


@dataclass(frozen=True)
class ResendRequestResult:
    found: bool
    internal_id: Optional[str] = None
    new_access_token: Optional[str] = None
    destination_email: Optional[str] = None


def handle_resend_request(
    fan_pass_store: _FanPassLookupAndReissueProtocol,
    stripe_lookup: StripeSubscriptionLookupProtocol,
    email: str,
    *,
    new_access_token_factory: Callable[[], str],
) -> ResendRequestResult:
    """design.md 3節の処理順序どおりに実行する。"""

    stripe_subscription_id = stripe_lookup.find_active_subscription_id_by_email(email)
    if stripe_subscription_id is None:
        return ResendRequestResult(found=False)

    fan_pass = fan_pass_store.get_by_stripe_subscription_id(stripe_subscription_id)
    if fan_pass is None:
        raise FanPassNotFoundForSubscriptionError(
            f"stripe_subscription_id={stripe_subscription_id!r} has an active Stripe "
            "subscription but no matching fan_pass document"
        )

    new_access_token = new_access_token_factory()
    fan_pass_store.reissue_access_token(fan_pass.internal_id, new_access_token=new_access_token)

    return ResendRequestResult(
        found=True,
        internal_id=fan_pass.internal_id,
        new_access_token=new_access_token,
        destination_email=email,
    )


class InMemoryStripeSubscriptionLookup:
    """StripeSubscriptionLookupProtocolの検証用インメモリ実装。
    `email -> stripe_subscription_id`(単一)または`email -> [stripe_subscription_id, ...]`
    (複数登録して異常系をテストする用途)の対応表を保持する。
    """

    def __init__(self) -> None:
        self._subscription_ids_by_email: dict[str, list[str]] = {}

    def register(self, email: str, stripe_subscription_id: str) -> None:
        self._subscription_ids_by_email.setdefault(email, []).append(stripe_subscription_id)

    def find_active_subscription_id_by_email(self, email: str) -> "str | None":
        subscription_ids = self._subscription_ids_by_email.get(email, [])
        if not subscription_ids:
            return None
        if len(subscription_ids) > 1:
            raise MultipleActiveSubscriptionsError(
                f"email={email!r} has {len(subscription_ids)} active subscriptions, expected at most 1"
            )
        return subscription_ids[0]
