#!/usr/bin/env python3
"""store_deletion_execution.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_store_deletion_execution -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from store_deletion_candidate import DELETION_CANDIDATE_DELAY, StoreDeletionCandidateState
from store_deletion_execution import (
    SUBCOLLECTION_DELETION_ORDER,
    DeletionNotConfirmedError,
    InMemoryDeletionTargetStore,
    InMemorySubcollectionDeleter,
    execute_store_deletion,
    render_deletion_execution_review_report,
)

FINAL_SENT_AT = datetime(2026, 8, 20, 10, 0)
DUE_AT = FINAL_SENT_AT + DELETION_CANDIDATE_DELAY


def _state(**overrides) -> StoreDeletionCandidateState:
    defaults = dict(
        store_id="store-1",
        dormant_renotify_count=3,
        dormant_final_renotify_sent_at=FINAL_SENT_AT,
        suspension_reason="trial_unselected",
        stripe_customer_id=None,
        store_deletion_confirmation_sent_at=None,
        store_deletion_confirmation_unreachable_at=None,
        store_deletion_confirmation_unreachable_reason=None,
    )
    defaults.update(overrides)
    return StoreDeletionCandidateState(**defaults)


def _subcollections(document_counts: dict[str, int] | None = None):
    document_counts = document_counts or {}
    return [
        InMemorySubcollectionDeleter(
            name=name, document_count=document_counts.get(name, 0)
        )
        for name in SUBCOLLECTION_DELETION_ORDER
    ]


class ExecuteStoreDeletionTests(unittest.TestCase):
    def test_raises_when_not_confirmed_by_owner(self) -> None:
        store = InMemoryDeletionTargetStore(store_id="store-1")
        subcollections = _subcollections()
        with self.assertRaises(DeletionNotConfirmedError):
            execute_store_deletion(
                "store-1", store, subcollections, confirmed_by_owner=False
            )
        # 例外発生時は一切削除が行われていないこと。
        self.assertFalse(store.deleted)
        self.assertTrue(all(not d.deleted for d in subcollections))

    def test_deletes_subcollections_in_order_then_parent(self) -> None:
        store = InMemoryDeletionTargetStore(store_id="store-1")
        subcollections = _subcollections(
            {"bookingSlots": 2, "conversations": 5, "escalationWindows": 1}
        )
        result = execute_store_deletion(
            "store-1", store, subcollections, confirmed_by_owner=True
        )

        self.assertTrue(store.deleted)
        self.assertTrue(result.store_document_deleted)
        self.assertEqual(result.completed_subcollections, SUBCOLLECTION_DELETION_ORDER)
        self.assertTrue(result.is_fully_deleted)
        self.assertEqual(result.deleted_document_counts["bookingSlots"], 2)
        self.assertEqual(result.deleted_document_counts["conversations"], 5)
        self.assertEqual(result.deleted_document_counts["escalationWindows"], 1)
        self.assertEqual(result.deleted_document_counts["notificationLogEntries"], 0)
        for deleter in subcollections:
            self.assertTrue(deleter.deleted)

    def test_rejects_subcollections_given_in_wrong_order(self) -> None:
        store = InMemoryDeletionTargetStore(store_id="store-1")
        subcollections = list(reversed(_subcollections()))
        with self.assertRaises(ValueError):
            execute_store_deletion(
                "store-1", store, subcollections, confirmed_by_owner=True
            )
        self.assertFalse(store.deleted)


class RenderDeletionExecutionReviewReportTests(unittest.TestCase):
    def test_classifies_candidates_into_three_sections(self) -> None:
        states = [
            # 1. 最終確認送信済み・未応答
            _state(store_id="store-sent", store_deletion_confirmation_sent_at=DUE_AT),
            # 2. 連絡不能
            _state(
                store_id="store-unreachable",
                store_deletion_confirmation_sent_at=None,
                store_deletion_confirmation_unreachable_at=DUE_AT,
                store_deletion_confirmation_unreachable_reason="line_push_delivery_failed",
            ),
            # 3. 最終確認未送信の新規候補
            _state(store_id="store-new"),
        ]
        report = render_deletion_execution_review_report(
            states, DUE_AT + timedelta(days=1)
        )

        self.assertIn("1. 最終確認送信済み・未応答: 1件", report)
        self.assertIn("store-sent", report)
        self.assertIn("2. 連絡不能", report)
        self.assertIn("store-unreachable", report)
        self.assertIn("3. (参考)最終確認未送信の新規削除候補: 1件", report)
        self.assertIn("本リストは自動削除の対象ではありません", report)
        self.assertIn("confirmed_by_owner=True", report)

    def test_empty_states_render_zero_counts(self) -> None:
        report = render_deletion_execution_review_report([], DUE_AT)
        self.assertIn("1. 最終確認送信済み・未応答: 0件", report)
        self.assertIn("2. 連絡不能", report)
        self.assertIn("0件", report)


if __name__ == "__main__":
    unittest.main()
