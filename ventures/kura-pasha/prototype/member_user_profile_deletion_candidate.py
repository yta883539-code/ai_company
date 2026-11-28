#!/usr/bin/env python3
"""
member-user-profile-deletion-candidate-design.md(フェーズ続き341)で設計した、
複数職人プランの縮小によって除外された非契約者メンバー(user_profile)の削除候補化
洗い出しロジックを実行可能なコードに落とし込んだもの。

deletion_candidate.py(workshop単位、Stripe解約起点)と対になる、user_profile単位
(`check_and_apply_pending_member_reduction`によるworkshop_id null化起点)の版。
判定ロジック(基準時刻+365日を`deletion_candidate_at`とみなす)・保留期間は
deletion_candidate.pyのRETENTION_DAYSをそのまま再利用し、独自の定数は持たない。

本モジュールは`unlink(user_id, unlinked_at=...)`が既に記録した`unlinked_at`を
読み出すだけの読み出し専用ロジックであり、`unlinked_at`自体の書き込み
(usage_counter_workshop.check_and_apply_pending_member_reduction側の責務)には
関与しない。

設計の参照元: member-user-profile-deletion-candidate-design.md
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Protocol

from deletion_candidate import RETENTION_DAYS, _DELETION_CANDIDATE_DELAY


class DeletionCandidateUserProfileStoreProtocol(Protocol):
    """本モジュールが必要とする最小のインターフェース(design 3節)。
    usage_counter_workshop.UserProfileStoreProtocol/InMemoryUserProfileStoreは
    構造的にこれを満たす。"""

    def get_unlinked_at(self, user_id: str) -> datetime | None: ...

    def all_unlinked_user_ids(self) -> list[str]: ...


def list_member_deletion_candidates(
    user_profile_store: DeletionCandidateUserProfileStoreProtocol,
    now: datetime,
) -> List[str]:
    """design 3節: `unlinked_at + 365日`(RETENTION_DAYS、deletion_candidate.pyと
    共通)が`now`以前になっているuser_idの一覧を返す(読み出し専用、削除・通知は
    行わない)。deletion_candidate.list_deletion_candidates()のuser_profile版。

    `all_unlinked_user_ids()`が返すのは「一度unlinked_at付きでunlinkされたuser_id」
    のみであり、未リンクのまま一度もworkshopに参加していないuser_idや、再リンクで
    unlinked_atがクリアされたuser_id(InMemoryUserProfileStore.link参照)はそもそも
    含まれないため、本関数側で別途「再リンク済みでないか」を確認する必要はない。
    """
    candidates = []
    for user_id in user_profile_store.all_unlinked_user_ids():
        unlinked_at = user_profile_store.get_unlinked_at(user_id)
        if unlinked_at is not None and unlinked_at + _DELETION_CANDIDATE_DELAY <= now:
            candidates.append(user_id)
    return candidates


__all__ = ["RETENTION_DAYS", "list_member_deletion_candidates"]
