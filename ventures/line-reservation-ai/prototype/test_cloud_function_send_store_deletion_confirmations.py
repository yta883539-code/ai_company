#!/usr/bin/env python3
"""cloud_function_send_store_deletion_confirmations.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_cloud_function_send_store_deletion_confirmations -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError
from cloud_function_send_store_deletion_confirmations import (
    StoreDeletionState,
    send_store_deletion_confirmations,
)
from store_deletion_candidate import DELETION_CANDIDATE_DELAY

FINAL_SENT_AT = datetime(2026, 8, 20, 10, 0)
DUE_AT = FINAL_SENT_AT + DELETION_CANDIDATE_DELAY


class FailingLinePushClient:
    """指定したuser_idへの送信を常に失敗させる検証用クライアント。"""

    def __init__(self, failing_user_ids: set[str]) -> None:
        self.failing_user_ids = failing_user_ids
        self.sent: list[tuple[str, str]] = []

    def send_message(self, user_id: str, text: str) -> None:
        if user_id in self.failing_user_ids:
            raise LinePushDeliveryError("simulated failure")
        self.sent.append((user_id, text))


def _store(**overrides) -> StoreDeletionState:
    defaults = dict(
        store_id="store-1",
        dormant_renotify_count=3,
        dormant_final_renotify_sent_at=FINAL_SENT_AT,
        owner_line_user_id="owner-1",
        suspension_reason="trial_unselected",
    )
    defaults.update(overrides)
    return StoreDeletionState(**defaults)


class SendStoreDeletionConfirmationsTests(unittest.TestCase):
    def test_not_yet_candidate_nothing_sent(self):
        store = _store()
        push = InMemoryLinePushClient()
        result = send_store_deletion_confirmations(
            [store], DUE_AT - timedelta(days=1), push
        )
        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, [])
        self.assertIsNone(store.store_deletion_confirmation_sent_at)

    def test_sends_confirmation_and_records_sent_at(self):
        store = _store()
        push = InMemoryLinePushClient()
        result = send_store_deletion_confirmations([store], DUE_AT, push)
        self.assertEqual(result.sent, ["store-1"])
        self.assertEqual(result.marked_unreachable, [])
        self.assertEqual(store.store_deletion_confirmation_sent_at, DUE_AT)
        self.assertEqual(len(push.sent), 1)
        self.assertEqual(push.sent[0][0], "owner-1")

    def test_idempotent_second_run_does_not_resend(self):
        store = _store()
        push = InMemoryLinePushClient()
        send_store_deletion_confirmations([store], DUE_AT, push)
        result = send_store_deletion_confirmations([store], DUE_AT + timedelta(days=1), push)
        self.assertEqual(result.sent, [])
        self.assertEqual(len(push.sent), 1)

    def test_missing_owner_line_user_id_marks_unreachable(self):
        store = _store(owner_line_user_id=None)
        push = InMemoryLinePushClient()
        result = send_store_deletion_confirmations([store], DUE_AT, push)
        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, ["store-1"])
        self.assertEqual(store.store_deletion_confirmation_unreachable_at, DUE_AT)
        self.assertIsNone(store.store_deletion_confirmation_sent_at)

    def test_push_failure_marks_unreachable_without_retalling_history(self):
        store = _store()
        push = FailingLinePushClient(failing_user_ids={"owner-1"})
        result = send_store_deletion_confirmations([store], DUE_AT, push)
        self.assertEqual(result.sent, [])
        self.assertEqual(result.marked_unreachable, ["store-1"])
        self.assertEqual(store.store_deletion_confirmation_unreachable_at, DUE_AT)

    def test_unreachable_store_remains_candidate_for_retry_after_recovery(self):
        store = _store(owner_line_user_id=None)
        push = InMemoryLinePushClient()
        send_store_deletion_confirmations([store], DUE_AT, push)
        store.owner_line_user_id = "owner-1"
        result = send_store_deletion_confirmations([store], DUE_AT + timedelta(days=1), push)
        self.assertEqual(result.sent, ["store-1"])
        self.assertEqual(len(push.sent), 1)

    def test_non_candidate_store_is_not_sent_to(self):
        candidate = _store(store_id="store-a")
        non_candidate = _store(store_id="store-b", dormant_renotify_count=1)
        push = InMemoryLinePushClient()
        result = send_store_deletion_confirmations([candidate, non_candidate], DUE_AT, push)
        self.assertEqual(result.sent, ["store-a"])
        self.assertEqual(len(push.sent), 1)


if __name__ == "__main__":
    unittest.main()
