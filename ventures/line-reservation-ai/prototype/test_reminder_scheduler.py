#!/usr/bin/env python3
"""reminder_scheduler.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_reminder_scheduler -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta

from reminder_scheduler import (
    ReminderBooking,
    ReminderConfigError,
    StoreReminderConfig,
    compute_initial_reminder_target,
    select_confirmed_to_archive,
    select_due_initial_reminders,
    select_due_resends,
    should_send_initial_reminder,
)


class ComputeInitialReminderTargetTests(unittest.TestCase):
    def test_default_is_business_end_minus_one_hour(self):
        # 営業時間 9:00-18:00 → デフォルト目標時刻は17:00
        store = StoreReminderConfig(business_hours=(9 * 60, 18 * 60))
        target = compute_initial_reminder_target(date(2026, 8, 10), store)
        self.assertEqual(target, datetime(2026, 8, 9, 17, 0))

    def test_default_is_capped_at_20_00(self):
        # 営業時間 9:00-23:00 → 22:00ではなく20:00が上限
        store = StoreReminderConfig(business_hours=(9 * 60, 23 * 60))
        target = compute_initial_reminder_target(date(2026, 8, 10), store)
        self.assertEqual(target, datetime(2026, 8, 9, 20, 0))

    def test_explicit_reminder_time_overrides_default(self):
        store = StoreReminderConfig(
            business_hours=(9 * 60, 18 * 60), reminder_time_minutes=18 * 60
        )
        target = compute_initial_reminder_target(date(2026, 8, 10), store)
        self.assertEqual(target, datetime(2026, 8, 9, 18, 0))

    def test_closed_previous_day_falls_back_to_prior_business_day(self):
        # 月曜(weekday=0)定休、火曜10:00の予約 → 前日(月)ではなく前営業日(日)に送信
        store = StoreReminderConfig(business_hours=(9 * 60, 18 * 60), closed_weekdays=frozenset({0}))
        tuesday = date(2026, 8, 11)  # 火曜
        self.assertEqual(tuesday.weekday(), 1)
        target = compute_initial_reminder_target(tuesday, store)
        self.assertEqual(target, datetime(2026, 8, 9, 17, 0))  # 日曜17:00

    def test_closed_date_falls_back_to_prior_business_day(self):
        # 前日(月)が臨時休業日として個別登録されている → 前営業日(日)に送信
        store = StoreReminderConfig(
            business_hours=(9 * 60, 18 * 60), closed_dates=frozenset({date(2026, 8, 10)})
        )
        tuesday = date(2026, 8, 11)  # 火曜、前日は月曜(2026-08-10)
        self.assertEqual(tuesday.weekday(), 1)
        target = compute_initial_reminder_target(tuesday, store)
        self.assertEqual(target, datetime(2026, 8, 9, 17, 0))  # 日曜17:00

    def test_closed_weekdays_and_closed_dates_combine(self):
        # 月曜(weekday=0)定休 + 日曜(2026-08-9)を臨時休業日として個別登録 → 土曜まで遡る
        store = StoreReminderConfig(
            business_hours=(9 * 60, 18 * 60),
            closed_weekdays=frozenset({0}),
            closed_dates=frozenset({date(2026, 8, 9)}),
        )
        tuesday = date(2026, 8, 11)  # 火曜
        target = compute_initial_reminder_target(tuesday, store)
        self.assertEqual(target, datetime(2026, 8, 8, 17, 0))  # 土曜17:00

    def test_weekday_specific_business_hours_used_for_target_day(self):
        store = StoreReminderConfig(
            business_hours=(9 * 60, 18 * 60),
            weekday_business_hours={5: [(10 * 60, 15 * 60)]},  # 土曜だけ短縮営業
        )
        sunday = date(2026, 8, 9)  # 日曜の予約 → 前日は土曜
        self.assertEqual((sunday - timedelta(days=1)).weekday(), 5)
        target = compute_initial_reminder_target(sunday, store)
        self.assertEqual(target, datetime(2026, 8, 8, 14, 0))  # 土曜15:00の1時間前

    def test_seven_consecutive_closed_days_raises(self):
        store = StoreReminderConfig(
            business_hours=(9 * 60, 18 * 60),
            closed_weekdays=frozenset({0, 1, 2, 3, 4, 5, 6}),
        )
        with self.assertRaises(ReminderConfigError):
            compute_initial_reminder_target(date(2026, 8, 10), store)


class ShouldSendInitialReminderTests(unittest.TestCase):
    def test_confirmed_before_target_sends(self):
        target = datetime(2026, 8, 9, 17, 0)
        confirmed_at = datetime(2026, 8, 9, 10, 0)
        self.assertTrue(should_send_initial_reminder(target, confirmed_at))

    def test_confirmed_after_target_skips(self):
        # 前日18:00にlast-minuteで確定 → 17:00の目標時刻は既に過ぎている
        target = datetime(2026, 8, 9, 17, 0)
        confirmed_at = datetime(2026, 8, 9, 18, 0)
        self.assertFalse(should_send_initial_reminder(target, confirmed_at))


class SelectDueInitialRemindersTests(unittest.TestCase):
    def setUp(self):
        self.store = StoreReminderConfig(business_hours=(9 * 60, 18 * 60))
        self.stores = {"store-1": self.store}

    def _booking(self, **overrides):
        base = dict(
            booking_id="b1",
            store_id="store-1",
            booking_date=date(2026, 8, 10),
            start_minutes=15 * 60,
            confirmed_at=datetime(2026, 8, 5, 10, 0),
        )
        base.update(overrides)
        return ReminderBooking(**base)

    def test_due_when_target_passed_and_not_yet_sent(self):
        booking = self._booking()
        now = datetime(2026, 8, 9, 17, 30)  # 目標17:00を過ぎている
        due = select_due_initial_reminders([booking], now, self.stores)
        self.assertEqual(due, [booking])

    def test_not_due_before_target(self):
        booking = self._booking()
        now = datetime(2026, 8, 9, 16, 0)  # 目標17:00より前
        due = select_due_initial_reminders([booking], now, self.stores)
        self.assertEqual(due, [])

    def test_scheduler_catch_up_after_missed_run(self):
        # スケジューラが数時間止まっていても、当日を迎えていなければ追いつける
        booking = self._booking()
        now = datetime(2026, 8, 9, 23, 45)
        due = select_due_initial_reminders([booking], now, self.stores)
        self.assertEqual(due, [booking])

    def test_already_sent_is_excluded(self):
        booking = self._booking(reminder_sent_at=datetime(2026, 8, 9, 17, 5))
        now = datetime(2026, 8, 9, 18, 0)
        due = select_due_initial_reminders([booking], now, self.stores)
        self.assertEqual(due, [])

    def test_booking_day_already_reached_is_excluded(self):
        # 予約当日を迎えてしまった場合は前日リマインドの対象外(取りこぼし後の誤送信防止)
        booking = self._booking()
        now = datetime(2026, 8, 10, 8, 0)
        due = select_due_initial_reminders([booking], now, self.stores)
        self.assertEqual(due, [])

    def test_last_minute_confirmation_marks_skipped_not_due(self):
        # 目標時刻(17:00)を過ぎた18:00に確定 → ルール2によりスキップ扱い
        booking = self._booking(confirmed_at=datetime(2026, 8, 9, 18, 0))
        now = datetime(2026, 8, 9, 20, 0)
        due = select_due_initial_reminders([booking], now, self.stores)
        self.assertEqual(due, [])
        self.assertTrue(booking.reminder_skipped)


class SelectDueResendsTests(unittest.TestCase):
    def _booking(self, **overrides):
        base = dict(
            booking_id="b1",
            store_id="store-1",
            booking_date=date(2026, 8, 10),
            start_minutes=15 * 60,  # 15:00
            confirmed_at=datetime(2026, 8, 5, 10, 0),
            reminder_sent_at=datetime(2026, 8, 9, 17, 0),
        )
        base.update(overrides)
        return ReminderBooking(**base)

    def test_due_after_business_open_with_no_reply(self):
        booking = self._booking()
        now = datetime(2026, 8, 10, 9, 5)
        due = select_due_resends([booking], now)
        self.assertEqual(due, [booking])

    def test_not_due_before_business_open(self):
        booking = self._booking()
        now = datetime(2026, 8, 10, 8, 55)
        due = select_due_resends([booking], now)
        self.assertEqual(due, [])

    def test_excluded_when_customer_replied(self):
        booking = self._booking(customer_replied_at=datetime(2026, 8, 9, 19, 0))
        now = datetime(2026, 8, 10, 9, 5)
        due = select_due_resends([booking], now)
        self.assertEqual(due, [])

    def test_excluded_when_already_resent(self):
        booking = self._booking(resend_sent_at=datetime(2026, 8, 10, 9, 5))
        now = datetime(2026, 8, 10, 9, 30)
        due = select_due_resends([booking], now)
        self.assertEqual(due, [])

    def test_excluded_when_initial_reminder_not_sent(self):
        booking = self._booking(reminder_sent_at=None)
        now = datetime(2026, 8, 10, 9, 5)
        due = select_due_resends([booking], now)
        self.assertEqual(due, [])

    def test_excluded_when_booking_is_morning_before_open(self):
        # ルール3: 予約時刻が9:00より前の場合、当日朝の再送は間に合わないため対象外
        booking = self._booking(start_minutes=8 * 60)
        now = datetime(2026, 8, 10, 9, 5)
        due = select_due_resends([booking], now)
        self.assertEqual(due, [])

    def test_excluded_when_not_booking_day(self):
        booking = self._booking()
        now = datetime(2026, 8, 9, 9, 5)
        due = select_due_resends([booking], now)
        self.assertEqual(due, [])


class SelectConfirmedToArchiveTests(unittest.TestCase):
    def _booking(self, **overrides):
        base = dict(
            booking_id="b1",
            store_id="store-1",
            booking_date=date(2026, 8, 10),
            start_minutes=15 * 60,
            confirmed_at=datetime(2026, 8, 5, 10, 0),
        )
        base.update(overrides)
        return ReminderBooking(**base)

    def test_not_yet_due_on_visit_day_itself(self):
        booking = self._booking()
        now = datetime(2026, 8, 10, 20, 0)
        self.assertEqual(select_confirmed_to_archive([booking], now), [])

    def test_due_from_the_calendar_day_after_visit_regardless_of_time_of_day(self):
        # confirmed-state-archival.md準拠: 判定は`now.date() - visit_date`という日付
        # (calendar day)単位の差分であり、時刻は問わない(来店日の翌日早朝でも対象)。
        booking = self._booking()
        now = datetime(2026, 8, 11, 0, 1)
        self.assertEqual(select_confirmed_to_archive([booking], now), [booking])

    def test_due_well_after_visit(self):
        booking = self._booking()
        now = datetime(2026, 9, 1, 0, 0)
        self.assertEqual(select_confirmed_to_archive([booking], now), [booking])

    def test_already_archived_is_excluded(self):
        booking = self._booking(archived_at=datetime(2026, 8, 12, 0, 0))
        now = datetime(2026, 9, 1, 0, 0)
        self.assertEqual(select_confirmed_to_archive([booking], now), [])

    def test_future_booking_is_excluded(self):
        booking = self._booking(booking_date=date(2026, 9, 10))
        now = datetime(2026, 8, 11, 0, 0)
        self.assertEqual(select_confirmed_to_archive([booking], now), [])

    def test_custom_after_visit_days_threshold(self):
        booking = self._booking()
        now = datetime(2026, 8, 12, 0, 0)  # 来店日+2日
        self.assertEqual(select_confirmed_to_archive([booking], now, after_visit_days=3), [])
        self.assertEqual(
            select_confirmed_to_archive([booking], now, after_visit_days=2), [booking]
        )


if __name__ == "__main__":
    unittest.main()
