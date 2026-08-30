#!/usr/bin/env python3
"""prototype/cloud_function_send_trial_end_reports.py の自動テストスイート
(unittest、外部ライブラリ非依存)。

実行方法: python3 -m unittest test_cloud_function_send_trial_end_reports -v
          (prototype/ディレクトリで実行)
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402
from cloud_function_send_trial_end_reports import (  # noqa: E402
    TrialEndReportCandidate,
    send_trial_end_reports,
)
from engine import NotificationLogAggregator  # noqa: E402

STORE_ID = "store-1"
NOW = datetime(2026, 9, 1, 4, 0, 0)


class _StubWriter:
    def __init__(self) -> None:
        self.sent_at: Optional[datetime] = None
        self.calls = 0

    def mark_trial_end_report_sent(self, now: datetime) -> None:
        self.calls += 1
        if self.sent_at is None:
            self.sent_at = now


def _candidate(writer: _StubWriter, **overrides) -> TrialEndReportCandidate:
    base = dict(
        store_id=STORE_ID,
        trial_start_at=datetime(2026, 8, 15, 10, 0, 0),  # 14日以上前=期間条件で到達
        trial_end_report_sent_at=None,
        booking_count=6,
        auto_handled_inquiry_count=4,
        owner_line_user_id="U-owner-1",
        report_sent_writer=writer,
    )
    base.update(overrides)
    return TrialEndReportCandidate(**base)


class SendTrialEndReportsTests(unittest.TestCase):
    def test_due_by_period_is_sent_and_marked(self):
        writer = _StubWriter()
        push = InMemoryLinePushClient()
        result = send_trial_end_reports([_candidate(writer)], NOW, push)

        self.assertEqual(result.sent, [STORE_ID])
        self.assertEqual(result.failed, [])
        self.assertEqual(writer.sent_at, NOW)
        self.assertEqual(len(push.sent), 1)
        user_id, text = push.sent[0]
        self.assertEqual(user_id, "U-owner-1")
        self.assertIn("・処理した予約件数: 6件", text)
        self.assertIn("・自動対応できたお問い合わせ: 4件", text)

    def test_due_by_booking_count_is_sent(self):
        writer = _StubWriter()
        push = InMemoryLinePushClient()
        candidate = _candidate(
            writer,
            trial_start_at=datetime(2026, 8, 30, 10, 0, 0),  # 期間未到達
            booking_count=20,  # 件数条件で到達
        )
        result = send_trial_end_reports([candidate], NOW, push)

        self.assertEqual(result.sent, [STORE_ID])
        self.assertEqual(writer.sent_at, NOW)

    def test_not_due_is_not_sent(self):
        writer = _StubWriter()
        push = InMemoryLinePushClient()
        candidate = _candidate(
            writer,
            trial_start_at=datetime(2026, 8, 30, 10, 0, 0),
            booking_count=2,
        )
        result = send_trial_end_reports([candidate], NOW, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(push.sent, [])
        self.assertIsNone(writer.sent_at)

    def test_already_sent_is_not_resent(self):
        writer = _StubWriter()
        push = InMemoryLinePushClient()
        candidate = _candidate(
            writer,
            trial_end_report_sent_at=datetime(2026, 8, 20, 4, 0, 0),
        )
        result = send_trial_end_reports([candidate], NOW, push)

        self.assertEqual(result.sent, [])
        self.assertEqual(writer.calls, 0)

    def test_tone_is_taken_from_candidate(self):
        writer = _StubWriter()
        push = InMemoryLinePushClient()
        send_trial_end_reports([_candidate(writer, message_tone="casual")], NOW, push)

        self.assertIn("🎉", push.sent[0][1])

    def test_delivery_failure_leaves_state_untouched_for_retry(self):
        writer = _StubWriter()

        class _FailingClient:
            def send_message(self, user_id: str, text: str) -> None:
                raise LinePushDeliveryError("simulated outage")

        result = send_trial_end_reports([_candidate(writer)], NOW, _FailingClient())

        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [STORE_ID])
        self.assertIsNone(writer.sent_at)
        self.assertEqual(writer.calls, 0)

        # 次回起動(now2)では未送信のまま送信対象として再度拾われる
        push = InMemoryLinePushClient()
        now2 = datetime(2026, 9, 1, 4, 15, 0)
        result2 = send_trial_end_reports([_candidate(writer)], now2, push)
        self.assertEqual(result2.sent, [STORE_ID])
        self.assertEqual(writer.sent_at, now2)

    def test_multiple_candidates_are_independent(self):
        writer_a = _StubWriter()
        writer_b = _StubWriter()
        push = InMemoryLinePushClient()
        candidate_a = _candidate(writer_a, store_id="store-a")
        candidate_b = _candidate(
            writer_b,
            store_id="store-b",
            trial_start_at=datetime(2026, 8, 30, 10, 0, 0),
            booking_count=1,
        )
        result = send_trial_end_reports([candidate_a, candidate_b], NOW, push)

        self.assertEqual(result.sent, ["store-a"])
        self.assertIsNotNone(writer_a.sent_at)
        self.assertIsNone(writer_b.sent_at)


class AutoHandledFaqCountWiringTests(unittest.TestCase):
    """trial-end-scheduler-design.md 5節の残課題だった「NotificationLogAggregator.
    auto_handled_faq_count(フェーズ続き148)とcloud_function_send_trial_end_reports.pyの
    候補組み立て(TrialEndReportCandidate.auto_handled_inquiry_count)が実際につながるか」の
    結線テスト。auto_handled_faq_countは本モジュールのスコープ外(呼び出し元が集計済みの値を
    渡す設計、モジュールdocstring参照)のため、production配線に相当する「aggregatorの値を
    そのままcandidateへ渡す」処理が壊れていないことをここで確認する
    (course-set-pashaのTrialEndSchedulerToGenerationPausedWiringTestと同種の位置づけ)。
    """

    def test_resolved_faq_segments_flow_into_rendered_report_message(self):
        aggregator = NotificationLogAggregator()
        now = datetime(2026, 8, 20, 12, 0, 0)
        # resolved:trueが3件(自動対応)、resolved:falseが1件(未登録FAQ、対象外)
        for topic in ("access", "parking", "hours"):
            aggregator.record(
                "U-customer-1",
                {"faq_segments": [{"topic": topic, "resolved": True}]},
                now,
            )
        aggregator.record(
            "U-customer-1",
            {"faq_segments": [{"topic": "other", "resolved": False}]},
            now,
        )
        self.assertEqual(aggregator.auto_handled_faq_count, 3)

        writer = _StubWriter()
        push = InMemoryLinePushClient()
        # 呼び出し元(Cloud Function E)が行う想定の配線: 集計済みの値をそのまま渡す
        candidate = _candidate(
            writer, auto_handled_inquiry_count=aggregator.auto_handled_faq_count
        )
        result = send_trial_end_reports([candidate], NOW, push)

        self.assertEqual(result.sent, [STORE_ID])
        text = push.sent[0][1]
        self.assertIn("・自動対応できたお問い合わせ: 3件", text)


if __name__ == "__main__":
    unittest.main()
