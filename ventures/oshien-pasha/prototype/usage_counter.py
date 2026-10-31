#!/usr/bin/env python3
"""
usage-counter-store-protocol-design.md(フェーズ37)で確定した`UsageCounterStoreProtocol`
(record_generation・get_current_month_countの2メソッド)を実行可能なコードに落とし込んだもの。

位置づけ:
- 本venture初のprototype/コード(usage-counter-store-protocol-design.md「未検証・残課題」
  1点目に対応)。kura-pasha/course-set-pashaのprototype/usage_counter_*.pyと同じ位置づけで、
  実Firestore接続なしにロジックのみを検証可能にする。実LLM呼び出し・実Firestore・実Stripe
  接続はいずれもオーナー承認待ちの範囲(pending-approval.md参照)で、本モジュールでは行わない。
- generation-count-design.md(フェーズ8)が確定した`fan_pass/{internal_id}`の
  `currentMonthGenerationCount`・`generationCountMonth`・`generation_log`サブコレクション
  (`requestedAt`・`venueMatched`・`inputPerformanceCount`)を前提とする。
- usage-counter-store-protocol-design.md 2節の注記「internal_idに対応するfan_passドキュメント
  が存在しない等で呼び出し自体が失敗した場合は例外を送出する契約とする」を検証できるよう、
  `InMemoryUsageCounterStore`はregister()で既知のinternal_idを明示的に登録する方式とした
  (本venture自身のfan_passドキュメント新規作成処理はまだ存在しないため、その代替として
  register()を設けた)。未登録のinternal_idへのrecord_generation/get_current_month_count
  呼び出しはいずれもUnknownInternalIdErrorを送出する。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

_JST = timezone(timedelta(hours=9))


def current_month_jst() -> str:
    """JST基準の暦月をYYYY-MM形式で返す(course-set-pashaのcurrent_month_jst()と同じ方針、
    usage-counter-store-protocol-design.md 3節「当月判定は実装側に委ねる」に対応)。
    """
    return datetime.now(_JST).strftime("%Y-%m")


class UnknownInternalIdError(Exception):
    """internal_idに対応するfan_passドキュメントが未登録(存在しない)場合に送出する
    (usage-counter-store-protocol-design.md 2節注記への対応)。
    """


@dataclass
class GenerationLogEntry:
    """`fan_pass/{internal_id}/generation_log`配下の1ドキュメントの机上表現
    (generation-count-design.md 2節のフィールド構成そのまま)。
    """

    requested_at: datetime
    venue_matched: bool
    input_performance_count: int


class UsageCounterStoreProtocol(Protocol):
    """usage-counter-store-protocol-design.md(フェーズ37)2節で確定したインターフェース。"""

    def record_generation(
        self,
        internal_id: str,
        *,
        requested_at: datetime,
        venue_matched: bool,
        input_performance_count: int,
    ) -> int:
        """1回の生成リクエストを記録し、記録後のcurrentMonthGenerationCountを返す。"""
        ...

    def get_current_month_count(self, internal_id: str) -> int:
        """currentMonthGenerationCountを読む(generationCountMonthが当月文字列と
        不一致の場合は0を返す、リセット書き込みは行わない)。
        """
        ...


class InMemoryUsageCounterStore:
    """kura-pashaのInMemoryUsageCounterStore・course-set-pashaのInMemoryUsageCounterと
    同じ位置づけの検証用実装。
    """

    def __init__(self) -> None:
        self._known_internal_ids: set[str] = set()
        self._month_by_internal_id: dict[str, str] = {}
        self._count_by_internal_id: dict[str, int] = {}
        self._log_by_internal_id: dict[str, list[GenerationLogEntry]] = {}

    def register(self, internal_id: str) -> None:
        """fan_passドキュメント新規作成時に呼び出される想定(本venture未着手のfan_pass
        ストア実装が担うべき処理を、本モジュールの検証目的のために代替する)。
        """
        self._known_internal_ids.add(internal_id)

    def record_generation(
        self,
        internal_id: str,
        *,
        requested_at: datetime,
        venue_matched: bool,
        input_performance_count: int,
    ) -> int:
        self._ensure_known(internal_id)

        current_month = current_month_jst()
        if self._month_by_internal_id.get(internal_id) != current_month:
            self._month_by_internal_id[internal_id] = current_month
            self._count_by_internal_id[internal_id] = 0

        count_after = self._count_by_internal_id.get(internal_id, 0) + 1
        self._count_by_internal_id[internal_id] = count_after

        self._log_by_internal_id.setdefault(internal_id, []).append(
            GenerationLogEntry(
                requested_at=requested_at,
                venue_matched=venue_matched,
                input_performance_count=input_performance_count,
            )
        )
        return count_after

    def get_current_month_count(self, internal_id: str) -> int:
        self._ensure_known(internal_id)

        if self._month_by_internal_id.get(internal_id) != current_month_jst():
            return 0
        return self._count_by_internal_id.get(internal_id, 0)

    def get_generation_log(self, internal_id: str) -> list[GenerationLogEntry]:
        """テスト側の状態検証用(generation_log追記の確認、kura-pashaのInMemoryUsageCounterStore
        .getと同じ位置づけ)。design.mdには読み取り専用メソッドとして明記されていないため
        UsageCounterStoreProtocol自体には含めない。
        """
        return list(self._log_by_internal_id.get(internal_id, []))

    def _ensure_known(self, internal_id: str) -> None:
        if internal_id not in self._known_internal_ids:
            raise UnknownInternalIdError(
                f"fan_pass document not found for internal_id={internal_id!r}"
            )
