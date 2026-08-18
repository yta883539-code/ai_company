#!/usr/bin/env python3
"""cloud_function_send_dunning_notifications.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_cloud_function_send_dunning_notifications -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError
from cloud_function_send_dunning_notifications import (
    StoreDunningState,
    select_due_dunning_events,
    send_dunning_notifications,
)
from dunning_notification_scheduler import DUNNING_CONFIG_A_7DAYS, DUNNING_CONFIG_B_14DAYS


class FailingLinePushClient:
    """指定したuser_idへの送信を常に失敗させる検証用クライアント。"""

    def __init__(self, failing_user_ids: set[str]) -> None:
        self.failing_user_ids = failing_user_ids
        self.sent: list[tuple[str, str]] = []

    def send_message(self, user_id: str, text: str) -> None:
        if user_id in self.failing_user_ids:
            raise LinePushDeliveryError("simulated failure")
        self.sent.append((user_id, text))


def _store(**overrides) -> StoreDunningState:
    defaults = dict(
        store_id="store-1",
        owner_line_user_id="owner-1",
        payment_failure_detected_at=datetime(2026, 8, 17, 10, 0),
        config=DUNNING_CONFIG_A_7DAYS,
        payment_page_url="https://example.com/billing",
    )
    defaults.update(overrides)
    return StoreDunningState(**defaults)


class SelectDueDunningEventsTests(unittest.TestCase):
    def test_not_in_dunning_returns_empty(self):
        state = _store(payment_failure_detected_at=None)
        self.assertEqual(select_due_dunning_events(state, datetime(2026, 8, 20)), [])

    def test_only_events_up_to_now_are_due(self):
        state = _store()
        due = select_due_dunning_events(state, datetime(2026, 8, 17, 10, 0))
        self.assertEqual([e.event_type for e in due], ["detected"])

    def test_all_due_events_returned_when_none_sent(self):
        state = _store()
        due = select_due_dunning_events(state, datetime(2026, 8, 25))
        self.assertEqual([e.event_type for e in due], ["detected", "reminder", "suspended"])

    def test_already_sent_events_excluded(self):
        state = _store(sent_event_keys={"detected"})
        due = select_due_dunning_events(state, datetime(2026, 8, 21, 10, 0))
        self.assertEqual([e.event_type for e in due], ["reminder"])
        self.assertEqual(due[0].label, "final")


class SendDunningNotificationsTests(unittest.TestCase):
    def test_sends_detected_message_and_records_idempotency_key(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = send_dunning_notifications([state], datetime(2026, 8, 17, 10, 0), push)
        self.assertEqual(result.sent, [("store-1", "detected")])
        self.assertEqual(result.failed, [])
        self.assertEqual(len(push.sent), 1)
        self.assertEqual(push.sent[0][0], "owner-1")
        self.assertIn("7日以内にお支払い方法", push.sent[0][1])
        self.assertIn("detected", state.sent_event_keys)

    def test_second_run_at_same_time_does_not_resend(self):
        state = _store()
        push = InMemoryLinePushClient()
        send_dunning_notifications([state], datetime(2026, 8, 17, 10, 0), push)
        result = send_dunning_notifications([state], datetime(2026, 8, 17, 10, 0), push)
        self.assertEqual(result.sent, [])
        self.assertEqual(len(push.sent), 1)

    def test_multiple_due_events_sent_in_chronological_order(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = send_dunning_notifications([state], datetime(2026, 8, 25), push)
        self.assertEqual(result.sent, [("store-1", "detected"), ("store-1", "reminder:final"), ("store-1", "suspended")])
        self.assertEqual(state.suspension_reason, "payment_failed")

    def test_config_b_sends_midpoint_before_final(self):
        state = _store(config=DUNNING_CONFIG_B_14DAYS)
        push = InMemoryLinePushClient()
        result = send_dunning_notifications([state], datetime(2026, 9, 1), push)
        keys = [key for _, key in result.sent]
        self.assertEqual(keys, ["detected", "reminder:midpoint", "reminder:final", "suspended"])

    def test_failure_stops_that_store_and_leaves_later_events_unsent(self):
        state = _store()
        push = FailingLinePushClient(failing_user_ids={"owner-1"})
        result = send_dunning_notifications([state], datetime(2026, 8, 25), push)
        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [("store-1", "detected")])
        self.assertEqual(state.sent_event_keys, set())
        self.assertIsNone(state.suspension_reason)

    def test_failure_on_second_event_still_records_first_as_sent(self):
        # 検知時は成功、終了直前リマインドで失敗する状況を再現するため、
        # 1回目に成功させてから2回目起動で失敗クライアントに切り替える。
        state = _store()
        ok_push = InMemoryLinePushClient()
        send_dunning_notifications([state], datetime(2026, 8, 17, 10, 0), ok_push)
        self.assertIn("detected", state.sent_event_keys)

        failing_push = FailingLinePushClient(failing_user_ids={"owner-1"})
        result = send_dunning_notifications([state], datetime(2026, 8, 25), failing_push)
        self.assertEqual(result.failed, [("store-1", "reminder:final")])
        self.assertNotIn("suspended", state.sent_event_keys)

    def test_tone_is_applied_from_store_setting(self):
        state = _store(message_tone="casual")
        push = InMemoryLinePushClient()
        send_dunning_notifications([state], datetime(2026, 8, 17, 10, 0), push)
        self.assertIn("🙏", push.sent[0][1])

    def test_multiple_stores_are_independent(self):
        store_a = _store(store_id="store-a", owner_line_user_id="owner-a")
        store_b = _store(
            store_id="store-b",
            owner_line_user_id="owner-b",
            payment_failure_detected_at=datetime(2026, 8, 18, 9, 0),
        )
        push = InMemoryLinePushClient()
        result = send_dunning_notifications([store_a, store_b], datetime(2026, 8, 18, 9, 0), push)
        self.assertEqual(
            sorted(result.sent), [("store-a", "detected"), ("store-b", "detected")]
        )


if __name__ == "__main__":
    unittest.main()
