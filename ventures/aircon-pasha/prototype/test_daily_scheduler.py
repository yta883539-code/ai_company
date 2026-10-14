#!/usr/bin/env python3
"""daily_scheduler.pyのテスト(フェーズ315)。

README.mdフェーズ314「次回候補(2)」で指摘された、trial_end_scheduler.py・
payment_failure_reminder_scheduler.py・payment_suspension_schedulerの3モジュールを
1回の日次起動から呼び出す結合層を検証する。各モジュール自体の抽出条件・送信ロジックは
test_trial_end_scheduler.py・test_payment_failure_reminder_scheduler.py・
test_payment_suspension_scheduler.pyで既にカバー済みのため、ここでは重複させない。
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_scheduler import (  # noqa: E402
    build_payment_failure_reminder_states,
    build_payment_suspension_states,
    run_daily_checks,
)
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402
from user_id_linking import InMemoryUserProfileStore  # noqa: E402


class BuildPaymentFailureReminderStatesTest(unittest.TestCase):
    def test_reflects_profile_fields_in_user_id_order(self):
        store = InMemoryUserProfileStore()
        now = datetime(2026, 10, 14, 4, 0, 0)
        store.save("u2", _profile("u2"))
        store.save("u1", _profile("u1"))
        store.set_payment_failure_detected_at("u1", now - timedelta(days=5))
        store.set_payment_suspended_at("u2", now - timedelta(days=1))

        states = build_payment_failure_reminder_states(store)

        self.assertEqual([s.user_id for s in states], ["u1", "u2"])
        self.assertEqual(states[0].payment_failure_detected_at, now - timedelta(days=5))
        self.assertIsNone(states[0].payment_suspended_at)
        self.assertEqual(states[1].payment_suspended_at, now - timedelta(days=1))

    def test_empty_store_returns_empty_list(self):
        self.assertEqual(build_payment_failure_reminder_states(InMemoryUserProfileStore()), [])


class BuildPaymentSuspensionStatesTest(unittest.TestCase):
    def test_reflects_profile_fields_in_user_id_order(self):
        store = InMemoryUserProfileStore()
        now = datetime(2026, 10, 14, 4, 0, 0)
        store.save("u1", _profile("u1"))
        store.set_payment_failure_detected_at("u1", now - timedelta(days=8))

        states = build_payment_suspension_states(store)

        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].user_id, "u1")
        self.assertEqual(states[0].payment_failure_detected_at, now - timedelta(days=8))
        self.assertIsNone(states[0].payment_suspended_at)


class RunDailyChecksTest(unittest.TestCase):
    def test_runs_all_three_schedulers_against_the_same_store(self):
        store = InMemoryUserProfileStore()
        push_client = InMemoryLinePushClient()
        now = datetime(2026, 10, 14, 4, 0, 0)

        # トライアル終了通知の対象(14日以上経過・未送信)
        store.save("trial_user", _profile("trial_user"))
        store.set_trial_start_at("trial_user", now - timedelta(days=14))

        # 決済失敗3日前リマインドの対象(検知から4日経過・未制限・未送信)
        store.save("reminder_user", _profile("reminder_user"))
        store.set_payment_failure_detected_at("reminder_user", now - timedelta(days=4))

        # 制限モード移行の対象(検知から7日以上経過・未制限)
        store.save("suspend_user", _profile("suspend_user"))
        store.set_payment_failure_detected_at("suspend_user", now - timedelta(days=7))

        result = run_daily_checks(now, store, push_client)

        self.assertIn("trial_user", result.trial_end_notifications.sent)
        self.assertIn("reminder_user", result.payment_failure_reminders.sent)
        self.assertIn("suspend_user", result.payment_suspensions.suspended)
        # 書き込みが実際にstoreへ反映されていること(次回起動時の二重送信防止)
        self.assertIsNotNone(store.get("trial_user").trial_end_notified_at)
        self.assertIsNotNone(store.get("suspend_user").payment_suspended_at)
        # 3モジュール合計で3通のFlex Messageが送信されていること
        self.assertEqual(len(push_client.sent), 3)

    def test_empty_store_runs_without_error_and_sends_nothing(self):
        store = InMemoryUserProfileStore()
        push_client = InMemoryLinePushClient()
        now = datetime(2026, 10, 14, 4, 0, 0)

        result = run_daily_checks(now, store, push_client)

        self.assertEqual(result.trial_end_notifications.sent, [])
        self.assertEqual(result.payment_failure_reminders.sent, [])
        self.assertEqual(result.payment_suspensions.suspended, [])
        self.assertEqual(push_client.sent, [])

    def test_a_user_due_for_multiple_notices_receives_each_independently(self):
        # trial_end(14日)とpayment_failure_reminder(4日)の対象条件は異なるフィールド
        # (trial_start_at vs payment_failure_detected_at)を見るため、同一ユーザーが
        # 両方の対象になっても互いを妨げないことを確認する。
        store = InMemoryUserProfileStore()
        push_client = InMemoryLinePushClient()
        now = datetime(2026, 10, 14, 4, 0, 0)
        store.save("both_user", _profile("both_user"))
        store.set_trial_start_at("both_user", now - timedelta(days=14))
        store.set_payment_failure_detected_at("both_user", now - timedelta(days=4))

        result = run_daily_checks(now, store, push_client)

        self.assertIn("both_user", result.trial_end_notifications.sent)
        self.assertIn("both_user", result.payment_failure_reminders.sent)
        self.assertEqual(len(push_client.sent), 2)

    def test_user_exactly_at_suspension_threshold_is_suspended_not_reminded(self):
        # daily_scheduler.run_daily_checks()のdocstring参照: payment_suspension_
        # scheduler.select_due_payment_suspensions()とpayment_failure_reminder_
        # scheduler.select_due_payment_failure_reminders()の抽出条件は、猶予期間
        # ちょうど7日経過時点(まだpayment_suspended_at未設定)のユーザーに関して
        # 重なる。payment_suspensionを先に実行することで、このユーザーには
        # 「制限モード移行」通知のみが送られ、「まもなく期限」のリマインドは
        # 二重送信されないことを確認する。
        store = InMemoryUserProfileStore()
        push_client = InMemoryLinePushClient()
        now = datetime(2026, 10, 14, 4, 0, 0)
        store.save("edge_user", _profile("edge_user"))
        store.set_payment_failure_detected_at("edge_user", now - timedelta(days=7))

        result = run_daily_checks(now, store, push_client)

        self.assertIn("edge_user", result.payment_suspensions.suspended)
        self.assertNotIn("edge_user", result.payment_failure_reminders.sent)
        self.assertEqual(len(push_client.sent), 1)


def _profile(user_id: str):
    from user_id_linking import UserProfile

    return UserProfile(
        business_name=f"{user_id}商店",
        business_type="エアコン洗浄業",
        email=f"{user_id}@example.com",
        linked_at=datetime(2026, 1, 1, 0, 0, 0),
    )


if __name__ == "__main__":
    unittest.main()
