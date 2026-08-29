#!/usr/bin/env python3
"""cloud_function_send_dormant_notifications.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_cloud_function_send_dormant_notifications -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError
from cloud_function_send_dormant_notifications import (
    StoreDormantState,
    send_dormant_notifications,
)
from dormant_mode_scheduler import GRACE_PERIOD_DAYS

REPORT_SENT_AT = datetime(2026, 8, 20, 10, 0)
TRANSITIONED_AT = REPORT_SENT_AT + timedelta(days=GRACE_PERIOD_DAYS)


class FailingLinePushClient:
    """指定したuser_idへの送信を常に失敗させる検証用クライアント。"""

    def __init__(self, failing_user_ids: set[str]) -> None:
        self.failing_user_ids = failing_user_ids
        self.sent: list[tuple[str, str]] = []

    def send_message(self, user_id: str, text: str) -> None:
        if user_id in self.failing_user_ids:
            raise LinePushDeliveryError("simulated failure")
        self.sent.append((user_id, text))


def _store(**overrides) -> StoreDormantState:
    defaults = dict(
        store_id="store-1",
        owner_line_user_id="owner-1",
        payment_page_url="https://example.com/billing",
        trial_end_report_sent_at=REPORT_SENT_AT,
    )
    defaults.update(overrides)
    return StoreDormantState(**defaults)


class SendDormantNotificationsTests(unittest.TestCase):
    def test_before_grace_period_ends_nothing_sent(self):
        state = _store()
        push = InMemoryLinePushClient()
        result = send_dormant_notifications([state], REPORT_SENT_AT, push)
        self.assertEqual(result.sent, [])
        self.assertIsNone(state.dormant_transitioned_at)

    def test_sends_transitioned_message_and_records_state(self):
        state = _store(message_tone="casual")
        push = InMemoryLinePushClient()
        result = send_dormant_notifications([state], TRANSITIONED_AT, push)
        self.assertEqual(result.sent, [("store-1", "transitioned")])
        self.assertEqual(result.failed, [])
        self.assertEqual(len(push.sent), 1)
        self.assertEqual(push.sent[0][0], "owner-1")
        self.assertIn("休止モードへの移行", push.sent[0][1])
        self.assertIn("🙆", push.sent[0][1])
        self.assertEqual(state.dormant_transitioned_at, TRANSITIONED_AT)

    def test_second_run_at_same_time_does_not_resend(self):
        state = _store()
        push = InMemoryLinePushClient()
        send_dormant_notifications([state], TRANSITIONED_AT, push)
        result = send_dormant_notifications([state], TRANSITIONED_AT, push)
        self.assertEqual(result.sent, [])
        self.assertEqual(len(push.sent), 1)

    def test_renotify_events_progress_one_at_a_time(self):
        state = _store()
        push = InMemoryLinePushClient()
        send_dormant_notifications([state], TRANSITIONED_AT, push)

        result = send_dormant_notifications(
            [state], TRANSITIONED_AT + timedelta(days=90), push
        )
        # 1回の起動につき最大1件(select_due_dormant_events()の既存仕様どおり)。
        self.assertEqual(result.sent, [("store-1", "renotify:2nd")])
        self.assertEqual(state.dormant_renotify_count, 1)

        result = send_dormant_notifications(
            [state], TRANSITIONED_AT + timedelta(days=90), push
        )
        self.assertEqual(result.sent, [("store-1", "renotify:3rd")])
        self.assertEqual(state.dormant_renotify_count, 2)

        result = send_dormant_notifications(
            [state], TRANSITIONED_AT + timedelta(days=90), push
        )
        self.assertEqual(result.sent, [("store-1", "renotify:final")])
        self.assertEqual(state.dormant_renotify_count, 3)

        # 4回で打ち切り(2節)。以降は何度実行しても送信されない。
        result = send_dormant_notifications(
            [state], TRANSITIONED_AT + timedelta(days=365), push
        )
        self.assertEqual(result.sent, [])

    def test_stripe_customer_id_before_transition_skips_and_leaves_no_state(self):
        state = _store(stripe_customer_id="cus_123")
        push = InMemoryLinePushClient()
        result = send_dormant_notifications([state], TRANSITIONED_AT, push)
        self.assertEqual(result.sent, [])
        self.assertIsNone(state.dormant_transitioned_at)
        self.assertEqual(len(push.sent), 0)

    def test_payment_failed_store_is_excluded(self):
        state = _store(suspension_reason="payment_failed")
        push = InMemoryLinePushClient()
        result = send_dormant_notifications([state], TRANSITIONED_AT, push)
        self.assertEqual(result.sent, [])

    def test_recovered_after_transition_stops_renotify(self):
        state = _store()
        push = InMemoryLinePushClient()
        send_dormant_notifications([state], TRANSITIONED_AT, push)
        state.suspension_reason = None  # subscription_activated Webhookで復旧済み

        result = send_dormant_notifications(
            [state], TRANSITIONED_AT + timedelta(days=90), push
        )
        self.assertEqual(result.sent, [])

    def test_send_failure_leaves_state_unchanged(self):
        state = _store()
        push = FailingLinePushClient(failing_user_ids={"owner-1"})
        result = send_dormant_notifications([state], TRANSITIONED_AT, push)
        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [("store-1", "transitioned")])
        self.assertIsNone(state.dormant_transitioned_at)

        # 送信失敗後、次回起動で改めて送信対象になる(状態未更新のため)。
        ok_push = InMemoryLinePushClient()
        result = send_dormant_notifications([state], TRANSITIONED_AT, ok_push)
        self.assertEqual(result.sent, [("store-1", "transitioned")])
        self.assertEqual(state.dormant_transitioned_at, TRANSITIONED_AT)

    def test_multiple_stores_are_independent(self):
        store_a = _store(store_id="store-a", owner_line_user_id="owner-a")
        store_b = _store(
            store_id="store-b",
            owner_line_user_id="owner-b",
            trial_end_report_sent_at=REPORT_SENT_AT + timedelta(days=1),
        )
        push = InMemoryLinePushClient()
        result = send_dormant_notifications(
            [store_a, store_b], TRANSITIONED_AT + timedelta(days=1), push
        )
        self.assertEqual(
            sorted(result.sent),
            [("store-a", "transitioned"), ("store-b", "transitioned")],
        )


if __name__ == "__main__":
    unittest.main()
