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
    BOOKING_CONFLICT_RETRY_MESSAGE,
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
STORE_FAQ_INFO = {
    "address": "○○駅から徒歩5分",
    "parking": {"available": True, "capacity": "3"},
    "payment_methods": ["現金", "クレジットカード"],
}


def _new_processor(store_faq_info=None):
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
        store_faq_info=STORE_FAQ_INFO if store_faq_info is None else store_faq_info,
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

    def test_unimplemented_intent_is_forwarded_without_touching_flow(self):
        # cancel/changeは未実装のため、faq/escalation以外は引き続き顧客への自動返信なし。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "cancel", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
            }

        result = processor.process(_event("U1", "明日の予約キャンセルできますか"), llm_call, NOW)
        self.assertEqual(result.action, "forwarded_to_owner")
        self.assertEqual(result.detail, "cancel")
        self.assertIsNone(flow.stage("U1"))
        self.assertEqual(push.sent, [])
        # consultation_countはintent: "escalation"のみを対象に集計する(engine.py
        # NotificationLogAggregator.record()準拠)ため、cancelでは増加しない。
        self.assertEqual(logs.consultation_count, 0)


class EscalationReplyTests(unittest.TestCase):
    def test_escalation_sends_holding_message_and_notifies_owner(self):
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "escalation", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
            }

        result = processor.process(_event("U1", "施術で肌荒れしたんですが大丈夫でしょうか"), llm_call, NOW)
        self.assertEqual(result.action, "escalation_replied")
        self.assertEqual(result.detail, "consultation")
        self.assertIsNone(flow.stage("U1"))
        self.assertEqual(len(push.sent), 1)
        self.assertIn("担当者に確認のうえ", push.sent[0][1])
        self.assertEqual(logs.consultation_count, 1)

    def test_escalation_reason_is_carried_into_detail(self):
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "escalation", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
                "escalation_reason": "unimplemented_feature", "feature_hint": "デポジット決済",
            }

        result = processor.process(_event("U1", "予約時に前払いできますか"), llm_call, NOW)
        self.assertEqual(result.action, "escalation_replied")
        self.assertEqual(result.detail, "unimplemented_feature")
        self.assertEqual(len(push.sent), 1)


