#!/usr/bin/env python3
"""trial-end-condition-design.md(フェーズ118)で設計した無料トライアル終了判定を
純粋関数として実装する。pricing-plan.md「無料トライアル条件(仮)」の「生成5回到達、
または初回生成から30日、いずれか早い方」をそのまま判定する(due_date_logic.py等と同じ
pure stdlib方針、実LLM呼び出し・外部サービス接続は行わない)。
"""

from datetime import datetime, timedelta

TRIAL_PERIOD_DAYS = 30  # pricing-plan.md「無料トライアル条件(仮)」確定値
TRIAL_GENERATION_LIMIT = 5  # 同上、course-set-pashaと同じ基準


class FleetOperatorStoreProtocol:
    """fleet_operatorドキュメントのトライアル関連フィールドの読み書きを模したProtocol
    (trial-end-condition-design.md「3. 追加フィールド」「6. 今後の課題」)。実際のFirestore
    接続は未実装で、本venture内ではInMemoryFleetOperatorStoreのみを実装として用意する。
    """

    def get_trial_start_at(self, internal_id: str) -> "datetime | None":
        raise NotImplementedError

    def set_trial_start_at(self, internal_id: str, value: datetime) -> None:
        """既に設定済みの場合は上書きしない(firestore-data-model.mdの設計通り、
        初回生成時に1回だけ設定・以降不変)。"""
        raise NotImplementedError

    def get_trial_generation_count(self, internal_id: str) -> int:
        raise NotImplementedError

    def increment_trial_generation_count(self, internal_id: str) -> "tuple[int, int]":
        """1回分の生成を加算し、(加算前カウント, 加算後カウント)を返す。"""
        raise NotImplementedError


class InMemoryFleetOperatorStore(FleetOperatorStoreProtocol):
    """fleet_operatorドキュメントのトライアル関連フィールドを模したInMemory実装
    (Firestore接続は未実装のまま)。"""

    def __init__(self) -> None:
        self._trial_start_at: "dict[str, datetime]" = {}
        self._trial_generation_count: "dict[str, int]" = {}

    def get_trial_start_at(self, internal_id: str) -> "datetime | None":
        return self._trial_start_at.get(internal_id)

    def set_trial_start_at(self, internal_id: str, value: datetime) -> None:
        if internal_id in self._trial_start_at:
            return
        self._trial_start_at[internal_id] = value

    def get_trial_generation_count(self, internal_id: str) -> int:
        return self._trial_generation_count.get(internal_id, 0)

    def increment_trial_generation_count(self, internal_id: str) -> "tuple[int, int]":
        before = self._trial_generation_count.get(internal_id, 0)
        after = before + 1
        self._trial_generation_count[internal_id] = after
        return before, after


def is_trial_period_over(
    internal_id: str,
    now: datetime,
    operator_store: FleetOperatorStoreProtocol,
) -> bool:
    """trial-end-condition-design.md 4節: 「生成5回到達、または初回生成から30日、
    いずれか早い方」の論理和。trialStartAtが未設定(初回生成前)の場合は常にトライアル中。
    """
    trial_start_at = operator_store.get_trial_start_at(internal_id)
    if trial_start_at is None:
        return False
    if operator_store.get_trial_generation_count(internal_id) >= TRIAL_GENERATION_LIMIT:
        return True
    return now >= trial_start_at + timedelta(days=TRIAL_PERIOD_DAYS)


def record_generation_for_trial(
    operator_store: FleetOperatorStoreProtocol, internal_id: str, now: datetime
) -> None:
    """生成成功時の呼び出し側配線(design 6節「今後の課題」1点目)。初回生成時に
    trialStartAtを設定し(2回目以降は既存値を保持)、trialGenerationCountを1加算する。
    呼び出し順序はtrialStartAt設定を先に行う(カウント加算前に起点が必ず存在する状態にする)。
    """
    operator_store.set_trial_start_at(internal_id, now)
    operator_store.increment_trial_generation_count(internal_id)
