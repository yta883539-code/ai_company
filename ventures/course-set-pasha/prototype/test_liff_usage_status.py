#!/usr/bin/env python3
"""liff_usage_status.pyのテスト。liff-plan-selection-ui-wireframe.mdの「現在のご利用状況」
欄の出し分けを検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trial_end_scheduler import (  # noqa: E402
    DEFAULT_TRIAL_PERIOD_DAYS,
    TRIAL_GENERATION_LIMIT,
)
from liff_usage_status import (  # noqa: E402
    PaidUsageStatus,
    TrialUsageStatus,
    format_usage_status_line,
    get_current_usage_status,
)


class _FakeProfileStore:
    def __init__(self, plan=None) -> None:
        self._plan = plan

    def get_plan(self, user_id: str):
        return self._plan


class _FakeUsageCounter:
    def __init__(
        self,
        trial_start_at=None,
        trial_generation_count: int = 0,
        monthly_count: int = 0,
    ) -> None:
        self._trial_start_at = trial_start_at
        self._trial_generation_count = trial_generation_count
        self._monthly_count = monthly_count

    def get_trial_start_at(self, user_id: str):
        return self._trial_start_at

    def get_trial_generation_count(self, user_id: str) -> int:
        return self._trial_generation_count

    def get_count(self, user_id: str, month: str) -> int:
        return self._monthly_count


class GetCurrentUsageStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 9, 5, 12, 0, 0)

    def test_paid_plan_returns_plan_and_monthly_count(self) -> None:
        status = get_current_usage_status(
            "u1",
            _FakeProfileStore(plan="スタンダード"),
            _FakeUsageCounter(monthly_count=4),
            self.now,
            "2026-09",
        )
        self.assertEqual(
            status, PaidUsageStatus(plan="スタンダード", monthly_count=4, monthly_limit=15)
        )

    def test_trial_not_yet_started_returns_full_allowance(self) -> None:
        # trial-start-anchor-decision.md: 初回生成成功前はtrial_start_at未設定。
        status = get_current_usage_status(
            "u1", _FakeProfileStore(plan=None), _FakeUsageCounter(), self.now, "2026-09"
        )
        self.assertEqual(
            status,
            TrialUsageStatus(
                remaining_generations=TRIAL_GENERATION_LIMIT,
                remaining_days=DEFAULT_TRIAL_PERIOD_DAYS,
            ),
        )

    def test_trial_in_progress_subtracts_used_count_and_elapsed_days(self) -> None:
        status = get_current_usage_status(
            "u1",
            _FakeProfileStore(plan=None),
            _FakeUsageCounter(
                trial_start_at=self.now - timedelta(days=6), trial_generation_count=2
            ),
            self.now,
            "2026-09",
        )
        self.assertEqual(
            status,
            TrialUsageStatus(
                remaining_generations=TRIAL_GENERATION_LIMIT - 2,
                remaining_days=DEFAULT_TRIAL_PERIOD_DAYS - 6,
            ),
        )

    def test_trial_usage_clamped_to_zero_when_over_limit(self) -> None:
        status = get_current_usage_status(
            "u1",
            _FakeProfileStore(plan=None),
            _FakeUsageCounter(
                trial_start_at=self.now - timedelta(days=30),
                trial_generation_count=TRIAL_GENERATION_LIMIT + 3,
            ),
            self.now,
            "2026-09",
        )
        self.assertEqual(
            status, TrialUsageStatus(remaining_generations=0, remaining_days=0)
        )


class FormatUsageStatusLineTest(unittest.TestCase):
    def test_paid_plan_line(self) -> None:
        self.assertEqual(
            format_usage_status_line(
                PaidUsageStatus(plan="ライト", monthly_count=1, monthly_limit=8)
            ),
            "現在のプラン: ライト",
        )

    def test_trial_line_matches_wireframe_text(self) -> None:
        self.assertEqual(
            format_usage_status_line(
                TrialUsageStatus(remaining_generations=3, remaining_days=14)
            ),
            "トライアル残り: 3回 / 14日",
        )


if __name__ == "__main__":
    unittest.main()
