#!/usr/bin/env python3
"""
fan-pass-store-protocol-design.md(フェーズ39)で確定した`FanPassStoreProtocol`
(create・get_by_access_token・get_by_stripe_subscription_id・update_subscription_status・
reissue_access_token)を実行可能なコードに落とし込んだもの。

位置づけ:
- usage_counter.pyに続く本venture2本目のprototype/コード。実Firestore接続なしにロジックのみ
  を検証可能にする。実LLM呼び出し・実Firestore・実Stripe接続はいずれもオーナー承認待ちの範囲
  (pending-approval.md参照)で、本モジュールでは行わない。
- firestore-data-model.md 1.1節`fan_pass/{internal_id}`の5フィールド(accessToken・email・
  stripeCustomerId・stripeSubscriptionId・subscriptionStatus)を前提とする。
  currentPeriodEnd・currentMonthGenerationCount・generationCountMonthは対象外
  (前者は未着手、後者2つはusage_counter.py側の責務)。
- internal_idの発行はFirestoreの自動生成IDを想定するため、本インメモリ実装では
  uuid4の16進数文字列で代替する。
- `create`はStripe Webhookの重複配信(fan-pass-store-protocol-design.md 3節の残課題)に
  対応し、同一stripe_subscription_idで再度呼ばれた場合は新規発行せず既存の
  (internal_id, accessToken)を返す(フェーズ40)。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace


class UnknownInternalIdError(Exception):
    """internal_idに対応するfan_passドキュメントが未登録(存在しない)場合に送出する
    (fan-pass-store-protocol-design.md 2節)。
    """


class InvalidSubscriptionStatusError(Exception):
    """"active"|"canceled"以外のstatusが渡された場合に送出する。"""


@dataclass(frozen=True)
class FanPass:
    """`fan_pass/{internal_id}`ドキュメントのうち本プロトコルが扱う5フィールドの机上表現。"""

    internal_id: str
    access_token: str
    email: str
    stripe_customer_id: str
    stripe_subscription_id: str
    subscription_status: str


_VALID_STATUSES = {"active", "canceled"}


class InMemoryFanPassStore:
    """usage_counter.pyのInMemoryUsageCounterStoreと同じ位置づけの検証用実装。"""

    def __init__(self) -> None:
        self._by_internal_id: dict[str, FanPass] = {}
        self._internal_id_by_access_token: dict[str, str] = {}
        self._internal_id_by_subscription_id: dict[str, str] = {}

    def create(
        self,
        *,
        email: str,
        stripe_customer_id: str,
        stripe_subscription_id: str,
    ) -> tuple[str, str]:
        existing_internal_id = self._internal_id_by_subscription_id.get(stripe_subscription_id)
        if existing_internal_id is not None:
            existing = self._by_internal_id[existing_internal_id]
            return existing.internal_id, existing.access_token

        internal_id = uuid.uuid4().hex
        access_token = uuid.uuid4().hex

        fan_pass = FanPass(
            internal_id=internal_id,
            access_token=access_token,
            email=email,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            subscription_status="active",
        )
        self._by_internal_id[internal_id] = fan_pass
        self._internal_id_by_access_token[access_token] = internal_id
        self._internal_id_by_subscription_id[stripe_subscription_id] = internal_id
        return internal_id, access_token

    def get_by_access_token(self, access_token: str) -> FanPass | None:
        internal_id = self._internal_id_by_access_token.get(access_token)
        if internal_id is None:
            return None
        return self._by_internal_id.get(internal_id)

    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> FanPass | None:
        internal_id = self._internal_id_by_subscription_id.get(stripe_subscription_id)
        if internal_id is None:
            return None
        return self._by_internal_id.get(internal_id)

    def update_subscription_status(self, internal_id: str, status: str) -> None:
        if status not in _VALID_STATUSES:
            raise InvalidSubscriptionStatusError(
                f"status must be one of {sorted(_VALID_STATUSES)}, got {status!r}"
            )
        fan_pass = self._require(internal_id)
        self._by_internal_id[internal_id] = replace(fan_pass, subscription_status=status)

    def reissue_access_token(self, internal_id: str, *, new_access_token: str) -> None:
        fan_pass = self._require(internal_id)
        del self._internal_id_by_access_token[fan_pass.access_token]
        self._internal_id_by_access_token[new_access_token] = internal_id
        self._by_internal_id[internal_id] = replace(fan_pass, access_token=new_access_token)

    def _require(self, internal_id: str) -> FanPass:
        fan_pass = self._by_internal_id.get(internal_id)
        if fan_pass is None:
            raise UnknownInternalIdError(
                f"fan_pass document not found for internal_id={internal_id!r}"
            )
        return fan_pass
