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
    DormantScheduleState,
    compute_dormant_schedule,
    render_dormant_message,
    render_dormant_recovery_message,
    select_due_dormant_events,
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


class SelectDueDormantEventsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 28, 4, 0)
        self.report_sent_at = datetime(2026, 8, 21, 9, 0)  # + 3日 = 8/24 9:00

    def test_transition_due_after_grace_period_with_no_subscription(self):
        state = DormantScheduleState(
            store_id="s1", trial_end_report_sent_at=self.report_sent_at
        )
        due = select_due_dormant_events([state], self.now)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].event.event_type, "transitioned")

    def test_transition_not_yet_due_within_grace_period(self):
        state = DormantScheduleState(
            store_id="s1", trial_end_report_sent_at=datetime(2026, 8, 27, 9, 0)
        )
        due = select_due_dormant_events([state], self.now)
        self.assertEqual(due, [])

    def test_no_report_sent_yet_is_not_due(self):
        state = DormantScheduleState(store_id="s1", trial_end_report_sent_at=None)
        due = select_due_dormant_events([state], self.now)
        self.assertEqual(due, [])

    def test_subscription_completed_during_grace_period_skips_transition(self):
        # 猶予期間中にプラン選択が完了(stripe_customer_id設定済み)。
        # 1通目未送信のため休止モード自体に入らない。
        state = DormantScheduleState(
            store_id="s1",
            trial_end_report_sent_at=self.report_sent_at,
            stripe_customer_id="cus_123",
        )
        due = select_due_dormant_events([state], self.now)
        self.assertEqual(due, [])

    def test_payment_failed_reason_is_out_of_scope(self):
        # 決済失敗からの猶予期間・制限モードはdunning_notification_scheduler.pyの担当。
        state = DormantScheduleState(
            store_id="s1",
            trial_end_report_sent_at=self.report_sent_at,
            suspension_reason="payment_failed",
        )
        due = select_due_dormant_events([state], self.now)
        self.assertEqual(due, [])

    def test_2nd_renotify_due_after_transition_plus_7_days(self):
        transitioned_at = self.report_sent_at + timedelta(days=GRACE_PERIOD_DAYS)
        state = DormantScheduleState(
            store_id="s1",
            trial_end_report_sent_at=self.report_sent_at,
            suspension_reason="trial_unselected",
            dormant_transitioned_at=transitioned_at,
            dormant_renotify_count=0,
        )
        now = transitioned_at + timedelta(days=7)
        due = select_due_dormant_events([state], now)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0].event.label, "2nd")

    def test_recovered_after_transition_stops_renotify(self):
        # cloud_function_subscription_activated_webhook.py経由でsuspension_reasonが
        # 解除(Noneへ)された場合、以降のrenotifyは送らない。
        transitioned_at = self.report_sent_at + timedelta(days=GRACE_PERIOD_DAYS)
        state = DormantScheduleState(
            store_id="s1",
            trial_end_report_sent_at=self.report_sent_at,
            suspension_reason=None,
            stripe_customer_id="cus_123",
            dormant_transitioned_at=transitioned_at,
            dormant_renotify_count=0,
        )
        now = transitioned_at + timedelta(days=90)
        due = select_due_dormant_events([state], now)
        self.assertEqual(due, [])

    def test_stops_after_final_notification(self):
        transitioned_at = self.report_sent_at + timedelta(days=GRACE_PERIOD_DAYS)
        state = DormantScheduleState(
            store_id="s1",
            trial_end_report_sent_at=self.report_sent_at,
            suspension_reason="trial_unselected",
            dormant_transitioned_at=transitioned_at,
            dormant_renotify_count=3,  # 2nd/3rd/finalすべて送信済み
        )
        now = transitioned_at + timedelta(days=365)
        due = select_due_dormant_events([state], now)
        self.assertEqual(due, [])

    def test_multiple_stores_only_returns_due_ones(self):
        due_state = DormantScheduleState(
            store_id="s1", trial_end_report_sent_at=self.report_sent_at
        )
        not_due_state = DormantScheduleState(
            store_id="s2", trial_end_report_sent_at=datetime(2026, 8, 27, 9, 0)
        )
        due = select_due_dormant_events([due_state, not_due_state], self.now)
        self.assertEqual([d.state.store_id for d in due], ["s1"])


if __name__ == "__main__":
    unittest.main()
