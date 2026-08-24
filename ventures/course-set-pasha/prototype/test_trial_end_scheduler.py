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
    LIFF_URL_PLACEHOLDER,
    MINUTES_SAVED_PER_GENERATION,
    InMemoryLinePushClient,
    LinePushDeliveryError,
    TrialUserState,
    format_trial_end_notification_message,
    select_due_trial_end_notifications,
    send_trial_end_notifications,
)


class _FakeUsageCounter:
    """set_trial_end_notified_at()呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.notified_at: dict[str, datetime] = {}

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        self.notified_at[user_id] = notified_at


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


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


class FormatTrialEndNotificationMessageTest(unittest.TestCase):
    def test_default_message_contains_placeholder_liff_url(self) -> None:
        text = format_trial_end_notification_message(3)
        self.assertIn(LIFF_URL_PLACEHOLDER, text)
        self.assertIn("14日間の無料トライアル", text)
        self.assertIn("このまま何もしなければ自動課金は発生せず", text)

    def test_generation_count_is_embedded(self) -> None:
        text = format_trial_end_notification_message(5)
        self.assertIn("投稿文生成: 5回", text)

    def test_zero_generation_count_is_embedded(self) -> None:
        # trial_generation_count未接続時(usage_counter側でincrement_trial_generation_count
        # 未実装)のフォールバック値0でも、プレースホルダに戻らず数値としてそのまま表示される。
        text = format_trial_end_notification_message(0)
        self.assertIn("投稿文生成: 0回", text)

    def test_custom_liff_url_is_embedded(self) -> None:
        text = format_trial_end_notification_message(3, "https://liff.line.me/xxxx")
        self.assertIn("https://liff.line.me/xxxx", text)
        self.assertNotIn(LIFF_URL_PLACEHOLDER, text)

    def test_minutes_saved_is_generation_count_times_default_rate(self) -> None:
        # content-generation-time-estimate.md: 仮置き値は1回あたり15分。
        text = format_trial_end_notification_message(4)
        self.assertIn(f"約{4 * MINUTES_SAVED_PER_GENERATION}分(1回あたり平均15分と仮定)", text)

    def test_zero_generation_count_shows_zero_minutes_saved(self) -> None:
        text = format_trial_end_notification_message(0)
        self.assertIn("約0分(1回あたり平均15分と仮定)", text)

    def test_custom_minutes_per_generation_is_used(self) -> None:
        text = format_trial_end_notification_message(2, minutes_per_generation=10)
        self.assertIn("約20分(1回あたり平均10分と仮定)", text)

    def test_area_count_none_falls_back_to_legacy_formula(self) -> None:
        # area_count未指定(既定値None)時は、フェーズ109以前の単純化式のまま。
        text = format_trial_end_notification_message(4)
        self.assertIn("約60分(1回あたり平均15分と仮定)", text)

    def test_area_count_uses_phase109_formula_single_area(self) -> None:
        # content-generation-time-estimate.md: minutes(n) = 10 + 5n。生成回数3回・全て
        # 1エリアずつ(area_count=3)なら10*3 + 5*3 = 45分(=15分×3回と一致)。
        text = format_trial_end_notification_message(3, area_count=3)
        self.assertIn("約45分", text)
        self.assertIn("投稿文生成: 3回", text)

    def test_area_count_uses_phase109_formula_multi_area(self) -> None:
        # 生成回数2回・エリア更新総数5(例: 1回目1エリア+2回目4エリア)なら
        # 10*2 + 5*5 = 45分。
        text = format_trial_end_notification_message(2, area_count=5)
        self.assertIn("約45分", text)

    def test_area_count_zero_shows_base_minutes_only(self) -> None:
        text = format_trial_end_notification_message(0, area_count=0)
        self.assertIn("約0分", text)

    def test_area_count_message_uses_updated_wording(self) -> None:
        text = format_trial_end_notification_message(3, area_count=3)
        self.assertIn(
            "1エリアの更新につき平均15分、複数エリア同時更新時は1エリア追加ごとにさらに約5分と仮定",
            text,
        )
        self.assertNotIn("1回あたり平均15分と仮定", text)


class SendTrialEndNotificationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 23, 4, 0, 0)

    def test_sends_only_to_due_users_and_marks_notified(self) -> None:
        due = TrialUserState(user_id="u1", trial_start_at=self.now - timedelta(days=14))
        not_due = TrialUserState(user_id="u2", trial_start_at=self.now - timedelta(days=1))
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()

        result = send_trial_end_notifications([due, not_due], self.now, usage_counter, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual([user_id for user_id, _ in push.sent], ["u1"])
        self.assertEqual(usage_counter.notified_at, {"u1": self.now})

    def test_no_due_users_sends_nothing(self) -> None:
        not_due = TrialUserState(user_id="u1", trial_start_at=self.now - timedelta(days=1))
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()

        result = send_trial_end_notifications([not_due], self.now, usage_counter, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(push.sent, [])
        self.assertEqual(usage_counter.notified_at, {})

    def test_delivery_failure_is_recorded_and_not_marked_notified(self) -> None:
        due = TrialUserState(user_id="u1", trial_start_at=self.now - timedelta(days=14))
        usage_counter = _FakeUsageCounter()

        result = send_trial_end_notifications(
            [due], self.now, usage_counter, _FailingLinePushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertEqual(usage_counter.notified_at, {})

    def test_custom_liff_url_is_used_in_sent_message(self) -> None:
        due = TrialUserState(user_id="u1", trial_start_at=self.now - timedelta(days=14))
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()

        send_trial_end_notifications(
            [due], self.now, usage_counter, push, liff_url="https://liff.line.me/yyyy"
        )

        self.assertIn("https://liff.line.me/yyyy", push.sent[-1][1])

    def test_each_user_generation_count_is_embedded_independently(self) -> None:
        # README.mdフェーズ105: trial_generation_countはユーザーごとに異なるため、
        # 1回のsend_trial_end_notifications()呼び出し内でもユーザーごとに正しい値が
        # 埋め込まれることを確認する。
        user_a = TrialUserState(
            user_id="u1", trial_start_at=self.now - timedelta(days=14), trial_generation_count=3
        )
        user_b = TrialUserState(
            user_id="u2", trial_start_at=self.now - timedelta(days=20), trial_generation_count=9
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()

        send_trial_end_notifications([user_a, user_b], self.now, usage_counter, push)

        sent_by_user = dict(push.sent)
        self.assertIn("投稿文生成: 3回", sent_by_user["u1"])
        self.assertIn("投稿文生成: 9回", sent_by_user["u2"])

    def test_trial_area_count_is_passed_through_per_user(self) -> None:
        # README.mdフェーズ109: trial_area_countが設定されているユーザーはフェーズ109の
        # 按分式(10×generation_count + 5×area_count)、未設定(None、既存usage_counter
        # 実装からの後方互換)のユーザーは従来の単純化式のまま、という違いを確認する。
        user_with_area_count = TrialUserState(
            user_id="u1",
            trial_start_at=self.now - timedelta(days=14),
            trial_generation_count=2,
            trial_area_count=5,
        )
        user_without_area_count = TrialUserState(
            user_id="u2",
            trial_start_at=self.now - timedelta(days=14),
            trial_generation_count=4,
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()

        send_trial_end_notifications(
            [user_with_area_count, user_without_area_count], self.now, usage_counter, push
        )

        sent_by_user = dict(push.sent)
        # 10*2 + 5*5 = 45分
        self.assertIn("約45分", sent_by_user["u1"])
        # フォールバック: 4*15 = 60分
        self.assertIn("約60分(1回あたり平均15分と仮定)", sent_by_user["u2"])


if __name__ == "__main__":
    unittest.main()
