#!/usr/bin/env python3
import unittest
from datetime import datetime, timedelta

from trial_end_scheduler import (
    StoreTrialState,
    is_trial_end_report_due,
    select_due_trial_end_reports,
)

NOW = datetime(2026, 9, 1, 19, 0, 0)


def make_state(**overrides):
    defaults = dict(
        store_id="store-1",
        trial_start_at=NOW - timedelta(days=20),
        trial_end_report_sent_at=None,
        booking_count=3,
    )
    defaults.update(overrides)
    return StoreTrialState(**defaults)


class StoreTrialStateTest(unittest.TestCase):
    def test_rejects_negative_booking_count(self):
        with self.assertRaises(ValueError):
            make_state(booking_count=-1)


class IsTrialEndReportDueTest(unittest.TestCase):
    def test_not_due_when_trial_not_started(self):
        state = make_state(trial_start_at=None)
        self.assertFalse(is_trial_end_report_due(state, NOW))

    def test_not_due_when_already_sent(self):
        state = make_state(trial_end_report_sent_at=NOW - timedelta(days=1))
        self.assertFalse(is_trial_end_report_due(state, NOW))

    def test_due_by_period_condition(self):
        state = make_state(trial_start_at=NOW - timedelta(days=14), booking_count=0)
        self.assertTrue(is_trial_end_report_due(state, NOW))

    def test_not_due_just_before_period(self):
        state = make_state(
            trial_start_at=NOW - timedelta(days=14) + timedelta(minutes=1), booking_count=0
        )
        self.assertFalse(is_trial_end_report_due(state, NOW))

    def test_due_by_booking_threshold_even_within_period(self):
        state = make_state(trial_start_at=NOW - timedelta(days=1), booking_count=20)
        self.assertTrue(is_trial_end_report_due(state, NOW))

    def test_not_due_below_booking_threshold(self):
        state = make_state(trial_start_at=NOW - timedelta(days=1), booking_count=19)
        self.assertFalse(is_trial_end_report_due(state, NOW))

    def test_custom_thresholds(self):
        state = make_state(trial_start_at=NOW - timedelta(days=6), booking_count=4)
        self.assertTrue(
            is_trial_end_report_due(state, NOW, trial_period_days=30, trial_booking_threshold=4)
        )
        self.assertFalse(
            is_trial_end_report_due(state, NOW, trial_period_days=30, trial_booking_threshold=5)
        )


class SelectDueTrialEndReportsTest(unittest.TestCase):
    def test_selects_only_due_stores(self):
        due_by_period = make_state(store_id="a", trial_start_at=NOW - timedelta(days=14))
        due_by_count = make_state(
            store_id="b", trial_start_at=NOW - timedelta(days=1), booking_count=20
        )
        not_due = make_state(store_id="c", trial_start_at=NOW - timedelta(days=1))
        already_sent = make_state(
            store_id="d",
            trial_start_at=NOW - timedelta(days=30),
            trial_end_report_sent_at=NOW - timedelta(days=10),
            booking_count=50,
        )
        result = select_due_trial_end_reports(
            [due_by_period, due_by_count, not_due, already_sent], NOW
        )
        self.assertEqual({state.store_id for state in result}, {"a", "b"})

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(select_due_trial_end_reports([], NOW), [])


if __name__ == "__main__":
    unittest.main()
