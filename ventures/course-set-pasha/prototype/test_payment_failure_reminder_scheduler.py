#!/usr/bin/env python3
"""payment_failure_reminder_scheduler.pyのテスト。
payment-failure-reminder-scheduler-design.md 4節の抽出条件を検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_webhook import (  # noqa: E402
    PORTAL_LINK_PLACEHOLDER,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    InMemoryPortalLinkProvider,
)
from payment_failure_reminder_scheduler import (  # noqa: E402
    DEFAULT_GRACE_PERIOD_DAYS,
    DEFAULT_REMINDER_DAYS_BEFORE_END,
    PaymentFailureUserState,
    render_payment_failure_reminder_message,
    select_due_payment_failure_reminders,
    send_payment_failure_reminders,
)
from trial_end_scheduler import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
)


class _FakeUsageCounter:
    """set_payment_failure_reminder_sent_at()呼び出しのみを記録するテスト用スタブ。"""

    def __init__(self) -> None:
        self.reminder_sent_at: dict[str, datetime] = {}

    def set_payment_failure_reminder_sent_at(self, user_id: str, sent_at: datetime) -> None:
        self.reminder_sent_at[user_id] = sent_at


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class SelectDuePaymentFailureRemindersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 28, 4, 0, 0)

    def test_exactly_4_days_elapsed_is_due(self) -> None:
        # grace_period_days(7) - reminder_days_before_end(3) = 4日ちょうど。
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=4)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [user])

    def test_5_days_elapsed_is_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=5)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [user])

    def test_3_days_elapsed_is_not_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=3)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_exactly_7_days_elapsed_is_not_due(self) -> None:
        # 猶予期間ちょうど経過(制限モード相当): 上限側の条件で除外される。
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=7)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_more_than_7_days_elapsed_is_not_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=20)
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_already_reminded_is_not_due(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1",
            payment_failure_detected_at=self.now - timedelta(days=6),
            payment_failure_reminder_sent_at=self.now - timedelta(days=1),
        )
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_no_detected_at_is_not_due(self) -> None:
        user = PaymentFailureUserState(user_id="u1", payment_failure_detected_at=None)
        self.assertEqual(select_due_payment_failure_reminders([user], self.now), [])

    def test_custom_thresholds(self) -> None:
        # grace_period_days=14, reminder_days_before_end=5 → 下限9日・上限14日。
        user_due = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=10)
        )
        user_too_early = PaymentFailureUserState(
            user_id="u2", payment_failure_detected_at=self.now - timedelta(days=8)
        )
        due = select_due_payment_failure_reminders(
            [user_due, user_too_early], self.now, grace_period_days=14, reminder_days_before_end=5
        )
        self.assertEqual(due, [user_due])

    def test_preserves_input_order_for_multiple_due_users(self) -> None:
        user1 = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=4)
        )
        user2 = PaymentFailureUserState(
            user_id="u2", payment_failure_detected_at=self.now - timedelta(days=6)
        )
        self.assertEqual(
            select_due_payment_failure_reminders([user1, user2], self.now), [user1, user2]
        )


class RenderPaymentFailureReminderMessageTest(unittest.TestCase):
    def test_resolves_portal_url_per_user(self) -> None:
        provider = InMemoryPortalLinkProvider(url="https://billing.stripe.com/p/session/u1")
        text = render_payment_failure_reminder_message(provider, "u1")
        self.assertIn("https://billing.stripe.com/p/session/u1", text)
        self.assertNotIn(PORTAL_LINK_PLACEHOLDER, text)
        self.assertIn("3日後に投稿文の生成を一時停止", text)

    def test_provider_none_falls_back(self) -> None:
        text = render_payment_failure_reminder_message(None, "u1")
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_user_id_none_falls_back(self) -> None:
        provider = InMemoryPortalLinkProvider(url="https://billing.stripe.com/p/session/u1")
        text = render_payment_failure_reminder_message(provider, None)
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_url_fetch_failure_falls_back(self) -> None:
        provider = InMemoryPortalLinkProvider(url=None)
        text = render_payment_failure_reminder_message(provider, "u1")
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)


class SendPaymentFailureRemindersTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 8, 28, 4, 0, 0)

    def test_sends_to_due_users_and_records_sent_at(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=5)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        provider = InMemoryPortalLinkProvider(url="https://billing.stripe.com/p/session/u1")
        result = send_payment_failure_reminders(
            [user], self.now, usage_counter, push, provider
        )

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(usage_counter.reminder_sent_at["u1"], self.now)
        self.assertEqual(
            push.sent,
            [("u1", render_payment_failure_reminder_message(provider, "u1"))],
        )

    def test_sends_fallback_message_when_provider_not_given(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=5)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        result = send_payment_failure_reminders([user], self.now, usage_counter, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(push.sent, [("u1", PORTAL_LINK_UNAVAILABLE_FALLBACK)])

    def test_skips_not_due_users(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=1)
        )
        usage_counter = _FakeUsageCounter()
        push = InMemoryLinePushClient()
        result = send_payment_failure_reminders([user], self.now, usage_counter, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(push.sent, [])
        self.assertNotIn("u1", usage_counter.reminder_sent_at)

    def test_failed_send_does_not_record_sent_at(self) -> None:
        user = PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=self.now - timedelta(days=5)
        )
        usage_counter = _FakeUsageCounter()
        result = send_payment_failure_reminders(
            [user], self.now, usage_counter, _FailingLinePushClient()
        )

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertNotIn("u1", usage_counter.reminder_sent_at)

    def test_default_grace_period_matches_dunning_design(self) -> None:
        # デフォルト値がpayment-failure-dunning-design.mdの猶予7日・3日前リマインドと
        # 一致していることを固定する回帰テスト。
        self.assertEqual(DEFAULT_GRACE_PERIOD_DAYS, 7)
        self.assertEqual(DEFAULT_REMINDER_DAYS_BEFORE_END, 3)


class StripeWebhookPaymentFailureDetectedToReminderSchedulerWiringTest(unittest.TestCase):
    """stripe_webhook.dispatch_stripe_event()が`invoice.payment_failed`受信時に書き込む
    payment_failure_detected_atと、select_due_payment_failure_reminders()が読む
    payment_failure_detected_at・payment_failure_reminder_sent_atが、
    build_payment_failure_user_states()を介して実際に同一のInMemoryUsageCounter経由で
    つながることを確認する(trial_end_scheduler.pyのStripeWebhookUpgradedAtTo
    TrialEndSchedulerWiringTest〈フェーズ130〉・payment_suspension_owner_notification.pyの
    StripeWebhookPaymentFailureDetectedToOwnerNotificationWiringTest〈フェーズ134〉と
    同種の配線漏れの観点、フェーズ135)。"""

    def setUp(self) -> None:
        from cloud_function_webhook import InMemoryUsageCounter
        from deletion_candidate import InMemoryProfileDeletionCandidateStore

        self.usage_counter = InMemoryUsageCounter()
        self.store = InMemoryProfileDeletionCandidateStore()

    def test_payment_failure_event_becomes_due_within_reminder_window(self) -> None:
        from stripe_webhook import dispatch_stripe_event

        from payment_failure_reminder_scheduler import build_payment_failure_user_states

        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,  # 2023-11-14T22:13:20Z
            "data": {"object": {"customer": "cus_A"}},
        }
        result = dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=lambda customer: {"cus_A": "u1"}.get(customer),
            usage_counter=self.usage_counter,
        )
        self.assertEqual(result.payment_failure_detected_user_ids, ["u1"])

        event_time = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)

        # 検知から2日(4日未満、リマインド窓の下限前): build_payment_failure_user_states()
        # 経由でもまだ対象外のまま。
        states = build_payment_failure_user_states(self.usage_counter, ["u1"])
        due = select_due_payment_failure_reminders(states, event_time + timedelta(days=2))
        self.assertEqual(due, [])

        # 検知から5日(4日以上7日未満、リマインド窓): 対象となる。
        states = build_payment_failure_user_states(self.usage_counter, ["u1"])
        due = select_due_payment_failure_reminders(states, event_time + timedelta(days=5))
        self.assertEqual([u.user_id for u in due], ["u1"])

        # 検知から8日(猶予期間超過、制限モード相当): 既に対象外(payment_suspension_
        # owner_notification.py側の対象へ切り替わる想定)。
        states = build_payment_failure_user_states(self.usage_counter, ["u1"])
        due = select_due_payment_failure_reminders(states, event_time + timedelta(days=8))
        self.assertEqual(due, [])

    def test_reminder_sent_excludes_user_from_next_scan(self) -> None:
        from stripe_webhook import dispatch_stripe_event

        from payment_failure_reminder_scheduler import build_payment_failure_user_states

        event = {
            "type": "invoice.payment_failed",
            "created": 1_700_000_000,
            "data": {"object": {"customer": "cus_A"}},
        }
        dispatch_stripe_event(
            event,
            store=self.store,
            resolve_user_id=lambda customer: {"cus_A": "u1"}.get(customer),
            usage_counter=self.usage_counter,
        )
        event_time = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
        now = event_time + timedelta(days=5)

        # send_payment_failure_reminders()を、dispatch_stripe_event()と同一の
        # usage_counterに対して実行すると、payment_failure_reminder_sent_atが書き込まれる。
        states = build_payment_failure_user_states(self.usage_counter, ["u1"])
        push = InMemoryLinePushClient()
        send_result = send_payment_failure_reminders(states, now, self.usage_counter, push)
        self.assertEqual(send_result.sent, ["u1"])

        # 同じusage_counterを再度build_payment_failure_user_states()経由で読み取ると、
        # payment_failure_reminder_sent_at設定済みのため次回スキャンの対象から除外される
        # (二重送信しない)。
        states_after = build_payment_failure_user_states(self.usage_counter, ["u1"])
        due_after = select_due_payment_failure_reminders(states_after, now)
        self.assertEqual(due_after, [])


if __name__ == "__main__":
    unittest.main()
