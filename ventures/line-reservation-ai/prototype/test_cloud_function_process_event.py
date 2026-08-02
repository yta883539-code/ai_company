#!/usr/bin/env python3
"""prototype/cloud_function_process_event.py の自動テストスイート(unittest、外部ライブラリ非依存)。

実行方法: python3 -m unittest test_cloud_function_process_event -v
          (prototype/ディレクトリで実行)
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    BOOKING_CONFLICT_MESSAGE,
    ConversationEventProcessor,
    InMemoryLinePushClient,
    REASK_DATE_RANGE_MESSAGE,
    REASK_NAME_MENU_MESSAGE,
    resolve_menu_duration,
)
from engine import (  # noqa: E402
    AvailabilitySearcher,
    BookingSlotManager,
    ConversationFlowStateMachine,
    EscalationConsolidator,
    NotificationLogAggregator,
)

STORE_ID = "store-1"
MENU_DURATIONS = {"カット": 30, "カラー": 90}
NOW = datetime(2026, 8, 3, 10, 0)  # 月曜


def _new_processor():
    flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
    searcher = AvailabilitySearcher(business_hours=(9 * 60, 18 * 60), slot_interval_minutes=30)
    push = InMemoryLinePushClient()
    logs = NotificationLogAggregator()
    processor = ConversationEventProcessor(
        flow=flow,
        searcher=searcher,
        booking_slots=flow._slots,
        consolidator=flow._consolidator,
        logs=logs,
        push_client=push,
        store_id=STORE_ID,
        menu_durations=MENU_DURATIONS,
    )
    return processor, flow, push, logs


def _event(user_id: str, text: str) -> dict:
    return {"source": {"userId": user_id}, "message": {"text": text}}


class ResolveMenuDurationTests(unittest.TestCase):
    def test_returns_duration_for_registered_menu(self):
        self.assertEqual(resolve_menu_duration("カット", MENU_DURATIONS), 30)

    def test_returns_none_for_unregistered_menu(self):
        self.assertIsNone(resolve_menu_duration("シェービング", MENU_DURATIONS))

    def test_returns_none_when_menu_is_missing(self):
        self.assertIsNone(resolve_menu_duration(None, MENU_DURATIONS))


class NewBookingDispatchTests(unittest.TestCase):
    def test_ambiguous_date_range_presents_candidates(self):
        processor, flow, push, _ = _new_processor()
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜の空き候補", "confirmed": False,
                "needs_owner_check": False,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        result = processor.process(_event("U1", "来週土曜カットで"), llm_call, NOW)
        self.assertEqual(result.action, "candidates_presented")
        self.assertEqual(flow.stage("U1"), "candidates_presented")
        self.assertEqual(len(push.sent), 1)
        self.assertIn("番号でお知らせください", push.sent[0][1])

    def test_unregistered_menu_is_forwarded_to_owner_without_searching(self):
        processor, flow, push, _ = _new_processor()

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "シェービング",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "来週土曜シェービングで"), llm_call, NOW)
        self.assertEqual(result.action, "forwarded_to_owner")
        self.assertEqual(result.detail, "unregistered_menu")
        self.assertIsNone(flow.stage("U1"))
        self.assertEqual(push.sent, [])

    def test_no_date_range_reasks_customer(self):
        processor, _, push, _ = _new_processor()

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "予約したいです"), llm_call, NOW)
        self.assertEqual(result.action, "reask")
        self.assertEqual(push.sent[0][1], REASK_DATE_RANGE_MESSAGE)

    def test_non_booking_intent_is_forwarded_without_touching_flow(self):
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "escalation", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
            }

        result = processor.process(_event("U1", "定休日を変更したいのですが"), llm_call, NOW)
        self.assertEqual(result.action, "forwarded_to_owner")
        self.assertEqual(result.detail, "escalation")
        self.assertIsNone(flow.stage("U1"))
        self.assertEqual(push.sent, [])
        self.assertEqual(logs.consultation_count, 1)


class CandidateSelectionAndDetailsTests(unittest.TestCase):
    def _present_candidates(self, processor, user_id="U1"):
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        return processor.process(_event(user_id, "来週土曜カットで"), llm_call, NOW)

    def test_selecting_a_candidate_holds_the_slot_and_sends_hold_message(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "1番で"), llm_call, NOW)
        self.assertEqual(result.action, "held")
        self.assertEqual(flow.stage("U1"), "awaiting_details")
        self.assertIn("仮押さえいたしました", push.sent[-1][1])
        self.assertIn("09:00", push.sent[-1][1])

    def test_unresolvable_reply_reasks_and_keeps_stage(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "うーん、どうしよう"), llm_call, NOW)
        self.assertEqual(result.action, "reask")
        self.assertEqual(flow.stage("U1"), "candidates_presented")

    def test_full_flow_reaches_confirmed_with_candidate_label_in_message(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)

        def llm_call_select():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event("U1", "1番で"), llm_call_select, NOW)

        def llm_call_details():
            return {
                "intent": "new_booking", "name": "山田", "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "山田です、カットでお願いします"), llm_call_details, NOW)
        self.assertEqual(result.action, "confirmed")
        self.assertEqual(flow.stage("U1"), "confirmed")
        message = push.sent[-1][1]
        self.assertIn("山田様", message)
        self.assertIn("09:00", message)  # holdしたcandidateのlabelが引き継がれていること

    def test_missing_name_or_menu_reasks_without_calling_provide_details(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)

        def llm_call_select():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event("U1", "1番で"), llm_call_select, NOW)

        def llm_call_incomplete():
            return {
                "intent": "new_booking", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "はい"), llm_call_incomplete, NOW)
        self.assertEqual(result.action, "reask")
        self.assertEqual(result.detail, "missing_name_or_menu")
        self.assertEqual(push.sent[-1][1], REASK_NAME_MENU_MESSAGE)
        self.assertEqual(flow.stage("U1"), "awaiting_details")

    def test_booking_conflict_notifies_owner_once_and_sends_apology_to_customer(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)

        def llm_call_select():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event("U1", "1番で"), llm_call_select, NOW)

        # ConversationFlowStateMachine.confirm()を確実に失敗させるため、hold中の枠を
        # 横から別ユーザーの確定で奪う(BookingSlotManagerの競合シナリオを再現)。
        held_slot_key = next(iter(flow._slots._slots))
        flow._slots.release(held_slot_key)
        flow._slots.hold(held_slot_key, "OTHER_USER", NOW)
        flow._slots.confirm(held_slot_key, "OTHER_USER", NOW)

        def llm_call_details():
            return {
                "intent": "new_booking", "name": "山田", "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "山田です、カットでお願いします"), llm_call_details, NOW)
        self.assertEqual(result.action, "booking_conflict")
        self.assertEqual(push.sent[-1][1], BOOKING_CONFLICT_MESSAGE)
        self.assertEqual(flow.stage("U1"), "candidates_presented")


if __name__ == "__main__":
    unittest.main()
