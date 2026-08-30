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
    TrialEndReportStoreInputs,
    build_trial_end_report_candidates,
    send_trial_end_reports,
)
from engine import (  # noqa: E402
    BookingSlotManager,
    ConversationFlowStateMachine,
    EscalationConsolidator,
    InMemoryBookingRecordStore,
    NotificationLogAggregator,
)

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


class BookingCountWiringTests(unittest.TestCase):
    """trial-end-scheduler-design.md 5節の残課題のうち、AutoHandledFaqCountWiringTests
    (フェーズ続き151)がauto_handled_inquiry_count側のみを検証し、booking_count側
    (InMemoryBookingRecordStore.count_confirmed_bookings()、フェーズ続き150で
    カウンタ方式に変更)は未検証のまま残っていた点に対応する結線テスト。
    こちらもモジュールdocstring通り「呼び出し元が集計済みの値をそのまま渡す」設計の
    ため、count_confirmed_bookings()の戻り値がTrialEndReportCandidate.booking_count
    経由でLINE Push文言まで壊れずに届くことを確認する。
    """

    def test_confirmed_booking_count_flows_into_rendered_report_message(self):
        record_store = InMemoryBookingRecordStore()
        record_store.record_confirmed(STORE_ID, (STORE_ID, "2026-08-16", "11:00"), "田中", "カット")
        record_store.record_confirmed(STORE_ID, (STORE_ID, "2026-08-17", "12:00"), "佐藤", "カラー")
        record_store.record_confirmed(STORE_ID, (STORE_ID, "2026-08-18", "13:00"), "山本", "カット")
        self.assertEqual(record_store.count_confirmed_bookings(STORE_ID), 3)

        writer = _StubWriter()
        push = InMemoryLinePushClient()
        # 呼び出し元(Cloud Function E)が行う想定の配線: 集計済みの値をそのまま渡す
        candidate = _candidate(
            writer, booking_count=record_store.count_confirmed_bookings(STORE_ID)
        )
        result = send_trial_end_reports([candidate], NOW, push)

        self.assertEqual(result.sent, [STORE_ID])
        text = push.sent[0][1]
        self.assertIn("・処理した予約件数: 3件", text)


class BuildTrialEndReportCandidatesWiringTest(unittest.TestCase):
    """trial-end-scheduler-design.md 5節の残課題だった「候補組み立て処理(呼び出し元)への
    実配線」に対応する結線テスト。AutoHandledFaqCountWiringTests・BookingCountWiringTestsは
    それぞれ個別の値を手動でTrialEndReportCandidateへ渡していたが、実際の
    ConversationFlowStateMachine(record_store・logsを結線した実運用相当のインスタンス)・
    InMemoryBookingRecordStore・NotificationLogAggregatorの3つを、build_trial_end_report_
    candidates()経由で一度に組み立てても、trial_start_at・booking_count・
    auto_handled_inquiry_countのすべてが壊れずLINE Push文言まで届くこと、および
    送信成功時にengine自身(report_sent_writer)へmark_trial_end_report_sent()が
    実際に反映されることを確認する。
    """

    def test_engine_booking_store_and_aggregator_flow_into_sent_report(self):
        record_store = InMemoryBookingRecordStore()
        aggregator = NotificationLogAggregator()
        flow = ConversationFlowStateMachine(
            BookingSlotManager(),
            EscalationConsolidator(),
            logs=aggregator,
            record_store=record_store,
        )

        confirm_at = datetime(2026, 8, 15, 10, 0, 0)
        key = (STORE_ID, "2026-08-15", "14:00")
        flow.present_candidates("user_tanaka", now=confirm_at)
        flow.select_slot("user_tanaka", key, confirm_at)
        flow.provide_details("user_tanaka", "田中", "カット", confirm_at)
        self.assertEqual(flow.get_trial_start_at(), confirm_at)
        self.assertEqual(record_store.count_confirmed_bookings(STORE_ID), 1)

        for topic in ("access", "parking"):
            aggregator.record(
                "user_tanaka",
                {"faq_segments": [{"topic": topic, "resolved": True}]},
                confirm_at,
            )
        self.assertEqual(aggregator.auto_handled_faq_count, 2)
        self.assertIsNone(flow.get_trial_end_report_sent_at())

        candidates = build_trial_end_report_candidates(
            [
                TrialEndReportStoreInputs(
                    store_id=STORE_ID,
                    engine=flow,
                    booking_store=record_store,
                    log_aggregator=aggregator,
                    owner_line_user_id="U-owner-1",
                )
            ]
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].trial_start_at, confirm_at)
        self.assertEqual(candidates[0].booking_count, 1)
        self.assertEqual(candidates[0].auto_handled_inquiry_count, 2)

        push = InMemoryLinePushClient()
        result = send_trial_end_reports(candidates, NOW, push)

        self.assertEqual(result.sent, [STORE_ID])
        text = push.sent[0][1]
        self.assertIn("・処理した予約件数: 1件", text)
        self.assertIn("・自動対応できたお問い合わせ: 2件", text)
        # report_sent_writer=flow自身に冪等性書き込みが実際に反映されることを確認
        self.assertEqual(flow.get_trial_end_report_sent_at(), NOW)


if __name__ == "__main__":
    unittest.main()