class FaqSegmentReplyTests(unittest.TestCase):
    def test_all_resolved_segments_are_answered_from_templates_individually(self):
        # E13a相当: 駐車場・支払い方法とも登録済み。1メッセージ1用件で2通に分けて送信する。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [
                    {"topic": "parking", "resolved": True},
                    {"topic": "payment", "resolved": True},
                ],
            }

        result = processor.process(_event("U1", "駐車場ある?支払いはカード使える?"), llm_call, NOW)
        self.assertEqual(result.action, "faq_replied")
        self.assertEqual(result.detail, "2_segments_0_unresolved")
        self.assertIsNone(flow.stage("U1"))
        self.assertEqual(len(push.sent), 2)
        self.assertEqual(push.sent[0][1], "当店: 駐車場がございます(3台分)。")
        self.assertEqual(push.sent[1][1], "当店: お支払い方法は現金、クレジットカードがご利用いただけます。")

    def test_unresolved_segment_gets_holding_message_and_owner_notification(self):
        # E13b相当: 駐車場は登録済み、電子マネーは未チェックのため保留文言に差し替える。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": True,
                "faq_segments": [
                    {"topic": "parking", "resolved": True},
                    {"topic": "payment", "resolved": False},
                ],
            }

        result = processor.process(_event("U1", "駐車場ある?電子マネーは使える?"), llm_call, NOW)
        self.assertEqual(result.detail, "2_segments_1_unresolved")
        self.assertEqual(len(push.sent), 2)
        self.assertEqual(push.sent[0][1], "当店: 駐車場がございます(3台分)。")
        self.assertIn("担当者に確認のうえ", push.sent[1][1])
        # 未解決topic(payment)はNotificationLogAggregatorのユニーク集計対象
        # (duplicate-topic-notification-log-rule.md準拠)。intentが"faq"のため
        # consultation_countは対象外(escalation専用の集計軸)。
        self.assertEqual(logs.unique_unresolved_topic_count(), 1)
        self.assertEqual(logs.consultation_count, 0)

    def test_access_topic_uses_registered_address(self):
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [
                    {"topic": "access", "resolved": True},
                    {"topic": "hours", "resolved": True},
                ],
            }

        processor.process(_event("U1", "場所と営業時間を教えてください"), llm_call, NOW)
        self.assertEqual(push.sent[0][1], "当店: ○○駅から徒歩5分です。")
        # "hours"はfaq-response-templates.mdの項目別テンプレート対象外(9aは住所/駐車場/支払いのみ)
        # のため、resolved: trueでも安全側で保留文言にフォールバックする。
        self.assertIn("担当者に確認のうえ", push.sent[1][1])

    def test_resolved_topic_without_registered_value_falls_back_to_holding_message(self):
        # 構造化出力がresolved: trueを返しても店舗FAQ情報が未登録なら断定回答しない(安全側)。
        processor, flow, push, logs = _new_processor(store_faq_info={})

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [
                    {"topic": "parking", "resolved": True},
                    {"topic": "access", "resolved": True},
                ],
            }

        processor.process(_event("U1", "駐車場と場所を教えてください"), llm_call, NOW)
        self.assertIn("担当者に確認のうえ", push.sent[0][1])
        self.assertIn("担当者に確認のうえ", push.sent[1][1])

    def test_single_item_faq_without_segments_is_still_forwarded_only(self):
        # faq_segmentsが付与されない単一項目FAQ(E10・E6等)は、topic情報が無いため
        # 引き続きオーナー転送のみ(自動返信なし)。モジュールdocstringの既知の制約。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "駐車場はありますか"), llm_call, NOW)
        self.assertEqual(result.action, "forwarded_to_owner")
        self.assertEqual(push.sent, [])


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

    def test_booking_conflict_notifies_owner_once_and_represents_fresh_candidates(self):
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
        self.assertTrue(result.detail.startswith("represented_"))
        # 謝罪(BOOKING_CONFLICT_RETRY_MESSAGE)に続けて、奪われた枠を除いた新しい候補一覧を送る。
        self.assertEqual(push.sent[-2][1], BOOKING_CONFLICT_RETRY_MESSAGE)
        self.assertIn("番号でお知らせください", push.sent[-1][1])
        self.assertNotIn(held_slot_key[2], push.sent[-1][1])
        self.assertEqual(flow.stage("U1"), "candidates_presented")

        # 差し戻された候補一覧からも、通常の候補選択→hold と同じ流れで再確定できること。
        def llm_call_reselect():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        result2 = processor.process(_event("U1", "1番で"), llm_call_reselect, NOW)
        self.assertEqual(result2.action, "held")

    def test_booking_conflict_falls_back_to_apology_when_no_alternative_slot(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)

        def llm_call_select():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event("U1", "1番で"), llm_call_select, NOW)

        # hold中の枠を横から奪われた状況を再現しつつ、検索条件のキャッシュが無いケース
        # (再検索できない、通常は発生しないが安全側フォールバックの確認)をシミュレートする。
        held_slot_key = next(iter(flow._slots._slots))
        flow._slots.release(held_slot_key)
        flow._slots.hold(held_slot_key, "OTHER_USER", NOW)
        flow._slots.confirm(held_slot_key, "OTHER_USER", NOW)
        del processor._search_context_by_user["U1"]

        def llm_call_details():
            return {
                "intent": "new_booking", "name": "山田", "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "山田です、カットでお願いします"), llm_call_details, NOW)
        self.assertEqual(result.action, "booking_conflict")
        self.assertEqual(result.detail, "no_alternative_forwarded_to_owner")
        self.assertEqual(push.sent[-1][1], BOOKING_CONFLICT_MESSAGE)
        self.assertEqual(flow.stage("U1"), "candidates_presented")


if __name__ == "__main__":
    unittest.main()
