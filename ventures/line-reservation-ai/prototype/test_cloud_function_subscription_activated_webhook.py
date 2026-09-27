#!/usr/bin/env python3
"""cloud_function_subscription_activated_webhook.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_cloud_function_subscription_activated_webhook -v で実行可能。
"""

from __future__ import annotations

import unittest

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError
from datetime import datetime

from cloud_function_subscription_activated_webhook import (
    OUTCOME_ACTIVATED,
    OUTCOME_ALREADY_ACTIVE,
    OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED,
    OUTCOME_SEND_FAILED,
    OUTCOME_STALE_EVENT,
    StoreSubscriptionState,
    classify_subscription_activated,
    handle_subscription_activated,
    render_subscription_activated_message,
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
        next_billing_date="2026-09-14",
    )
    defaults.update(overrides)
    return StoreSubscriptionState(**defaults)


class ClassifySubscriptionActivatedTests(unittest.TestCase):
    def test_trial_unselected_is_activated(self):
        state = _store(suspension_reason="trial_unselected")
        self.assertEqual(classify_subscription_activated(state), OUTCOME_ACTIVATED)

    def test_cancelled_is_activated(self):
        state = _store(suspension_reason="cancelled")
        self.assertEqual(classify_subscription_activated(state), OUTCOME_ACTIVATED)

    def test_no_suspension_reason_is_already_active(self):
        state = _store(suspension_reason=None)
        self.assertEqual(classify_subscription_activated(state), OUTCOME_ALREADY_ACTIVE)

    def test_payment_failed_is_out_of_scope(self):
        state = _store(suspension_reason="payment_failed")
        self.assertEqual(
            classify_subscription_activated(state), OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED
        )


class RenderSubscriptionActivatedMessageTests(unittest.TestCase):
    def test_facts_identical_across_tones(self):
        for tone in ("formal", "standard", "casual"):
            text = render_subscription_activated_message(
                "スタンダードプラン", "2026-09-14", "https://example.com/portal", tone
            )
            self.assertIn("スタンダードプラン", text)
            self.assertIn("2026-09-14", text)
            self.assertIn("https://example.com/portal", text)

    def test_formal_has_no_emoji_or_exclamation(self):
        text = render_subscription_activated_message(
            "スタンダードプラン", "2026-09-14", "https://example.com/portal", "formal"
        )
        self.assertNotIn("!", text)
        self.assertNotIn("🎉", text)

    def test_casual_allows_emoji_and_at_most_one_exclamation(self):
        text = render_subscription_activated_message(
            "スタンダードプラン", "2026-09-14", "https://example.com/portal", "casual"
        )
        self.assertLessEqual(text.count("!"), 1)  # message-tone-variants.md: カジュアルは1つまで
        self.assertEqual(text.count("🎉"), 1)  # 絵文字は1メッセージにつき1個まで

    def test_unknown_tone_falls_back_to_standard(self):
        expected = render_subscription_activated_message(
            "スタンダードプラン", "2026-09-14", "https://example.com/portal", "standard"
        )
        actual = render_subscription_activated_message(
            "スタンダードプラン", "2026-09-14", "https://example.com/portal", "unknown-tone"
        )
        self.assertEqual(actual, expected)

    def test_none_portal_url_omits_portal_line(self):
        # portal-session-provider-design.md 4節2.: 取得失敗時は案内行自体を省略する。
        for tone in ("formal", "standard", "casual"):
            text = render_subscription_activated_message(
                "スタンダードプラン", "2026-09-14", None, tone
            )
            self.assertNotIn("マイページ", text)
            self.assertNotIn("ご登録内容の確認・変更", text)
            self.assertIn("スタンダードプラン", text)
            self.assertIn("2026-09-14", text)


