#!/usr/bin/env python3
"""trial_end_scheduler.pyの単体テスト。
trial-end-scheduler-design.md(フェーズ133)の抽出条件・メッセージ整形・送信配線に
沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import (  # noqa: E402
    PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER,
    build_start_checkout_postback_data,
)
from trial_end_scheduler import (  # noqa: E402
    ADDITIONAL_MINUTES_PER_UNIT,
    BASE_MINUTES_PER_GENERATION,
    InMemoryLinePushClient,
    LinePushDeliveryError,
    TrialUserState,
    build_trial_end_notification_flex_message,
    build_trial_user_states,
    estimate_trial_minutes_saved,
    format_minutes_saved_line,
    select_due_trial_end_notifications,
    send_trial_end_notifications,
)

_NOW = datetime(2026, 8, 28, 4, 0, 0)


class SelectDueTrialEndNotificationsTest(unittest.TestCase):
    def test_selects_user_at_exactly_14_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=14))]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])

    def test_selects_user_past_14_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=30))]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])

    def test_excludes_user_before_14_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=13))]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_user_without_trial_start_at(self):
        users = [TrialUserState(user_id="u1", trial_start_at=None)]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_already_notified_user(self):
        users = [
            TrialUserState(
                user_id="u1",
                trial_start_at=_NOW - timedelta(days=20),
                trial_end_notified_at=_NOW - timedelta(days=1),
            )
        ]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_excludes_already_upgraded_user(self):
        users = [
            TrialUserState(
                user_id="u1",
                trial_start_at=_NOW - timedelta(days=20),
                upgraded_at=_NOW - timedelta(days=2),
            )
        ]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual(due, [])

    def test_preserves_input_order_among_multiple_due_users(self):
        users = [
            TrialUserState(user_id="u2", trial_start_at=_NOW - timedelta(days=15)),
            TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=14)),
        ]

        due = select_due_trial_end_notifications(users, _NOW)

        self.assertEqual([u.user_id for u in due], ["u2", "u1"])

    def test_custom_trial_period_days(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=7))]

        due = select_due_trial_end_notifications(users, _NOW, trial_period_days=7)

        self.assertEqual([u.user_id for u in due], ["u1"])


class BuildTrialEndNotificationFlexMessageTest(unittest.TestCase):
    def test_includes_generation_count_in_body_text(self):
        contents = build_trial_end_notification_flex_message(generation_count=8)

        body_texts = [
            block["text"]
            for block in contents["body"]["contents"]
            if block["type"] == "text"
        ]
        self.assertTrue(any("8回" in text for text in body_texts))

    def test_footer_has_one_button_per_plan_with_plan_specific_postback_data(self):
        """checkout-session-plan-selection-design.md 3節・フェーズ180対応。"""
        contents = build_trial_end_notification_flex_message(generation_count=0)

        buttons = contents["footer"]["contents"]
        self.assertEqual(len(buttons), len(PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER))
        for button, plan in zip(buttons, PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER):
            self.assertEqual(button["action"]["type"], "postback")
            self.assertEqual(button["action"]["data"], build_start_checkout_postback_data(plan))
            self.assertIn(plan, button["action"]["label"])

    def test_includes_minutes_saved_estimate_using_unit_count(self):
        """content-generation-time-estimate.md(フェーズ192)。"""
        contents = build_trial_end_notification_flex_message(generation_count=3, unit_count=4)

        body_texts = [
            block["text"]
            for block in contents["body"]["contents"]
            if block["type"] == "text"
        ]
        expected_minutes = estimate_trial_minutes_saved(3, 4)
        self.assertTrue(any(f"約{expected_minutes}分" in text for text in body_texts))

    def test_minutes_saved_defaults_to_zero_unit_count_when_omitted(self):
        contents = build_trial_end_notification_flex_message(generation_count=3)

        body_texts = [
            block["text"]
            for block in contents["body"]["contents"]
            if block["type"] == "text"
        ]
        expected_minutes = BASE_MINUTES_PER_GENERATION * 3
        self.assertTrue(any(f"約{expected_minutes}分" in text for text in body_texts))


class EstimateTrialMinutesSavedTest(unittest.TestCase):
    """content-generation-time-estimate.md「試算(仮置き)」節の式の単体テスト
    (フェーズ192)。"""

    def test_single_generation_single_unit_matches_flat_estimate(self):
        # 1回の生成が常に1台のみの場合、1回あたり13分(8+5)の仮置き値と一致する。
        self.assertEqual(estimate_trial_minutes_saved(1, 1), 13)

    def test_scales_with_generation_count_and_unit_count_independently(self):
        self.assertEqual(
            estimate_trial_minutes_saved(3, 5),
            BASE_MINUTES_PER_GENERATION * 3 + ADDITIONAL_MINUTES_PER_UNIT * 5,
        )

    def test_zero_generations_and_units_is_zero(self):
        self.assertEqual(estimate_trial_minutes_saved(0, 0), 0)


class FormatMinutesSavedLineTest(unittest.TestCase):
    def test_line_starts_with_bullet_and_contains_estimate(self):
        line = format_minutes_saved_line(2, 3)

        self.assertTrue(line.startswith("・浮いた作業時間の目安"))
        self.assertIn(f"約{estimate_trial_minutes_saved(2, 3)}分", line)


class SendTrialEndNotificationsTest(unittest.TestCase):
    class _InMemoryProfileStoreStub:
        def __init__(self) -> None:
            self.notified_at: dict[str, datetime] = {}

        def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
            self.notified_at[user_id] = notified_at

    def test_sends_to_due_users_and_writes_notified_at(self):
        users = [
            TrialUserState(
                user_id="u1", trial_start_at=_NOW - timedelta(days=14),
                trial_generation_count=3, trial_unit_count=4,
            ),
            TrialUserState(user_id="u2", trial_start_at=_NOW - timedelta(days=1)),
        ]
        profile_store = self._InMemoryProfileStoreStub()
        push = InMemoryLinePushClient()

        result = send_trial_end_notifications(users, _NOW, profile_store, push)

        self.assertEqual(result.sent, ["u1"])
        self.assertEqual(result.failed, [])
        self.assertEqual(profile_store.notified_at, {"u1": _NOW})
        self.assertEqual(len(push.sent), 1)
        sent_user_id, alt_text, contents = push.sent[0]
        self.assertEqual(sent_user_id, "u1")
        self.assertIn("トライアル", alt_text)
        body_texts = [
            block["text"]
            for block in contents["body"]["contents"]
            if block["type"] == "text"
        ]
        self.assertTrue(
            any(f"約{estimate_trial_minutes_saved(3, 4)}分" in text for text in body_texts)
        )

    def test_delivery_failure_does_not_write_notified_at_and_is_reported_as_failed(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=14))]
        profile_store = self._InMemoryProfileStoreStub()

        class _FailingPushClient:
            def send_flex_message(self, user_id, alt_text, contents):
                raise LinePushDeliveryError("boom")

        result = send_trial_end_notifications(users, _NOW, profile_store, _FailingPushClient())

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, ["u1"])
        self.assertEqual(profile_store.notified_at, {})

    def test_no_due_users_sends_nothing(self):
        users = [TrialUserState(user_id="u1", trial_start_at=_NOW - timedelta(days=1))]
        profile_store = self._InMemoryProfileStoreStub()
        push = InMemoryLinePushClient()

        result = send_trial_end_notifications(users, _NOW, profile_store, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])
        self.assertEqual(push.sent, [])


class BuildTrialUserStatesTest(unittest.TestCase):
    def test_builds_state_from_existing_profile(self) -> None:
        from user_id_linking import InMemoryUserProfileStore, UserProfile

        store = InMemoryUserProfileStore()
        store.save(
            "u1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=_NOW,
                trial_start_at=_NOW - timedelta(days=20),
                trial_generation_count=3,
                trial_unit_count=4,
            ),
        )

        states = build_trial_user_states(store, ["u1"])

        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].user_id, "u1")
        self.assertEqual(states[0].trial_start_at, _NOW - timedelta(days=20))
        self.assertIsNone(states[0].trial_end_notified_at)
        self.assertIsNone(states[0].upgraded_at)
        self.assertEqual(states[0].trial_generation_count, 3)
        self.assertEqual(states[0].trial_unit_count, 4)

    def test_unknown_user_id_becomes_trial_not_started_state(self) -> None:
        from user_id_linking import InMemoryUserProfileStore

        store = InMemoryUserProfileStore()

        states = build_trial_user_states(store, ["ghost"])

        self.assertEqual(
            states, [TrialUserState(user_id="ghost", trial_start_at=None)]
        )


class StripeWebhookUpgradedAtToTrialEndSchedulerWiringTest(unittest.TestCase):
    """stripe_webhook.handle_checkout_session_completed()が書き込むupgraded_atと、
    trial_end_scheduler.select_due_trial_end_notifications()が読むupgraded_atが、
    build_trial_user_states()を介して実際に同一のInMemoryUserProfileStore経由で
    つながることを確認する(trial-end-scheduler-design.md 2節の残課題)。

    これまでTrialUserStateはselect_due_trial_end_notifications()側のテストでも
    stripe_webhook.py側のテストでも手動構築されるのみで、両モジュールが
    UserProfileStoreProtocol実装を介して連携することを確認するテストが存在しなかった
    (course-set-pashaフェーズ158のStripeWebhookUpgradedAtToTrialEndSchedulerWiring
    Testと同種の配線漏れの観点)。"""

    def test_checkout_completion_excludes_user_from_next_trial_end_scan(self) -> None:
        from stripe_webhook import handle_checkout_session_completed
        from user_id_linking import InMemoryUserProfileStore, UserProfile

        store = InMemoryUserProfileStore()
        store.save(
            "u1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=_NOW,
                trial_start_at=_NOW - timedelta(days=20),
            ),
        )

        # 決済完了(checkout.session.completed)により、同一storeへupgraded_atが
        # 書き込まれる(stripe_webhook.py handle_checkout_session_completed())。
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {"client_reference_id": "u1", "customer": "cus_1"}},
        }
        result = handle_checkout_session_completed(event, store, now=_NOW)
        self.assertTrue(result.upgraded_at_written)

        # 同じstoreをbuild_trial_user_states()経由で読み取ると、trial_start_atから
        # 20日経過(条件Bを満たす)にもかかわらず、upgraded_at設定済みのため対象から外れる。
        states = build_trial_user_states(store, ["u1"])
        due = select_due_trial_end_notifications(states, _NOW)

        self.assertEqual(due, [])

    def test_user_without_checkout_completion_remains_due(self) -> None:
        from user_id_linking import InMemoryUserProfileStore, UserProfile

        store = InMemoryUserProfileStore()
        store.save(
            "u1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=_NOW,
                trial_start_at=_NOW - timedelta(days=20),
            ),
        )

        states = build_trial_user_states(store, ["u1"])
        due = select_due_trial_end_notifications(states, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])


class ConditionAWriteExcludesFromTrialEndSchedulerWiringTest(unittest.TestCase):
    """process_memo_event()の条件A(生成回数10回到達、trial-end-condition-a-cta-design.md、
    フェーズ137)が書き込むtrial_end_notified_atと、本モジュールの
    select_due_trial_end_notifications()(条件B、期間到達)が読むtrial_end_notified_atが、
    build_trial_user_states()を介して実際に同一のInMemoryUserProfileStore経由でつながり、
    「いずれか早い方で1回のみ送信」(trial-end-notification-design.md 2節)が(A)(B)間で
    実際に成立することを確認する(trial-end-scheduler-design.md 2節の記載漏れ、
    StripeWebhookUpgradedAtToTrialEndSchedulerWiringTestと同種の観点)。"""

    def test_tenth_generation_excludes_user_from_next_trial_end_scan(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
        from validate_test_cases import TEST_CASES  # noqa: E402

        from cloud_function_webhook import (
            InMemoryReplyClient,
            TRIAL_GENERATION_LIMIT,
            process_memo_event,
        )
        from user_id_linking import InMemoryUserProfileStore, UserProfile

        class _FixtureLlmClient:
            def generate(self, memo_text, retry_context=None):
                return dict(TEST_CASES["G1_basic"])

        # trial_start_atは13日前とし、条件B(14日経過)はまだ満たさない状態から出発する
        # (条件Aの効果だけを切り分けて確認するため)。
        trial_start_at = _NOW - timedelta(days=13)
        store = InMemoryUserProfileStore()
        store.save(
            "u1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=trial_start_at,
                trial_start_at=trial_start_at,
                trial_generation_count=TRIAL_GENERATION_LIMIT - 1,
            ),
        )
        reply_client = InMemoryReplyClient()
        event = {
            "replyToken": "rt-1",
            "message": {"type": "text", "text": "壁掛け型2.2kW、フィルター清掃"},
            "source": {"userId": "u1"},
        }

        # 10回目の生成完了(process_memo_event、cloud_function_webhook.py)により、
        # 同一storeへtrial_end_notified_atが書き込まれる。
        result = process_memo_event(
            event, _FixtureLlmClient(), reply_client, profile_store=store, now=_NOW,
        )
        self.assertIsNotNone(store.get("u1").trial_end_notified_at)
        self.assertTrue(result.reply_sent)

        # trial_start_atから20日後(条件Bの14日を満たす時点)にbuild_trial_user_states()
        # 経由で同じstoreを読み取っても、条件A側で既にtrial_end_notified_atが設定済み
        # のため、日次スケジューラ(条件B)の送信対象からは除外される(二重送信しない)。
        later = trial_start_at + timedelta(days=20)
        states = build_trial_user_states(store, ["u1"])
        due = select_due_trial_end_notifications(states, later)

        self.assertEqual(due, [])

    def test_ninth_generation_still_leaves_user_due_once_period_elapses(self) -> None:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
        from validate_test_cases import TEST_CASES  # noqa: E402

        from cloud_function_webhook import (
            InMemoryReplyClient,
            TRIAL_GENERATION_LIMIT,
            process_memo_event,
        )
        from user_id_linking import InMemoryUserProfileStore, UserProfile

        class _FixtureLlmClient:
            def generate(self, memo_text, retry_context=None):
                return dict(TEST_CASES["G1_basic"])

        trial_start_at = _NOW - timedelta(days=13)
        store = InMemoryUserProfileStore()
        store.save(
            "u1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=trial_start_at,
                trial_start_at=trial_start_at,
                trial_generation_count=TRIAL_GENERATION_LIMIT - 2,
            ),
        )
        reply_client = InMemoryReplyClient()
        event = {
            "replyToken": "rt-1",
            "message": {"type": "text", "text": "壁掛け型2.2kW、フィルター清掃"},
            "source": {"userId": "u1"},
        }

        # 9回目の生成完了では条件Aは発火せず、trial_end_notified_atは未設定のまま。
        process_memo_event(
            event, _FixtureLlmClient(), reply_client, profile_store=store, now=_NOW,
        )
        self.assertIsNone(store.get("u1").trial_end_notified_at)

        # 条件B(14日経過)を満たす時点になれば、条件Aが未発火のため通常通り送信対象になる。
        later = trial_start_at + timedelta(days=20)
        states = build_trial_user_states(store, ["u1"])
        due = select_due_trial_end_notifications(states, later)

        self.assertEqual([u.user_id for u in due], ["u1"])


if __name__ == "__main__":
    unittest.main()
