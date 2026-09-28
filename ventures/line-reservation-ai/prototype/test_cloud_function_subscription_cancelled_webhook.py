#!/usr/bin/env python3
"""cloud_function_subscription_cancelled_webhook.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_cloud_function_subscription_cancelled_webhook -v で実行可能。
"""

from __future__ import annotations

import unittest

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError
from datetime import datetime

from cloud_function_subscription_cancelled_webhook import (
    OUTCOME_ALREADY_CANCELLED,
    OUTCOME_CANCELLATION_RESCHEDULED,
    OUTCOME_CANCELLATION_SCHEDULED,
    OUTCOME_CANCELLED,
    OUTCOME_NO_CHANGE,
    OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED,
    OUTCOME_SEND_FAILED,
    OUTCOME_STALE_EVENT,
    StoreSubscriptionState,
    classify_subscription_deleted,
    classify_subscription_update,
    handle_subscription_deleted,
    handle_subscription_updated,
    render_cancellation_completed_message,
    render_cancellation_rescheduled_message,
    render_cancellation_scheduled_message,
)


class AlwaysFailingLinePushClient:
    """送信が常に失敗する検証用クライアント。"""

    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated failure")


def _store(**overrides) -> StoreSubscriptionState:
    defaults = dict(
        store_id="store-1",
        owner_line_user_id="owner-1",
        plan_name="スタンダードプラン",
        period_end_date="2026-09-14",
    )
    defaults.update(overrides)
    return StoreSubscriptionState(**defaults)


class ClassifySubscriptionUpdateTests(unittest.TestCase):
    def test_false_to_true_is_scheduled(self):
        self.assertEqual(
            classify_subscription_update(False, True, None), OUTCOME_CANCELLATION_SCHEDULED
        )

    def test_true_to_false_is_rescheduled(self):
        self.assertEqual(
            classify_subscription_update(True, False, None), OUTCOME_CANCELLATION_RESCHEDULED
        )

    def test_no_change_when_both_false(self):
        self.assertEqual(classify_subscription_update(False, False, None), OUTCOME_NO_CHANGE)

    def test_no_change_when_both_true(self):
        self.assertEqual(classify_subscription_update(True, True, None), OUTCOME_NO_CHANGE)

    def test_payment_failed_store_is_out_of_scope(self):
        self.assertEqual(
            classify_subscription_update(False, True, "payment_failed"), OUTCOME_NO_CHANGE
        )

    def test_payment_suspended_store_is_out_of_scope(self):
        # 制限モード(新規予約受付停止済み)の店舗に対して、render_cancellation_scheduled_
        # message()の「新規のご予約受付も含め、機能の制限はありません」という事実と矛盾する
        # 案内を送らないための除外(restricted-mode-cancellation-consistency-review.md)。
        self.assertEqual(
            classify_subscription_update(False, True, "payment_suspended"), OUTCOME_NO_CHANGE
        )


class ClassifySubscriptionDeletedTests(unittest.TestCase):
    def test_normal_store_is_cancelled(self):
        self.assertEqual(classify_subscription_deleted(None), OUTCOME_CANCELLED)

    def test_trial_unselected_store_is_cancelled(self):
        self.assertEqual(classify_subscription_deleted("trial_unselected"), OUTCOME_CANCELLED)

    def test_already_cancelled_is_idempotent(self):
        self.assertEqual(classify_subscription_deleted("cancelled"), OUTCOME_ALREADY_CANCELLED)

    def test_payment_failed_is_out_of_scope(self):
        self.assertEqual(
            classify_subscription_deleted("payment_failed"), OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED
        )


