#!/usr/bin/env python3
"""member_user_profile_deletion_candidate.pyの単体テスト。
member-user-profile-deletion-candidate-design.md(フェーズ続き341)の削除候補洗い出し
ロジックの仕様に沿った挙動を確認する(test_deletion_candidate.pyのuser_profile版)。"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from member_user_profile_deletion_candidate import (  # noqa: E402
    RETENTION_DAYS,
    list_member_deletion_candidates,
)
from usage_counter_workshop import InMemoryUserProfileStore  # noqa: E402

_UNLINKED_AT = datetime(2026, 10, 13, 12, 0, 0)


class ListMemberDeletionCandidatesTest(unittest.TestCase):
    def test_returns_users_whose_unlinked_at_plus_retention_days_has_passed(self):
        store = InMemoryUserProfileStore()
        store.link("U1", "W1")
        store.unlink("U1", unlinked_at=_UNLINKED_AT)
        now = _UNLINKED_AT + timedelta(days=RETENTION_DAYS, seconds=1)
        self.assertEqual(list_member_deletion_candidates(store, now), ["U1"])

    def test_excludes_users_not_yet_due(self):
        store = InMemoryUserProfileStore()
        store.link("U1", "W1")
        store.unlink("U1", unlinked_at=_UNLINKED_AT)
        now = _UNLINKED_AT + timedelta(days=RETENTION_DAYS - 1)
        self.assertEqual(list_member_deletion_candidates(store, now), [])

    def test_excludes_users_never_unlinked(self):
        store = InMemoryUserProfileStore()
        store.link("U1", "W1")
        now = _UNLINKED_AT + timedelta(days=RETENTION_DAYS + 1)
        self.assertEqual(list_member_deletion_candidates(store, now), [])

    def test_excludes_users_unlinked_without_a_timestamp(self):
        # unlink()をunlinked_at省略で呼んだ場合は削除候補一覧に乗らない
        # (all_unlinked_user_idsにも含まれない、usage_counter_workshop.py参照)。
        store = InMemoryUserProfileStore()
        store.link("U1", "W1")
        store.unlink("U1")
        now = _UNLINKED_AT + timedelta(days=RETENTION_DAYS + 1)
        self.assertEqual(list_member_deletion_candidates(store, now), [])

    def test_excludes_users_relinked_after_unlink(self):
        # 削除候補化前に別workshopへ再参加した場合はunlinked_atがクリアされ、
        # 以後候補から外れる(InMemoryUserProfileStore.link参照)。
        store = InMemoryUserProfileStore()
        store.link("U1", "W1")
        store.unlink("U1", unlinked_at=_UNLINKED_AT)
        store.link("U1", "W2")
        now = _UNLINKED_AT + timedelta(days=RETENTION_DAYS + 1)
        self.assertEqual(list_member_deletion_candidates(store, now), [])

    def test_does_not_affect_other_users(self):
        store = InMemoryUserProfileStore()
        store.link("U1", "W1")
        store.unlink("U1", unlinked_at=_UNLINKED_AT)
        now = _UNLINKED_AT + timedelta(days=RETENTION_DAYS + 1)
        self.assertNotIn("U2", list_member_deletion_candidates(store, now))


if __name__ == "__main__":
    unittest.main()
