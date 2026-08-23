#!/usr/bin/env python3
"""trial_end_scheduler.pyのテスト。trial-end-scheduler-design.md 3節の抽出条件を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trial_end_scheduler import (  # noqa: E402
    DEFAULT_TRIAL_PERIOD_DAYS,
    TrialUserState,
    select_due_trial_end_notifications,
)


class SelectDueTrialEndNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 23, 4, 0, 0)

    def test_exactly_14_days_elapsed_is_due(self) -> None:
        user = TrialUserState(
            user_id="u1", trial_start_at=self.now - timedelta(days=DEFAULT_TRIAL_PERIOD_DAYS)
        )
        self.assertEqual(select_due_trial_end_notifications([user], self.now), [user])

    def test_more_than_14_days_elapsed_is_due(self) -> None:
        # スケジューラの遅延・欠落を想定し、超過分でも「以上」で拾えることを確認する。
        user = TrialUserState(user_id="u1", trial_start_at=self.now - timedelta(days=30))
        self.assertEqual(select_due_trial_end_notifications([user], self.now), [user])

    def test_13_days_elapsed_is_not_due(self) -> None:
        user = TrialUserState(user_id="u1", trial_start_at=self.now - timedelta(days=13))
        self.assertEqual(select_due_trial_end_notifications([user], self.now), [])

    def test_trial_start_at_unset_is_not_due(self) -> None:
        user = TrialUserState(user_id="u1", trial_start_at=None)
        self.assertEqual(select_due_trial_end_notifications([user], self.now), [])

    def test_already_notified_is_not_due(self) -> None:
        user = TrialUserState(
            user_id="u1",
            trial_start_at=self.now - timedelta(days=20),
            trial_end_notified_at=self.now - timedelta(days=1),
        )
        self.assertEqual(select_due_trial_end_notifications([user], self.now), [])

    def test_already_upgraded_is_not_due(self) -> None:
        user = TrialUserState(
            user_id="u1",
            trial_start_at=self.now - timedelta(days=20),
            upgraded_at=self.now - timedelta(days=2),
        )
        self.assertEqual(select_due_trial_end_notifications([user], self.now), [])

    def test_custom_trial_period_days(self) -> None:
        user = TrialUserState(user_id="u1", trial_start_at=self.now - timedelta(days=7))
        self.assertEqual(
            select_due_trial_end_notifications([user], self.now, trial_period_days=7), [user]
        )
        self.assertEqual(
            select_due_trial_end_notifications([user], self.now, trial_period_days=8), []
        )

    def test_preserves_input_order_and_only_due_users(self) -> None:
        due_1 = TrialUserState(user_id="due-1", trial_start_at=self.now - timedelta(days=14))
        not_due = TrialUserState(user_id="not-due", trial_start_at=self.now - timedelta(days=1))
        due_2 = TrialUserState(user_id="due-2", trial_start_at=self.now - timedelta(days=15))
        result = select_due_trial_end_notifications([due_1, not_due, due_2], self.now)
        self.assertEqual([u.user_id for u in result], ["due-1", "due-2"])


if __name__ == "__main__":
    unittest.main()