class RenderMessageTests(unittest.TestCase):
    def test_scheduled_message_contains_plan_and_date(self):
        text = render_cancellation_scheduled_message(
            "スタンダードプラン", "2026-09-14", "https://example.com/portal"
        )
        self.assertIn("スタンダードプラン", text)
        self.assertIn("2026-09-14", text)
        self.assertIn("https://example.com/portal", text)

    def test_scheduled_message_unknown_tone_falls_back_to_standard(self):
        standard = render_cancellation_scheduled_message(
            "スタンダードプラン", "2026-09-14", "https://example.com/portal", tone="standard"
        )
        unknown = render_cancellation_scheduled_message(
            "スタンダードプラン", "2026-09-14", "https://example.com/portal", tone="unknown"
        )
        self.assertEqual(standard, unknown)

    def test_scheduled_message_none_portal_url_falls_back_to_reply_in_chat(self):
        # portal-session-provider-design.md 4節2.: 取得失敗時はURLブロックを
        # 「このトークルームへご返信ください」導線に差し替える。
        for tone in ("formal", "standard", "casual"):
            text = render_cancellation_scheduled_message(
                "スタンダードプラン", "2026-09-14", None, tone=tone
            )
            self.assertNotIn("お手続きはこちら", text)
            self.assertNotIn("example.com", text)
            self.assertIn("トークルーム", text)
            self.assertIn("スタンダードプラン", text)
            self.assertIn("2026-09-14", text)

    def test_rescheduled_message_contains_plan_and_date(self):
        text = render_cancellation_rescheduled_message("スタンダードプラン", "2026-09-14")
        self.assertIn("スタンダードプラン", text)
        self.assertIn("2026-09-14", text)

    def test_completed_message_mentions_new_booking_stop_and_existing_continuation(self):
        text = render_cancellation_completed_message()
        self.assertIn("新規のご予約受付は停止", text)
        self.assertIn("前日リマインド", text)

    def test_all_tones_render_without_error(self):
        for tone in ("formal", "standard", "casual"):
            self.assertTrue(
                render_cancellation_scheduled_message(
                    "スタンダードプラン", "2026-09-14", "https://example.com/portal", tone=tone
                )
            )
            self.assertTrue(render_cancellation_rescheduled_message("スタンダードプラン", "2026-09-14", tone=tone))
            self.assertTrue(render_cancellation_completed_message(tone=tone))


