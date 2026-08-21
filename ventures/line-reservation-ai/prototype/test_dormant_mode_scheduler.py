#!/usr/bin/env python3
"""dormant_mode_scheduler.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_dormant_mode_scheduler -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from dormant_mode_scheduler import (
    GRACE_PERIOD_DAYS,
    RENOTIFY_OFFSETS_DAYS,
    compute_dormant_schedule,
    render_dormant_message,
    render_dormant_recovery_message,
)


class ComputeDormantScheduleTests(unittest.TestCase):
    def test_transition_is_grace_period_after_report(self):
        report_sent_at = datetime(2026, 8, 21, 9, 0)
        events = compute_dormant_schedule(report_sent_at)
        self.assertEqual(events[0].event_type, "transitioned")
        self.assertEqual(events[0].scheduled_at, datetime(2026, 8, 24, 9, 0))  # 3日後
        self.assertEqual(GRACE_PERIOD_DAYS, 3)

    def test_renotify_offsets_are_relative_to_transition_not_report(self):
        report_sent_at = datetime(2026, 8, 21, 9, 0)
        events = compute_dormant_schedule(report_sent_at)
        transitioned_at = events[0].scheduled_at
        renotify_events = events[1:]
        self.assertEqual([e.label for e in renotify_events], ["2nd", "3rd", "final"])
        self.assertEqual(RENOTIFY_OFFSETS_DAYS, (7, 30, 90))
        for event, offset in zip(renotify_events, RENOTIFY_OFFSETS_DAYS):
            self.assertEqual(event.event_type, "renotify")
            self.assertEqual(event.scheduled_at - transitioned_at, timedelta(days=offset))

    def test_schedule_has_four_events_total(self):
        events = compute_dormant_schedule(datetime(2026, 1, 1, 0, 0))
        self.assertEqual(len(events), 4)


class RenderDormantMessageTests(unittest.TestCase):
    def setUp(self):
        self.events = compute_dormant_schedule(datetime(2026, 8, 21, 9, 0))

    def test_transitioned_message_mentions_new_booking_stop_and_data_retained(self):
        text = render_dormant_message(self.events[0], "https://pay.example.com/store1")
        self.assertIn("休止モードへ移行しました", text)
        self.assertIn("新規のご予約受付を停止しました", text)
        self.assertIn("データは削除されません", text)
        self.assertIn("https://pay.example.com/store1", text)

    def test_2nd_renotify_message(self):
        text = render_dormant_message(self.events[1], "https://pay.example.com/store1")
        self.assertIn("1週間が経過しました", text)

    def test_3rd_renotify_message(self):
        text = render_dormant_message(self.events[2], "https://pay.example.com/store1")
        self.assertIn("1か月が経過しました", text)
        self.assertIn("30日経過", text)

    def test_final_renotify_message_states_no_more_notifications(self):
        text = render_dormant_message(self.events[3], "https://pay.example.com/store1")
        self.assertIn("3か月が経過しました", text)
        self.assertIn("お送りしません", text)

    def test_unknown_event_raises(self):
        from dormant_mode_scheduler import DormantEvent

        bogus = DormantEvent(event_type="unknown", scheduled_at=datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            render_dormant_message(bogus, "https://pay.example.com/store1")

    def test_formal_tone_avoids_casual_endings(self):
        text = render_dormant_message(self.events[0], "https://pay.example.com/store1", tone="formal")
        self.assertIn("移行いたしました", text)
        self.assertNotIn("!", text)

    def test_casual_tone_allows_exclamation_and_emoji(self):
        text = render_dormant_message(self.events[0], "https://pay.example.com/store1", tone="casual")
        self.assertIn("!", text)
        self.assertIn("🙆", text)

    def test_unknown_tone_falls_back_to_standard(self):
        standard_text = render_dormant_message(self.events[0], "https://pay.example.com/store1", tone="standard")
        fallback_text = render_dormant_message(self.events[0], "https://pay.example.com/store1", tone="nonexistent")
        self.assertEqual(standard_text, fallback_text)


class RenderDormantRecoveryMessageTests(unittest.TestCase):
    def test_recovery_message_mentions_resume_and_next_billing_date(self):
        text = render_dormant_recovery_message("2026-09-24", "https://pay.example.com/store1")
        self.assertIn("新規予約受付を再開しました", text)
        self.assertIn("2026-09-24", text)
        self.assertIn("休止期間中に確定していたご予約", text)

    def test_recovery_message_differs_from_first_time_registration_message(self):
        text = render_dormant_recovery_message("2026-09-24", "https://pay.example.com/store1")
        self.assertNotIn("正式にご利用いただけます", text)  # billing-upgrade-flow-design.md 3節の文言とは異なる

    def test_recovery_message_formal_tone(self):
        text = render_dormant_recovery_message("2026-09-24", "https://pay.example.com/store1", tone="formal")
        self.assertIn("再開いたしました", text)


if __name__ == "__main__":
    unittest.main()