class HandleSubscriptionActivatedTests(unittest.TestCase):
    def test_activation_sends_message_and_clears_suspension(self):
        state = _store(suspension_reason="trial_unselected")
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(
            state, push, portal_url="https://example.com/billing/portal"
        )

        self.assertEqual(result.outcome, OUTCOME_ACTIVATED)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_reset)
        self.assertIsNone(state.suspension_reason)
        self.assertEqual(len(push.sent), 1)
        self.assertEqual(push.sent[0][0], "owner-1")
        self.assertIn("https://example.com/billing/portal", push.sent[0][1])

    def test_activation_without_portal_url_still_sends_message(self):
        # portal_link_provider未接続(None)でも送信自体はブロックしない
        # (portal-session-provider-design.md 4節2.のフォールバック文言に委ねる)。
        state = _store(suspension_reason="trial_unselected")
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(state, push)

        self.assertEqual(result.outcome, OUTCOME_ACTIVATED)
        self.assertTrue(result.notified)
        self.assertNotIn("マイページ", push.sent[0][1])

    def test_cancelled_store_reactivation_sends_message_and_clears_suspension(self):
        # subscription-cancellation-flow-design.md「未確定事項・残課題」で指摘されていた、
        # suspension_reason="cancelled"の店舗が再契約しても再開通知が届かない欠落の解消確認。
        state = _store(suspension_reason="cancelled")
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(state, push)

        self.assertEqual(result.outcome, OUTCOME_ACTIVATED)
        self.assertTrue(result.notified)
        self.assertTrue(result.state_reset)
        self.assertIsNone(state.suspension_reason)
        self.assertEqual(len(push.sent), 1)

    def test_webhook_replay_after_activation_is_noop(self):
        state = _store(suspension_reason=None)
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(state, push)

        self.assertEqual(result.outcome, OUTCOME_ALREADY_ACTIVE)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(len(push.sent), 0)

    def test_dunning_suspended_store_is_untouched(self):
        state = _store(suspension_reason="payment_failed")
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(state, push)

        self.assertEqual(result.outcome, OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(state.suspension_reason, "payment_failed")
        self.assertEqual(len(push.sent), 0)

    def test_send_failure_leaves_state_unchanged_for_retry(self):
        state = _store(suspension_reason="trial_unselected")
        result = handle_subscription_activated(state, AlwaysFailingLinePushClient())

        self.assertEqual(result.outcome, OUTCOME_SEND_FAILED)
        self.assertFalse(result.notified)
        self.assertFalse(result.state_reset)
        self.assertEqual(state.suspension_reason, "trial_unselected")

    def test_applies_when_event_time_newer_than_recorded(self):
        # 正常順序の回帰確認: event_time指定でも新しいイベントなら従来通り適用される。
        state = _store(
            suspension_reason="cancelled",
            last_subscription_event_time=datetime(2026, 9, 20, 9, 0),
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(
            state, push, event_time=datetime(2026, 9, 20, 10, 0)
        )

        self.assertEqual(result.outcome, OUTCOME_ACTIVATED)
        self.assertTrue(result.notified)
        self.assertIsNone(state.suspension_reason)
        self.assertEqual(state.last_subscription_event_time, datetime(2026, 9, 20, 10, 0))

    def test_skips_when_reactivation_event_is_stale_after_later_cancellation(self):
        # 遅延配信ケース: 解約確定(customer.subscription.deleted、event_time 10:00)を
        # 既に反映済みの状態に、それより前(9:00)に発生していたはずの
        # subscription_activatedが遅れて届いても、既に確定済みの解約を誤って解除しない。
        state = _store(
            suspension_reason="cancelled",
            last_subscription_event_time=datetime(2026, 9, 20, 10, 0),
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(
            state, push, event_time=datetime(2026, 9, 20, 9, 0)
        )

        self.assertEqual(result.outcome, OUTCOME_STALE_EVENT)
        self.assertTrue(result.stale)
        self.assertFalse(result.notified)
        self.assertEqual(state.suspension_reason, "cancelled")
        self.assertEqual(len(push.sent), 0)

    def test_applies_unconditionally_when_event_time_omitted(self):
        # event_time省略時(呼び出し側が未対応)は従来通り無条件適用する後方互換。
        state = _store(
            suspension_reason="cancelled",
            last_subscription_event_time=datetime(2026, 9, 20, 10, 0),
        )
        push = InMemoryLinePushClient()
        result = handle_subscription_activated(state, push)

        self.assertEqual(result.outcome, OUTCOME_ACTIVATED)
        self.assertTrue(result.notified)
        self.assertIsNone(state.suspension_reason)


if __name__ == "__main__":
    unittest.main()
