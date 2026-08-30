#!/usr/bin/env python3
"""trial_end_scheduler.pyの単体テスト。
trial-end-scheduler-design.md(フェーズ133)の抽出条件・メッセージ整形・送信配線に
沿った挙動を確認する。"""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import START_CHECKOUT_POSTBACK_DATA  # noqa: E402
from trial_end_scheduler import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
    TrialUserState,
    build_trial_end_notification_flex_message,
    build_trial_user_states,
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

    def test_footer_button_uses_start_checkout_postback_data(self):
        contents = build_trial_end_notification_flex_message(generation_count=0)

        button = contents["footer"]["contents"][0]
        self.assertEqual(button["action"]["type"], "postback")
        self.assertEqual(button["action"]["data"], START_CHECKOUT_POSTBACK_DATA)


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
                trial_generation_count=3,
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
            ),
        )

        states = build_trial_user_states(store, ["u1"])

        self.assertEqual(len(states), 1)
        self.assertEqual(states[0].user_id, "u1")
        self.assertEqual(states[0].trial_start_at, _NOW - timedelta(days=20))
        self.assertIsNone(states[0].trial_end_notified_at)
        self.assertIsNone(states[0].upgraded_at)
        self.assertEqual(states[0].trial_generation_count, 3)

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

        # checkout.session.completedを一度も受け取っていない(upgraded_at未設定)ユーザーは
        # 引き続き通知対象として残る。
        states = build_trial_user_states(store, ["u1"])
        due = select_due_trial_end_notifications(states, _NOW)

        self.assertEqual([u.user_id for u in due], ["u1"])


if __name__ == "__main__":
    unittest.main()
