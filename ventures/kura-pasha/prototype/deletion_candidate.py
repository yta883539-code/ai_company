#!/usr/bin/env python3
"""
stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ232)で設計した、
Stripe解約webhookを起点とする削除候補洗い出しロジックを実行可能なコードに落とし込んだもの。

aircon-pasha/course-set-pashaの同名モジュール(フェーズ123・91)と判定ロジック
(解約日+365日を`deletion_candidate_at`として記録)は同一だが、以下の点が異なる
(design 3節):
- 本venture専用のstaleガード・イベント時刻記録フィールドは持たない。呼び出し元
  (stripe_webhook.py)が既存の`_is_stale_subscription_status_event()`ガードを通過した
  後にのみ本モジュールの関数を呼ぶことで、順序保証に相乗りする。
- 取り消しトリガーは`customer.subscription.created`/`updated`ではなく
  `checkout.session.completed`(本ventureで`subscription_status`を`"active"`へ
  実際に書き込む唯一の箇所)。
- `WorkshopStoreProtocol`(usage_counter_workshop.py)の既存ストアに直接
  `get_deletion_candidate_at`/`set_deletion_candidate_at`/`clear_deletion_candidate_at`
  を追加した(aircon-pasha/course-set-pashaのような専用の軽量Protocol・専用InMemory
  ストアを別途新設していない)。

設計の参照元: stripe-cancellation-deletion-candidate-trigger-design.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Protocol

# design 2節: 解約日から削除候補化までの猶予期間(data-retention-policy.mdの保存期間ポリシー)
RETENTION_DAYS = 365
_DELETION_CANDIDATE_DELAY = timedelta(days=RETENTION_DAYS)


class DeletionCandidateWorkshopStoreProtocol(Protocol):
    """本モジュールが必要とする最小のインターフェース(design 4節)。
    usage_counter_workshop.WorkshopStoreProtocol/InMemoryWorkshopStoreは
    構造的にこれを満たす。"""

    def get_deletion_candidate_at(self, workshop_id: str) -> datetime | None: ...

    def set_deletion_candidate_at(self, workshop_id: str, deletion_candidate_at: datetime) -> None: ...

    def clear_deletion_candidate_at(self, workshop_id: str) -> None: ...

    def all_workshop_ids(self) -> list[str]: ...


def mark_deletion_candidate_on_subscription_deleted(
    workshop_store: DeletionCandidateWorkshopStoreProtocol,
    workshop_id: str,
    event_time: datetime,
) -> datetime:
    """design 4節: `customer.subscription.deleted`受信時、呼び出し元が
    `_is_stale_subscription_status_event()`を通過して`subscription_status`を
    `"canceled"`へ実際に更新した場合にのみ呼ぶ。`event_time + 365日`を
    `deletion_candidate_at`として書き込み、書き込んだ値を返す(既に設定済みの場合も
    最新の解約日を基準に上書きする、他ventureと同じ「安全側」判断)。
    """
    deletion_candidate_at = event_time + _DELETION_CANDIDATE_DELAY
    workshop_store.set_deletion_candidate_at(workshop_id, deletion_candidate_at)
    return deletion_candidate_at


def clear_deletion_candidate_on_subscription_reactivated(
    workshop_store: DeletionCandidateWorkshopStoreProtocol,
    workshop_id: str,
) -> bool:
    """design 4節: `checkout.session.completed`受信時、呼び出し元が
    `subscription_status`を`"active"`へ実際に更新した場合にのみ呼ぶ。
    `deletion_candidate_at`が設定済みなら削除してTrueを返す。未設定ならFalse
    (冪等。初回契約時に呼ばれても実害はない)。
    """
    if workshop_store.get_deletion_candidate_at(workshop_id) is None:
        return False
    workshop_store.clear_deletion_candidate_at(workshop_id)
    return True


def list_deletion_candidates(
    workshop_store: DeletionCandidateWorkshopStoreProtocol,
    now: datetime,
) -> List[str]:
    """design 4節: `deletion_candidate_at`が`now`以前に設定されているworkshop_idの
    一覧を返す(読み出し専用、削除・通知は行わない)。data-retention-policy.md
    「削除候補化後の最終確認」節の配線からの呼び出しを想定するが、本フェーズでは
    その配線自体は次回候補として残す。
    """
    candidates = []
    for workshop_id in workshop_store.all_workshop_ids():
        deletion_candidate_at = workshop_store.get_deletion_candidate_at(workshop_id)
        if deletion_candidate_at is not None and deletion_candidate_at <= now:
            candidates.append(workshop_id)
    return candidates
