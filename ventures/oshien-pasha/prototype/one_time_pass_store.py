#!/usr/bin/env python3
"""
one-time-plan-access-token-design.md(フェーズ104)で確定した`one_time_pass/{internal_id}`
コレクション(accessToken・stripeCheckoutSessionId・consumedAt・createdAt・expiresAt)を
実行可能なコードに落とし込んだもの。

位置づけ:
- fan_pass_store.pyと同じ位置づけの検証用インメモリ実装。実Firestore接続はオーナー承認待ちの
  範囲(pending-approval.md参照)で、本モジュールでは行わない。
- `create`はStripe Webhook(checkout.session.completed, mode=payment)の重複配信に対応し、
  同一stripe_checkout_session_idで再度呼ばれた場合は新規発行せず既存の
  (internal_id, access_token)を返す(fan_pass_store.pyのstripe_subscription_id方式〈フェーズ40〉
  を踏襲)。
- `expires_at`はcreated_at起点+24時間(one-time-plan-access-token-design.md 2節)。呼び出し元が
  Stripe Webhookの`event.created`(Unixエポック秒)をそのまま`created_at`として渡す想定で、
  現在時刻の取得(`time.time()`)自体は本モジュールの責務外とする(fan_pass_store.pyの
  `event_time`引数と同じ、呼び出し元が時刻を明示的に渡す方針)。
- 1回使用後の失効判定(`consumed_at`が既に設定済みなら403、`expires_at`超過なら404)という
  ステータスコード振り分け自体はCombinedPassLookupProtocol側(次回候補)の責務とし、本モジュールは
  `consumed_at`への書き込み・読み出しのみを提供する「ストア」の責務に留める
  (one-time-plan-access-token-design.md 4節)。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

_EXPIRES_AFTER_SECONDS = 24 * 60 * 60


class UnknownInternalIdError(Exception):
    """internal_idに対応するone_time_passドキュメントが未登録(存在しない)場合に送出する。"""


class AlreadyConsumedError(Exception):
    """既にconsumed_atが設定済みのドキュメントに対して再度mark_consumed()を呼んだ場合に送出する
    (one-time-plan-access-token-design.md 4節の「生成成功後にのみ消費済みにする」順序を
    ストア側でも二重に保護するためのガード)。
    """


@dataclass(frozen=True)
class OneTimePass:
    """`one_time_pass/{internal_id}`ドキュメントの机上表現。"""

    internal_id: str
    access_token: str
    stripe_checkout_session_id: str
    created_at: int
    expires_at: int
    consumed_at: int | None = None


class InMemoryOneTimePassStore:
    """fan_pass_store.pyのInMemoryFanPassStoreと同じ位置づけの検証用実装。"""

    def __init__(self) -> None:
        self._by_internal_id: dict[str, OneTimePass] = {}
        self._internal_id_by_access_token: dict[str, str] = {}
        self._internal_id_by_checkout_session_id: dict[str, str] = {}

    def create(
        self,
        *,
        stripe_checkout_session_id: str,
        created_at: int,
    ) -> tuple[str, str]:
        existing_internal_id = self._internal_id_by_checkout_session_id.get(
            stripe_checkout_session_id
        )
        if existing_internal_id is not None:
            existing = self._by_internal_id[existing_internal_id]
            return existing.internal_id, existing.access_token

        internal_id = uuid.uuid4().hex
        access_token = uuid.uuid4().hex

        one_time_pass = OneTimePass(
            internal_id=internal_id,
            access_token=access_token,
            stripe_checkout_session_id=stripe_checkout_session_id,
            created_at=created_at,
            expires_at=created_at + _EXPIRES_AFTER_SECONDS,
        )
        self._by_internal_id[internal_id] = one_time_pass
        self._internal_id_by_access_token[access_token] = internal_id
        self._internal_id_by_checkout_session_id[stripe_checkout_session_id] = internal_id
        return internal_id, access_token

    def get_by_access_token(self, access_token: str) -> OneTimePass | None:
        internal_id = self._internal_id_by_access_token.get(access_token)
        if internal_id is None:
            return None
        return self._by_internal_id.get(internal_id)

    def get_by_checkout_session_id(self, stripe_checkout_session_id: str) -> OneTimePass | None:
        internal_id = self._internal_id_by_checkout_session_id.get(stripe_checkout_session_id)
        if internal_id is None:
            return None
        return self._by_internal_id.get(internal_id)

    def mark_consumed(self, internal_id: str, *, consumed_at: int) -> None:
        one_time_pass = self._require(internal_id)
        if one_time_pass.consumed_at is not None:
            raise AlreadyConsumedError(
                f"one_time_pass document already consumed for internal_id={internal_id!r}"
            )
        self._by_internal_id[internal_id] = replace(one_time_pass, consumed_at=consumed_at)

    def _require(self, internal_id: str) -> OneTimePass:
        one_time_pass = self._by_internal_id.get(internal_id)
        if one_time_pass is None:
            raise UnknownInternalIdError(
                f"one_time_pass document not found for internal_id={internal_id!r}"
            )
        return one_time_pass