class HandleSubscriptionUpdatedTests(unittest.TestCase):
    def test_scheduled_sends_message_and_does_not_change_state(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(
            state, False, True, push, portal_url="https://example.com/billing/portal"
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        self.assertIsNone(state.suspension_reason)
        self.assertEqual(len(push.sent), 1)
        self.assertIn("https://example.com/billing/portal", push.sent[0][1])

    def test_scheduled_without_portal_url_still_sends_message(self):
        # portal_link_provider未接続(None)でも送信自体はブロックしない
        # (portal-session-provider-design.md 4節2.のフォールバック文言に委ねる)。
        state = _store()
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(state, False, True, push)
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        self.assertIn("トークルーム", push.sent[0][1])

    def test_rescheduled_sends_message(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(state, True, False, push)
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_RESCHEDULED)
        self.assertTrue(result.notified)
        self.assertEqual(len(push.sent), 1)

    def test_no_change_does_not_send(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(state, False, False, push)
        self.assertEqual(result.outcome, OUTCOME_NO_CHANGE)
        self.assertFalse(result.notified)
        self.assertEqual(len(push.sent), 0)

    def test_send_failure_is_reported_and_state_unchanged(self):
        state = _store()
        result = handle_subscription_updated(state, False, True, AlwaysFailingLinePushClient())
        self.assertEqual(result.outcome, OUTCOME_SEND_FAILED)
        self.assertIsNone(state.suspension_reason)

    def test_payment_failed_store_is_untouched(self):
        state = _store(suspension_reason="payment_failed")
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(state, False, True, push)
        self.assertEqual(result.outcome, OUTCOME_NO_CHANGE)
        self.assertEqual(state.suspension_reason, "payment_failed")
        self.assertEqual(len(push.sent), 0)

    def test_payment_suspended_store_is_untouched(self):
        state = _store(suspension_reason="payment_suspended")
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(state, False, True, push)
        self.assertEqual(result.outcome, OUTCOME_NO_CHANGE)
        self.assertEqual(state.suspension_reason, "payment_suspended")
        self.assertEqual(len(push.sent), 0)

    # subscription-updated-event-order-guard-design.md準拠(kura-pashaフェーズ198・
    # course-set-pashaの横展開)。

    def test_applies_and_records_event_time_when_newer_than_recorded(self):
        state = _store(
            last_subscription_updated_event_time=datetime(2026, 9, 20, 9, 0)
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(
            state, False, True, push, event_time=datetime(2026, 9, 20, 10, 0)
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        self.assertFalse(result.stale)
        self.assertEqual(
            state.last_subscription_updated_event_time, datetime(2026, 9, 20, 10, 0)
        )

    def test_skips_when_updated_event_is_stale(self):
        # 遅延配信ケース: 既により新しい.updatedイベント(10:00)で確定済みの状態に対し、
        # それより前(9:00)に発生していたはずのイベントが遅れて届いても、通知を送らず
        # last_subscription_updated_event_timeも巻き戻さない。
        state = _store(
            last_subscription_updated_event_time=datetime(2026, 9, 20, 10, 0)
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(
            state, False, True, push, event_time=datetime(2026, 9, 20, 9, 0)
        )
        self.assertEqual(result.outcome, OUTCOME_STALE_EVENT)
        self.assertTrue(result.stale)
        self.assertFalse(result.notified)
        self.assertEqual(len(push.sent), 0)
        self.assertEqual(
            state.last_subscription_updated_event_time, datetime(2026, 9, 20, 10, 0)
        )

    def test_applies_unconditionally_when_event_time_omitted(self):
        # event_time省略時(呼び出し側が未対応)は従来通り無条件適用する後方互換。
        state = _store(
            last_subscription_updated_event_time=datetime(2026, 9, 20, 10, 0)
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(state, False, True, push)
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        self.assertEqual(
            state.last_subscription_updated_event_time, datetime(2026, 9, 20, 10, 0)
        )

    def test_applies_unconditionally_when_store_lacks_recorded_event_time(self):
        # last_subscription_updated_event_time未設定(本ガード導入前からの既存店舗・
        # 初回)の場合は従来通り無条件適用する。
        state = _store(last_subscription_updated_event_time=None)
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(
            state, False, True, push, event_time=datetime(2026, 9, 20, 9, 0)
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLATION_SCHEDULED)
        self.assertTrue(result.notified)
        self.assertEqual(
            state.last_subscription_updated_event_time, datetime(2026, 9, 20, 9, 0)
        )

    def test_no_change_outcome_still_records_event_time(self):
        # NO_CHANGE(cancel_at_period_endが変化しない.updated、支払い方法変更等)でも
        # event_timeは記録する(course-set-pashaの「結果にかかわらず記録」方針)。
        state = _store()
        push = InMemoryLinePushClient()
        result = handle_subscription_updated(
            state, False, False, push, event_time=datetime(2026, 9, 20, 9, 0)
        )
        self.assertEqual(result.outcome, OUTCOME_NO_CHANGE)
        self.assertEqual(
            state.last_subscription_updated_event_time, datetime(2026, 9, 20, 9, 0)
        )


class HandleSubscriptionDeletedTests(unittest.TestCase):
    def test_cancels_active_store(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertEqual(result.outcome, OUTCOME_CANCELLED)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_changed)
        self.assertEqual(state.suspension_reason, "cancelled")
        self.assertEqual(len(push.sent), 1)

    def test_cancels_trial_unselected_store(self):
        state = _store(suspension_reason="trial_unselected")
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertEqual(result.outcome, OUTCOME_CANCELLED)
        self.assertEqual(state.suspension_reason, "cancelled")

    def test_webhook_retry_is_idempotent(self):
        state = _store(suspension_reason="cancelled")
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertEqual(result.outcome, OUTCOME_ALREADY_CANCELLED)
        self.assertFalse(result.notified)
        self.assertEqual(len(push.sent), 0)

    def test_payment_failed_store_is_untouched(self):
        state = _store(suspension_reason="payment_failed")
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertEqual(result.outcome, OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED)
        self.assertEqual(state.suspension_reason, "payment_failed")
        self.assertEqual(len(push.sent), 0)

    def test_send_failure_leaves_state_unchanged_for_retry(self):
        state = _store()
        result = handle_subscription_deleted(state, AlwaysFailingLinePushClient())
        self.assertEqual(result.outcome, OUTCOME_SEND_FAILED)
        self.assertFalse(result.state_changed)
        self.assertIsNone(state.suspension_reason)

    # blocked-but-billing-owner-email-notification-design.md 5節「クリア配線」
    # (フェーズ続き178)準拠。

    def test_cancellation_clears_blocked_but_billing_owner_notified_at(self):
        state = _store(blocked_but_billing_owner_notified_at="2026-09-01T00:00:00Z")
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertTrue(result.blocked_but_billing_owner_notified_at_cleared)
        self.assertIsNone(state.blocked_but_billing_owner_notified_at)

    def test_cancellation_without_prior_notification_leaves_flag_unset(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertFalse(result.blocked_but_billing_owner_notified_at_cleared)
        self.assertIsNone(state.blocked_but_billing_owner_notified_at)

    def test_send_failure_does_not_clear_blocked_but_billing_owner_notified_at(self):
        state = _store(blocked_but_billing_owner_notified_at="2026-09-01T00:00:00Z")
        result = handle_subscription_deleted(state, AlwaysFailingLinePushClient())
        self.assertFalse(result.blocked_but_billing_owner_notified_at_cleared)
        self.assertEqual(state.blocked_but_billing_owner_notified_at, "2026-09-01T00:00:00Z")

    def test_webhook_retry_does_not_reclear_already_cleared_flag(self):
        # 冪等性: suspension_reasonが既に"cancelled"(=前回配信で処理済み)の場合、
        # OUTCOME_ALREADY_CANCELLEDで早期returnするためclearedはFalseのまま。
        state = _store(
            suspension_reason="cancelled",
            blocked_but_billing_owner_notified_at=None,
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertEqual(result.outcome, OUTCOME_ALREADY_CANCELLED)
        self.assertFalse(result.blocked_but_billing_owner_notified_at_cleared)

    # subscription-event-order-guard-design.md準拠(kura-pashaの
    # subscription-status-event-order-guard-design.mdの横展開)。

    def test_applies_when_event_time_newer_than_recorded(self):
        # 正常順序の回帰確認: event_time指定でも新しいイベントなら従来通り適用される。
        state = _store(last_subscription_event_time=datetime(2026, 9, 20, 9, 0))
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(
            state, push, event_time=datetime(2026, 9, 20, 10, 0)
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLED)
        self.assertTrue(result.notified)
        self.assertEqual(state.suspension_reason, "cancelled")
        self.assertEqual(state.last_subscription_event_time, datetime(2026, 9, 20, 10, 0))

    def test_skips_when_deleted_event_is_stale_after_reactivation(self):
        # 遅延配信ケース(design「ケースA」): 解約直後の即再契約でsuspension_reasonが
        # 既に解除(None)された後、それより前(9:00)に発生していたはずの
        # customer.subscription.deletedが遅れて届いても、有効な契約を誤って
        # "cancelled"へ書き換えない。
        state = _store(
            suspension_reason=None,
            last_subscription_event_time=datetime(2026, 9, 20, 10, 0),
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(
            state, push, event_time=datetime(2026, 9, 20, 9, 0)
        )
        self.assertEqual(result.outcome, OUTCOME_STALE_EVENT)
        self.assertTrue(result.stale)
        self.assertFalse(result.notified)
        self.assertIsNone(state.suspension_reason)
        self.assertEqual(len(push.sent), 0)

    def test_applies_unconditionally_when_event_time_omitted(self):
        # event_time省略時(呼び出し側が未対応)は従来通り無条件適用する後方互換。
        state = _store(last_subscription_event_time=datetime(2026, 9, 20, 10, 0))
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(state, push)
        self.assertEqual(result.outcome, OUTCOME_CANCELLED)
        self.assertTrue(result.notified)
        self.assertEqual(state.suspension_reason, "cancelled")

    def test_applies_unconditionally_when_store_lacks_recorded_event_time(self):
        # last_subscription_event_time未設定(store側が本ガード未対応/初回)の場合は
        # 従来通り無条件適用する。
        state = _store(last_subscription_event_time=None)
        push = InMemoryLinePushClient()
        result = handle_subscription_deleted(
            state, push, event_time=datetime(2026, 9, 20, 9, 0)
        )
        self.assertEqual(result.outcome, OUTCOME_CANCELLED)
        self.assertTrue(result.notified)
        self.assertEqual(state.suspension_reason, "cancelled")


if __name__ == "__main__":
    unittest.main()
