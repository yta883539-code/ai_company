#!/usr/bin/env python3
"""dunning_notification_scheduler.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_dunning_notification_scheduler -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime

from dunning_notification_scheduler import (
    DUNNING_CONFIG_A_7DAYS,
    DUNNING_CONFIG_B_14DAYS,
    DunningConfig,
    compute_dunning_schedule,
    render_dunning_message,
    render_recovery_message,
)


class ComputeDunningScheduleTests(unittest.TestCase):
    def test_config_a_produces_detected_reminder_suspended(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)
        self.assertEqual([e.event_type for e in events], ["detected", "reminder", "suspended"])
        self.assertEqual(events[1].label, "final")
        self.assertEqual(events[1].scheduled_at, datetime(2026, 8, 21, 10, 0))  # 検知から4日後
        self.assertEqual(events[2].scheduled_at, datetime(2026, 8, 24, 10, 0))  # 検知から7日後

    def test_config_b_produces_midpoint_and_final_reminders(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)
        self.assertEqual(
            [e.event_type for e in events], ["detected", "reminder", "reminder", "suspended"]
        )
        self.assertEqual([e.label for e in events if e.event_type == "reminder"], ["midpoint", "final"])
        self.assertEqual(events[1].scheduled_at, datetime(2026, 8, 24, 10, 0))  # 検知から7日後
        self.assertEqual(events[2].scheduled_at, datetime(2026, 8, 28, 10, 0))  # 検知から11日後
        self.assertEqual(events[3].scheduled_at, datetime(2026, 8, 31, 10, 0))  # 検知から14日後

    def test_reminder_offsets_must_precede_grace_period(self):
        with self.assertRaises(ValueError):
            DunningConfig(name="invalid", grace_period_days=7, reminder_offsets=(7,))

    def test_reminder_offsets_must_be_ascending(self):
        with self.assertRaises(ValueError):
            DunningConfig(name="invalid", grace_period_days=14, reminder_offsets=(11, 7))

    def test_reminder_offsets_must_not_be_empty(self):
        with self.assertRaises(ValueError):
            DunningConfig(name="invalid", grace_period_days=7, reminder_offsets=())


class RenderDunningMessageTests(unittest.TestCase):
    URL = "https://example.com/billing"

    def test_detected_message_uses_config_grace_period(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)[0]
        text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL)
        self.assertIn("7日以内にお支払い方法", text)
        self.assertIn(self.URL, text)

    def test_detected_message_reflects_14day_config(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)[0]
        text = render_dunning_message(event, DUNNING_CONFIG_B_14DAYS, self.URL)
        self.assertIn("14日以内にお支払い方法", text)

    def test_config_a_final_reminder_says_3_days(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)[1]
        text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL)
        self.assertIn("このままですと3日後に新規のご予約受付", text)

    def test_config_b_final_reminder_also_says_3_days(self):
        # 11日後(終了3日前)に送るリマインドなので、猶予期間が14日でも文言は「3日後」のまま。
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)
        final_reminder = next(e for e in events if e.event_type == "reminder" and e.label == "final")
        text = render_dunning_message(final_reminder, DUNNING_CONFIG_B_14DAYS, self.URL)
        self.assertIn("このままですと3日後に新規のご予約受付", text)

    def test_config_b_midpoint_reminder_shows_elapsed_and_remaining_days(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)
        midpoint = next(e for e in events if e.event_type == "reminder" and e.label == "midpoint")
        text = render_dunning_message(midpoint, DUNNING_CONFIG_B_14DAYS, self.URL)
        self.assertIn("検知から7日が経過", text)
        self.assertIn("猶予期間は残り7日", text)

    def test_config_a_has_no_midpoint_reminder(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)
        labels = [e.label for e in events if e.event_type == "reminder"]
        self.assertNotIn("midpoint", labels)

    def test_suspended_message_is_config_independent(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event_a = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)[-1]
        event_b = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)[-1]
        self.assertEqual(
            render_dunning_message(event_a, DUNNING_CONFIG_A_7DAYS, self.URL),
            render_dunning_message(event_b, DUNNING_CONFIG_B_14DAYS, self.URL),
        )

    def test_recovery_message_has_no_placeholders_and_takes_no_config(self):
        text = render_recovery_message()
        self.assertNotIn("{", text)
        self.assertIn("お支払いを確認しました", text)


if __name__ == "__main__":
    unittest.main()
