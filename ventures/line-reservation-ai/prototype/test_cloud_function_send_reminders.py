#!/usr/bin/env python3
"""prototype/cloud_function_send_reminders.py の自動テストスイート(unittest、外部ライブラリ非依存)。

実行方法: python3 -m unittest test_cloud_function_send_reminders -v
          (prototype/ディレクトリで実行)
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402
from cloud_function_send_reminders import send_reminders  # noqa: E402
from reminder_scheduler import ReminderBooking, StoreReminderConfig  # noqa: E402

STORE_ID = "store-1"


def _store(**overrides) -> StoreReminderConfig:
    base = dict(business_hours=(9 * 60, 18 * 60), message_tone="standard")
    base.update(overrides)
    return StoreReminderConfig(**base)


def _booking(**overrides) -> ReminderBooking:
    base = dict(
        booking_id="b1",
        store_id=STORE_ID,
        booking_date=date(2026, 8, 10),
        start_minutes=15 * 60 + 30,
        confirmed_at=datetime(2026, 8, 8, 12, 0),
        line_user_id="U1",
        menu="カット",
    )
    base.update(overrides)
    return ReminderBooking(**base)


class SendInitialReminderTests(unittest.TestCase):
    def test_due_booking_is_sent_and_marked(self):
        booking = _booking()
        push = InMemoryLinePushClient()
        now = datetime(2026, 8, 9, 17, 30)  # 目標17:00を過ぎている
        result = send_reminders([booking], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.initial_sent, ["b1"])
        self.assertEqual(booking.reminder_sent_at, now)
        self.assertEqual(len(push.sent), 1)
        user_id, text = push.sent[0]
        self.assertEqual(user_id, "U1")
        self.assertIn("8/10(月) 15:30〜", text)
        self.assertIn("カット", text)

    def test_not_due_booking_is_not_sent(self):
        booking = _booking()
        push = InMemoryLinePushClient()
        now = datetime(2026, 8, 9, 10, 0)  # まだ目標17:00前
        result = send_reminders([booking], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.initial_sent, [])
        self.assertIsNone(booking.reminder_sent_at)
        self.assertEqual(push.sent, [])

    def test_tone_is_taken_from_store_config(self):
        booking = _booking()
        push = InMemoryLinePushClient()
        now = datetime(2026, 8, 9, 17, 30)
        send_reminders([booking], now, {STORE_ID: _store(message_tone="casual")}, push)

        self.assertIn("🙌", push.sent[0][1])

    def test_delivery_failure_leaves_state_untouched_for_retry(self):
        booking = _booking()
        now = datetime(2026, 8, 9, 17, 30)

        class _FailingClient:
            def send_message(self, user_id: str, text: str) -> None:
                raise LinePushDeliveryError("simulated outage")

        result = send_reminders([booking], now, {STORE_ID: _store()}, _FailingClient())

        self.assertEqual(result.initial_sent, [])
        self.assertEqual(result.failed, ["b1"])
        self.assertIsNone(booking.reminder_sent_at)

        # 次回起動(now2)では未送信のまま送信対象として再度拾われる
        push = InMemoryLinePushClient()
        now2 = datetime(2026, 8, 9, 17, 45)
        result2 = send_reminders([booking], now2, {STORE_ID: _store()}, push)
        self.assertEqual(result2.initial_sent, ["b1"])
        self.assertEqual(booking.reminder_sent_at, now2)


class SendResendTests(unittest.TestCase):
    def test_due_resend_is_sent_and_marked_with_time_only_label(self):
        booking = _booking(reminder_sent_at=datetime(2026, 8, 9, 17, 0))
        push = InMemoryLinePushClient()
        now = datetime(2026, 8, 10, 9, 5)  # 予約当日・営業開始9:00を過ぎている
        result = send_reminders([booking], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.resend_sent, ["b1"])
        self.assertEqual(booking.resend_sent_at, now)
        user_id, text = push.sent[0]
        self.assertEqual(user_id, "U1")
        self.assertIn("【本日】15:30〜", text)
        self.assertNotIn("8/10", text)  # 再送は日付部分を持たない書式

    def test_already_replied_booking_is_not_resent(self):
        booking = _booking(
            reminder_sent_at=datetime(2026, 8, 9, 17, 0),
            customer_replied_at=datetime(2026, 8, 9, 20, 0),
        )
        push = InMemoryLinePushClient()
        now = datetime(2026, 8, 10, 9, 5)
        result = send_reminders([booking], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.resend_sent, [])
        self.assertIsNone(booking.resend_sent_at)
        self.assertEqual(push.sent, [])

    def test_delivery_failure_leaves_state_untouched_for_retry(self):
        booking = _booking(reminder_sent_at=datetime(2026, 8, 9, 17, 0))
        now = datetime(2026, 8, 10, 9, 5)

        class _FailingClient:
            def send_message(self, user_id: str, text: str) -> None:
                raise LinePushDeliveryError("simulated outage")

        result = send_reminders([booking], now, {STORE_ID: _store()}, _FailingClient())

        self.assertEqual(result.resend_sent, [])
        self.assertEqual(result.failed, ["b1"])
        self.assertIsNone(booking.resend_sent_at)


class SendBothInSameRunTests(unittest.TestCase):
    def test_one_run_can_send_initial_for_one_booking_and_resend_for_another(self):
        booking_initial = _booking(booking_id="b-initial")
        booking_resend = _booking(
            booking_id="b-resend",
            line_user_id="U2",
            reminder_sent_at=datetime(2026, 8, 9, 17, 0),
        )
        push = InMemoryLinePushClient()
        # b-initialの目標時刻(前日17:00)は過ぎていないが、b-resendの当日朝9:00は過ぎている
        # という状況を作るため、日付をまたいだbooking_dateにする。
        booking_initial.booking_date = date(2026, 8, 20)
        now = datetime(2026, 8, 10, 9, 5)
        result = send_reminders([booking_initial, booking_resend], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.initial_sent, [])  # b-initialはまだ目標時刻前
        self.assertEqual(result.resend_sent, ["b-resend"])
        self.assertEqual(len(push.sent), 1)


class ArchiveDuringSendRemindersTests(unittest.TestCase):
    """archive-trigger-unification-design.md準拠。send_reminders()実行のたびに
    select_confirmed_to_archive()も呼ばれ、来店日+1日以上経過したconfirmed予約が
    店舗のWebhook到着有無に関係なくアーカイブされることを確認する。"""

    def test_visited_booking_is_archived_after_one_day(self):
        booking = _booking(booking_date=date(2026, 8, 10))
        push = InMemoryLinePushClient()
        now = datetime(2026, 8, 11, 20, 0)  # 来店日+1日、Webhookトラフィックとは無関係
        result = send_reminders([booking], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.archived, ["b1"])
        self.assertEqual(booking.archived_at, now)

    def test_booking_on_visit_day_is_not_yet_archived(self):
        booking = _booking(booking_date=date(2026, 8, 10))
        push = InMemoryLinePushClient()
        now = datetime(2026, 8, 10, 23, 0)
        result = send_reminders([booking], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.archived, [])
        self.assertIsNone(booking.archived_at)

    def test_already_archived_booking_is_not_reported_again(self):
        booking = _booking(booking_date=date(2026, 8, 10), archived_at=datetime(2026, 8, 12, 0, 0))
        push = InMemoryLinePushClient()
        now = datetime(2026, 9, 1, 0, 0)
        result = send_reminders([booking], now, {STORE_ID: _store()}, push)

        self.assertEqual(result.archived, [])

    def test_archival_runs_independently_of_reminder_delivery_failure(self):
        # 同一実行内の別予約への送信失敗(failed)があっても、アーカイブ判定は
        # 別関心事のため影響を受けない。
        failing_booking = _booking(
            booking_id="b-failing",
            booking_date=date(2026, 8, 10),
            reminder_sent_at=datetime(2026, 8, 9, 17, 0),
        )  # 当日朝の再送対象(送信失敗させる)
        archivable_booking = _booking(booking_id="b-archivable", booking_date=date(2026, 7, 1))
        now = datetime(2026, 8, 10, 9, 5)

        class _FailingClient:
            def send_message(self, user_id: str, text: str) -> None:
                raise LinePushDeliveryError("simulated outage")

        result = send_reminders(
            [failing_booking, archivable_booking], now, {STORE_ID: _store()}, _FailingClient()
        )
        self.assertEqual(result.failed, ["b-failing"])
        self.assertEqual(result.archived, ["b-archivable"])
        self.assertEqual(archivable_booking.archived_at, now)


if __name__ == "__main__":
    unittest.main()
