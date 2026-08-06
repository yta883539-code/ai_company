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
    CHANGE_NO_CANDIDATES_MESSAGE,
    ConversationEventProcessor,
    InMemoryConfirmedReplyRecorder,
    InMemoryLinePushClient,
    LinePushDeliveryError,
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
    "hours": {"open_minutes": 9 * 60, "close_minutes": 18 * 60, "closed_weekdays": frozenset({6})},
}


class FlakyLinePushClient(InMemoryLinePushClient):
    """api-call-failure-handling.md「方針2」のテスト用。send_message()呼び出しのうち
    最初のfail_count回はLinePushDeliveryErrorを送出し、それ以降(または最初からfail_count=0なら
    常時)は成功してInMemoryLinePushClientと同様に`sent`へ記録する。呼び出し回数はメッセージ単位
    (同じテキストの2回目の呼び出しであっても)でカウントする。
    """

    def __init__(self, fail_count: int) -> None:
        super().__init__()
        self._remaining_failures = fail_count

    def send_message(self, user_id: str, text: str) -> None:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise LinePushDeliveryError("simulated LINE push failure")
        super().send_message(user_id, text)


def _new_processor(
    store_faq_info=None,
    confirmed_reply_recorder=None,
    closed_weekdays=frozenset(),
    push_client=None,
    owner_user_id=None,
):
    # system-event-log-gap-fix.md準拠。logsをflowにも渡すことで、booking_conflict等の
    # システム内部イベントがNotificationLogAggregator.system_event_countsにも記録されるようにする。
    logs = NotificationLogAggregator()
    flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator(), logs=logs)
    searcher = AvailabilitySearcher(
        business_hours=(9 * 60, 18 * 60), slot_interval_minutes=30, closed_weekdays=closed_weekdays
    )
    push = push_client if push_client is not None else InMemoryLinePushClient()
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
        confirmed_reply_recorder=confirmed_reply_recorder,
        owner_user_id=owner_user_id,
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

    # 「予約フロー外intentは自動返信なしでオーナー転送のみ」という汎用フォールバック経路
    # (process()の`if intent != "new_booking":`分岐)を検証していたtest_unimplemented_intent_*は
    # change-intent-handling-design.md実装に伴い削除した。理由: booking_output.schema.jsonの
    # intent enum(new_booking/cancel/change/faq/escalation)は全て専用ハンドラを持つように
    # なったため(2026-08-02時点)、この汎用分岐に到達するのは「faq_segments無しのfaq」
    # (9b雑談等)のケースのみになった。そのケースは
    # FaqSegmentReplyTests.test_faq_without_segments_is_still_forwarded_only で別途検証済みのため、
    # enumに存在しない架空のintent値でこの分岐を叩くテストは、schema検証のフォールバック
    # (SAFE_FALLBACK_OUTPUT、intent: "escalation"に上書きされる)を経由してしまい
    # 意図した経路を検証できないため、重複テストとして残さず削除した。


class PushDeliveryFailureTests(unittest.TestCase):
    """api-call-failure-handling.md「方針2」(LINE Push API呼び出し自体の失敗)のテスト。
    ConversationEventProcessor._send()の即時1回のみリトライと、それでも失敗した場合の
    line_push_failed記録・オーナー即時通知を、_start_new_booking()のREASK_DATE_RANGE_MESSAGE
    送信(1回のpush呼び出しで完結する経路)を借りて検証する。
    """

    def _reask_llm_call(self):
        return {
            "intent": "new_booking", "name": None, "menu": "カット",
            "datetime_candidate": None, "confirmed": False, "needs_owner_check": False,
        }

    def test_succeeds_after_one_immediate_retry(self):
        push = FlakyLinePushClient(fail_count=1)
        processor, _, push, logs = _new_processor(push_client=push)

        result = processor.process(_event("U1", "予約したいです"), self._reask_llm_call, NOW)

        self.assertEqual(result.action, "reask")
        # 1回目は失敗、即時リトライした2回目で成功したメッセージだけが届く。
        self.assertEqual(push.sent, [("U1", REASK_DATE_RANGE_MESSAGE)])
        self.assertEqual(logs.system_event_counts.get("line_push_failed"), None)

    def test_records_line_push_failed_and_notifies_owner_when_retry_also_fails(self):
        push = FlakyLinePushClient(fail_count=2)
        processor, _, push, logs = _new_processor(push_client=push)

        result = processor.process(_event("U1", "予約したいです"), self._reask_llm_call, NOW)

        # 送信自体は諦めるが、process()の呼び出し自体は例外を伝播させず正常に完了する
        # (Cloud Tasksにタスクを再実行させ、hold/confirm等の状態変更を二重実行しないため)。
        self.assertEqual(result.action, "reask")
        self.assertEqual(push.sent, [])
        self.assertEqual(logs.system_event_counts.get("line_push_failed"), 1)

    def test_third_call_after_two_failures_is_treated_as_new_escalation_window(self):
        # EscalationConsolidator.on_event()は初回発火のみ即時扱いのため、直後に発生した
        # 2件目のline_push_failedは5分ウィンドウ内としてキューに貯まる(即時通知はされない)
        # ことを確認する。集約自体の挙動はEscalationConsolidatorTest側で別途検証済みのため、
        # ここではProcessorがEscalationConsolidator/NotificationLogAggregator双方に正しく
        # 委譲していることのみを確認する。
        push = FlakyLinePushClient(fail_count=2)
        processor, _, push, logs = _new_processor(push_client=push)
        processor.process(_event("U1", "予約したいです"), self._reask_llm_call, NOW)

        push._remaining_failures = 2
        processor.process(_event("U1", "予約したいです"), self._reask_llm_call, NOW + timedelta(minutes=1))

        self.assertEqual(logs.system_event_counts.get("line_push_failed"), 2)


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
                "faq_segments": [{"topic": "access", "resolved": True}],
            }

        processor.process(_event("U1", "場所を教えてください"), llm_call, NOW)
        self.assertEqual(push.sent[0][1], "当店: ○○駅から徒歩5分です。")

    def test_hours_topic_uses_registered_business_hours(self):
        # E17相当(2026-08-03新規、hours-other-faq-topic-resolution.md参照)。
        # 曜日別営業時間・休憩時間を使わないシンプルな店舗は、登録済みの開始・終了時刻と
        # 定休日をそのまま組み立てたテンプレートで自動回答できる。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [{"topic": "hours", "resolved": True}],
            }

        processor.process(_event("U1", "営業時間を教えてください"), llm_call, NOW)
        self.assertEqual(push.sent[0][1], "当店の営業時間は09:00〜18:00です(定休日: 日曜)。")

    def test_hours_topic_falls_back_when_store_has_complex_hours(self):
        # 曜日別営業時間・休憩時間を使う店舗はstore_faq_infoに"hours"キーを設定しない運用とし
        # (Cloud Function B呼び出し側の責務、hours-other-faq-topic-resolution.md参照)、
        # 単一時間帯のテンプレートでは不正確な案内になるため安全側でエスカレーションに倒す。
        info = dict(STORE_FAQ_INFO)
        del info["hours"]
        processor, flow, push, logs = _new_processor(store_faq_info=info)

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [{"topic": "hours", "resolved": True}],
            }

        processor.process(_event("U1", "営業時間を教えてください"), llm_call, NOW)
        self.assertIn("担当者に確認のうえ", push.sent[0][1])

    def test_other_topic_always_falls_back_to_holding_message(self):
        # topic: "other"は店舗FAQ情報欄に対応する登録項目が存在しないため常にエスカレーションに
        # 倒す設計(hours-other-faq-topic-resolution.md参照)。resolved: trueが返っても安全側。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [{"topic": "other", "resolved": True}],
            }

        processor.process(_event("U1", "予約は何件まで一度に取れますか"), llm_call, NOW)
        self.assertIn("担当者に確認のうえ", push.sent[0][1])

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

    def test_single_item_faq_segments_is_answered_from_template(self):
        # E10相当(2026-08-02改訂): json-schema-multi-intent-extension.mdの改訂により、
        # 厳守事項9aに基づく単一項目FAQでもfaq_segmentsを1要素配列で付与する方針になった。
        # 既存の複合質問向けループ(_handle_faq)がそのまま流用され、1通だけ自動返信される。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [{"topic": "parking", "resolved": True}],
            }

        result = processor.process(_event("U1", "駐車場はありますか"), llm_call, NOW)
        self.assertEqual(result.action, "faq_replied")
        self.assertEqual(result.detail, "1_segments_0_unresolved")
        self.assertEqual(len(push.sent), 1)
        self.assertEqual(push.sent[0][1], "当店: 駐車場がございます(3台分)。")

    def test_faq_without_segments_is_still_forwarded_only(self):
        # faq_segmentsが付与されないfaq intent(厳守事項9b雑談(E6等)や、2026-08-02改訂の
        # 付与ルールに実LLMが従わなかったレガシー出力)は、topic情報が無いため
        # 引き続きオーナー転送のみ(自動返信なし)の安全側フォールバックを維持する。
        processor, flow, push, logs = _new_processor()

        def llm_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "こんにちは!"), llm_call, NOW)
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
        processor, flow, push, logs = _new_processor()
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
        # system-event-log-gap-fix.md準拠。booking_conflictはEscalationConsolidatorだけでなく
        # NotificationLogAggregator.system_event_countsにも記録される。
        self.assertEqual(logs.system_event_counts.get("booking_conflict"), 1)

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


class FirstBookingSelfCheckNotificationTests(unittest.TestCase):
    """owner-notification-channel-design.md / first-booking-self-check-notification-design.md準拠。
    店舗全体で最初の確定にのみ、owner_user_id宛にセルフチェック促し通知が1回だけ追加送信されること。
    """

    def _present_candidates(self, processor, user_id):
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        return processor.process(_event(user_id, "来週土曜カットで"), llm_call, NOW)

    def _reach_confirmed(self, processor, user_id, name="山田"):
        self._present_candidates(processor, user_id)

        def llm_call_select():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event(user_id, "1番で"), llm_call_select, NOW)

        def llm_call_details():
            return {
                "intent": "new_booking", "name": name, "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        return processor.process(_event(user_id, f"{name}です、カットでお願いします"), llm_call_details, NOW)

    def test_first_confirmation_sends_self_check_to_owner(self):
        processor, flow, push, _ = _new_processor(owner_user_id="U-owner")
        result = self._reach_confirmed(processor, "U1", name="山田")

        self.assertEqual(result.action, "confirmed")
        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("最初のご予約確定", owner_messages[0])
        self.assertIn("山田様", owner_messages[0])
        # 顧客への確定メッセージの直後に送られていること(pushの最後の1件がオーナー宛)。
        self.assertEqual(push.sent[-1], ("U-owner", owner_messages[0]))

    def test_second_confirmation_does_not_resend_self_check(self):
        processor, flow, push, _ = _new_processor(owner_user_id="U-owner")
        self._reach_confirmed(processor, "U1", name="山田")
        self._reach_confirmed(processor, "U2", name="鈴木")

        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)

    def test_no_owner_push_when_owner_user_id_not_configured(self):
        processor, flow, push, _ = _new_processor(owner_user_id=None)
        result = self._reach_confirmed(processor, "U1", name="山田")

        self.assertEqual(result.action, "confirmed")
        self.assertEqual([uid for uid, _ in push.sent if uid == "U-owner"], [])
        # オーナー宛が無いだけで、顧客への確定メッセージ送信自体は成功していること。
        self.assertIn("山田様", push.sent[-1][1])


class CancelIntentTests(unittest.TestCase):
    """cancel-intent-handling-design.md準拠。会話のstageごとにcancel intentの挙動を検証する。"""

    def _present_candidates(self, processor, user_id="U1"):
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        return processor.process(_event(user_id, "来週土曜カットで"), llm_call, NOW)

    def _select_first_candidate(self, processor, user_id="U1"):
        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        return processor.process(_event(user_id, "1番で"), llm_call, NOW)

    def _confirm_details(self, processor, user_id="U1", name="山田"):
        def llm_call():
            return {
                "intent": "new_booking", "name": name, "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        return processor.process(_event(user_id, f"{name}です、カットでお願いします"), llm_call, NOW)

    def _cancel(self, processor, user_id="U1"):
        def llm_call():
            return {
                "intent": "cancel", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
            }

        return processor.process(_event(user_id, "キャンセルでお願いします"), llm_call, NOW)

    def test_cancel_with_no_active_state_is_forwarded_to_owner(self):
        processor, flow, push, logs = _new_processor()

        result = self._cancel(processor)
        self.assertEqual(result.action, "forwarded_to_owner")
        self.assertEqual(result.detail, "cancel_not_found")
        self.assertIn("確認できな", push.sent[-1][1])
        self.assertIsNone(flow.stage("U1"))
        # system-event-log-gap-fix.md準拠。cancel_not_foundもNotificationLogAggregatorに記録される。
        self.assertEqual(logs.system_event_counts.get("cancel_not_found"), 1)

    def test_cancel_while_candidates_presented_clears_state_without_owner_notice(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)
        slots_before = dict(flow._slots._slots)

        result = self._cancel(processor)
        self.assertEqual(result.action, "cancelled")
        self.assertEqual(result.detail, "candidates_presented")
        self.assertIsNone(flow.stage("U1"))
        self.assertIn("中止", push.sent[-1][1])
        # candidates_presentedの段階ではまだhold()していないため、枠の状態は変化しない。
        self.assertEqual(dict(flow._slots._slots), slots_before)

    def test_cancel_while_awaiting_details_releases_the_held_slot(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)
        self._select_first_candidate(processor)
        held_slot_key = next(iter(flow._slots._slots))
        self.assertEqual(flow._slots.status(held_slot_key, NOW), "pending")

        result = self._cancel(processor)
        self.assertEqual(result.action, "cancelled")
        self.assertEqual(result.detail, "awaiting_details")
        self.assertIsNone(flow.stage("U1"))
        self.assertIsNone(flow._slots.status(held_slot_key, NOW))
        self.assertIn("中止", push.sent[-1][1])

    def test_cancel_after_confirmed_releases_slot_and_notifies_owner(self):
        processor, flow, push, logs = _new_processor()
        self._present_candidates(processor)
        self._select_first_candidate(processor)
        self._confirm_details(processor, name="山田")
        confirmed_slot_key = next(iter(flow._slots._slots))
        self.assertEqual(flow._slots.status(confirmed_slot_key, NOW), "confirmed")

        result = self._cancel(processor)
        self.assertEqual(result.action, "cancelled")
        self.assertEqual(result.detail, "confirmed")
        self.assertIsNone(flow.stage("U1"))
        self.assertIsNone(flow._slots.status(confirmed_slot_key, NOW))
        message = push.sent[-1][1]
        self.assertIn("キャンセルを承りました", message)
        self.assertIn("09:00", message)

        # 確定済みキャンセルはEscalationConsolidator経由でオーナーに即時通知される
        # (candidates_presented/awaiting_detailsの段階とは異なり、外部予約記録の更新が必要なため)。
        window = flow._consolidator._windows["U1"]
        self.assertEqual(window.last_event_at, NOW)
        # system-event-log-gap-fix.md準拠。booking_cancelledもNotificationLogAggregatorに記録される。
        self.assertEqual(logs.system_event_counts.get("booking_cancelled"), 1)


class ChangeIntentTests(unittest.TestCase):
    """change-intent-handling-design.md準拠。会話のstageごとにchange intentの挙動を検証する
    (旧枠の解放部分はCancelIntentTestsと対称だが、changeは会話を終わらせず新規候補検索へ
    そのまま接続する点が異なる)。
    """

    def _present_candidates(self, processor, user_id="U1"):
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        return processor.process(_event(user_id, "来週土曜カットで"), llm_call, NOW)

    def _select_first_candidate(self, processor, user_id="U1"):
        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        return processor.process(_event(user_id, "1番で"), llm_call, NOW)

    def _confirm_details(self, processor, user_id="U1", name="山田"):
        def llm_call():
            return {
                "intent": "new_booking", "name": name, "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        return processor.process(_event(user_id, f"{name}です、カットでお願いします"), llm_call, NOW)

    def _change(self, processor, user_id="U1", date_range_day=None):
        day = date_range_day or NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call():
            return {
                "intent": "change", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜の別の時間に変更したい", "confirmed": False,
                "needs_owner_check": True,
                "requested_date_range": {"start": day.isoformat(), "end": day.isoformat()},
            }

        return processor.process(_event(user_id, "来週土曜の別の時間に変更できますか"), llm_call, NOW)

    def test_change_with_no_active_state_is_forwarded_to_owner(self):
        processor, flow, push, logs = _new_processor()

        result = self._change(processor)
        self.assertEqual(result.action, "forwarded_to_owner")
        self.assertEqual(result.detail, "change_not_found")
        self.assertIn("確認できな", push.sent[-1][1])
        self.assertIsNone(flow.stage("U1"))
        # system-event-log-gap-fix.md準拠。change_not_foundもNotificationLogAggregatorに記録される。
        self.assertEqual(logs.system_event_counts.get("change_not_found"), 1)

    def test_change_while_candidates_presented_re_searches_without_release_notice(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)
        slots_before = dict(flow._slots._slots)
        sent_before_change = len(push.sent)

        result = self._change(processor)
        self.assertEqual(result.action, "candidates_presented")
        self.assertEqual(flow.stage("U1"), "candidates_presented")
        # candidates_presentedの段階ではまだhold()していないため、枠の状態は変化しない。
        self.assertEqual(dict(flow._slots._slots), slots_before)
        # 解放すべき実体が無いため「取り消した」旨の案内なしに、新しい候補一覧のみ1通届く。
        self.assertEqual(len(push.sent) - sent_before_change, 1)
        self.assertIn("番号でお知らせください", push.sent[-1][1])

    def test_change_while_awaiting_details_releases_the_held_slot_then_represents_candidates(self):
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)
        self._select_first_candidate(processor)
        held_slot_key = next(iter(flow._slots._slots))
        self.assertEqual(flow._slots.status(held_slot_key, NOW), "pending")

        result = self._change(processor)
        self.assertEqual(result.action, "candidates_presented")
        self.assertEqual(flow.stage("U1"), "candidates_presented")
        self.assertIsNone(flow._slots.status(held_slot_key, NOW))
        self.assertIn("取り消し", push.sent[-2][1])
        self.assertIn("番号でお知らせください", push.sent[-1][1])

    def test_change_after_confirmed_releases_slot_notifies_owner_then_represents_candidates(self):
        processor, flow, push, logs = _new_processor()
        self._present_candidates(processor)
        self._select_first_candidate(processor)
        self._confirm_details(processor, name="山田")
        confirmed_slot_key = next(iter(flow._slots._slots))
        self.assertEqual(flow._slots.status(confirmed_slot_key, NOW), "confirmed")

        result = self._change(processor)
        self.assertEqual(result.action, "candidates_presented")
        self.assertEqual(flow.stage("U1"), "candidates_presented")
        self.assertIsNone(flow._slots.status(confirmed_slot_key, NOW))
        message = push.sent[-2][1]
        self.assertIn("取り消し", message)
        self.assertIn("09:00", message)
        self.assertIn("番号でお知らせください", push.sent[-1][1])

        # cancelと同じくEscalationConsolidator経由でオーナーに即時通知される
        # (外部予約記録の更新が必要なため。escalation_reasonはbooking_change_startedで
        # cancelのbooking_cancelledと区別する)。
        window = flow._consolidator._windows["U1"]
        self.assertEqual(window.last_event_at, NOW)
        # system-event-log-gap-fix.md準拠。booking_change_startedもNotificationLogAggregatorに記録される。
        self.assertEqual(logs.system_event_counts.get("booking_change_started"), 1)

    def test_change_after_confirmed_with_no_new_candidates_uses_change_specific_reask(self):
        """change-intent-handling-design.mdの「残る課題」で指摘していた、change後の新規候補
        検索が0件だった場合の文言出し分け。旧予約を解放済み(confirmed→release)であるにも
        かかわらず新しい候補が見つからない場合は、通常のREASK_DATE_RANGE_MESSAGEではなく
        「以前のご予約は取り消し済み」である旨を含むCHANGE_NO_CANDIDATES_MESSAGEを送る。
        """
        processor, flow, push, _ = _new_processor()
        self._present_candidates(processor)
        self._select_first_candidate(processor)
        self._confirm_details(processor, name="山田")
        confirmed_slot_key = next(iter(flow._slots._slots))
        self.assertEqual(flow._slots.status(confirmed_slot_key, NOW), "confirmed")

        # 新規候補検索が確実に0件になるよう、既に過ぎた日付をrequested_date_rangeに指定する。
        past_day = NOW.date() - timedelta(days=1)
        result = self._change(processor, date_range_day=past_day)

        self.assertEqual(result.action, "reask")
        self.assertEqual(result.detail, "no_date_range_or_no_candidates_change")
        # 旧予約は既にreleaseされている(通常のchange成功時と変わらない)。
        self.assertIsNone(flow._slots.status(confirmed_slot_key, NOW))
        # 「取り消した」旨の案内 → 新候補0件時のchange専用文言、の順に2通届く。
        self.assertIn("取り消し", push.sent[-2][1])
        self.assertEqual(push.sent[-1][1], CHANGE_NO_CANDIDATES_MESSAGE)

    def test_change_while_candidates_presented_with_no_new_candidates_uses_generic_reask(self):
        """旧予約を解放していない(candidates_presented、まだhold()していない)場合は
        「取り消した」実体が無いため、change専用文言ではなく通常のREASK_DATE_RANGE_MESSAGEで
        聞き直す(CHANGE_NO_CANDIDATES_MESSAGEの「以前のご予約は取り消し済み」は不正確なため)。
        """
        processor, _, push, _ = _new_processor()
        self._present_candidates(processor)

        past_day = NOW.date() - timedelta(days=1)
        result = self._change(processor, date_range_day=past_day)

        self.assertEqual(result.action, "reask")
        self.assertEqual(result.detail, "no_date_range_or_no_candidates")
        self.assertEqual(push.sent[-1][1], REASK_DATE_RANGE_MESSAGE)


class ConfirmedReplyRecordingTests(unittest.TestCase):
    """customer-reply-detection-design.md準拠。confirmed状態の会話へメッセージが届いた
    事実がConfirmedReplyRecorderへ記録されることを検証する。
    """

    def _reach_confirmed(self, processor, user_id="U1"):
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call_present():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        processor.process(_event(user_id, "来週土曜カットで"), llm_call_present, NOW)

        def llm_call_select():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event(user_id, "1番で"), llm_call_select, NOW)

        def llm_call_details():
            return {
                "intent": "new_booking", "name": "山田", "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        processor.process(_event(user_id, "山田です、カットでお願いします"), llm_call_details, NOW)

    def test_message_while_confirmed_is_recorded_regardless_of_intent(self):
        recorder = InMemoryConfirmedReplyRecorder()
        processor, flow, push, _ = _new_processor(confirmed_reply_recorder=recorder)
        self._reach_confirmed(processor)
        self.assertEqual(flow.stage("U1"), "confirmed")
        self.assertEqual(recorder.recorded, [])  # 確定直後はまだ返信していない

        def llm_call_faq():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [{"topic": "parking", "resolved": True}],
            }

        later = NOW + timedelta(hours=2)
        processor.process(_event("U1", "駐車場ありますか"), llm_call_faq, later)
        self.assertEqual(recorder.recorded, [("U1", later)])
        # faq返信自体はconfirmed後の通常経路のまま継続する(記録は副作用として追加されるのみ)。
        self.assertTrue(any("駐車場" in text for _, text in push.sent))

    def test_second_message_overwrites_with_latest_timestamp(self):
        recorder = InMemoryConfirmedReplyRecorder()
        processor, flow, _, _ = _new_processor(confirmed_reply_recorder=recorder)
        self._reach_confirmed(processor)

        def llm_call_escalation():
            return {
                "intent": "escalation", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": True,
            }

        first_reply = NOW + timedelta(hours=1)
        second_reply = NOW + timedelta(hours=3)
        processor.process(_event("U1", "ありがとうございます"), llm_call_escalation, first_reply)
        processor.process(_event("U1", "体調が心配です"), llm_call_escalation, second_reply)
        self.assertEqual(recorder.recorded, [("U1", first_reply), ("U1", second_reply)])

    def test_not_recorded_before_confirmed_stage(self):
        recorder = InMemoryConfirmedReplyRecorder()
        processor, flow, _, _ = _new_processor(confirmed_reply_recorder=recorder)

        def llm_call_present():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
                "requested_date_range": {
                    "start": (NOW.date() + timedelta(days=5)).isoformat(),
                    "end": (NOW.date() + timedelta(days=5)).isoformat(),
                },
            }

        processor.process(_event("U1", "来週土曜カットで"), llm_call_present, NOW)
        self.assertEqual(flow.stage("U1"), "candidates_presented")
        self.assertEqual(recorder.recorded, [])

    def test_recorder_is_optional_and_defaults_to_no_op(self):
        processor, flow, push, _ = _new_processor()  # confirmed_reply_recorder未指定
        self._reach_confirmed(processor)

        def llm_call_faq():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
                "faq_segments": [{"topic": "parking", "resolved": True}],
            }

        # recorder未指定でも例外にならず、通常の返信処理は継続すること。
        result = processor.process(_event("U1", "駐車場ありますか"), llm_call_faq, NOW)
        self.assertEqual(result.action, "faq_replied")


class FailForUserPushClient(InMemoryLinePushClient):
    """指定したuser_id宛の送信のみ常に失敗させる検証用クライアント。
    _send()の「オーナー自身への送信失敗時は再帰しない」ガードを検証するために使う。
    """

    def __init__(self, failing_user_id: str) -> None:
        super().__init__()
        self._failing_user_id = failing_user_id

    def send_message(self, user_id: str, text: str) -> None:
        if user_id == self._failing_user_id:
            raise LinePushDeliveryError("simulated failure")
        super().send_message(user_id, text)


class OwnerEscalationNotificationTests(unittest.TestCase):
    """owner-notification-channel-design.mdの残課題だった「EscalationConsolidator/
    NotificationLogAggregatorが返す通知を実際にオーナーへpushする配線」のテスト。
    """

    def _escalation_llm_call(self, reason=None, feature_hint=None):
        def call():
            output = {
                "intent": "escalation", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
            }
            if reason:
                output["escalation_reason"] = reason
            if feature_hint:
                output["feature_hint"] = feature_hint
            return output

        return call

    def test_escalation_notifies_owner_with_consultation_label(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")

        result = processor.process(
            _event("U1", "施術で肌荒れしたんですが大丈夫でしょうか"), self._escalation_llm_call(), NOW
        )

        self.assertEqual(result.action, "escalation_replied")
        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("【要確認】", owner_messages[0])
        self.assertIn("予約以外のご相談", owner_messages[0])
        self.assertIn("お客様", owner_messages[0])

    def test_unimplemented_feature_notification_includes_feature_hint(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")

        processor.process(
            _event("U1", "予約時に前払いできますか"),
            self._escalation_llm_call("unimplemented_feature", "デポジット決済"),
            NOW,
        )

        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("未対応機能に関するお問い合わせ", owner_messages[0])
        self.assertIn("デポジット決済", owner_messages[0])

    def test_chitchat_like_forward_does_not_notify_owner(self):
        # E6相当(9b雑談、needs_owner_check: false)。forwarded_to_ownerにはなるが
        # オーナーへの実pushは対象外(EscalationConsolidatorのウィンドウ管理には乗る)。
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")

        def chitchat_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "こんにちは!"), chitchat_call, NOW)

        self.assertEqual(result.action, "forwarded_to_owner")
        self.assertEqual([uid for uid, _ in push.sent if uid == "U-owner"], [])

    def test_unresolved_faq_segment_notifies_owner_with_topic_label(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")

        def faq_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": True,
                "faq_segments": [
                    {"topic": "parking", "resolved": True},
                    {"topic": "payment", "resolved": False},
                ],
            }

        processor.process(_event("U2", "駐車場ある?電子マネーは使える?"), faq_call, NOW)

        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("未登録FAQへのお問い合わせ", owner_messages[0])
        self.assertIn("支払い方法", owner_messages[0])

    def test_unregistered_menu_notifies_owner(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "フェイシャル",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
            }

        result = processor.process(_event("U1", "フェイシャルで予約したいです"), llm_call, NOW)

        self.assertEqual(result.detail, "unregistered_menu")
        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("未登録メニューでのご予約希望", owner_messages[0])

    def test_line_push_failed_notifies_owner(self):
        push = FlakyLinePushClient(fail_count=2)
        processor, flow, push, logs = _new_processor(push_client=push, owner_user_id="U-owner")

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event("U1", "予約したいです"), llm_call, NOW)

        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("LINE送信エラー", owner_messages[0])

    def test_owner_push_failure_does_not_recurse(self):
        push = FailForUserPushClient(failing_user_id="U-owner")
        processor, flow, push, logs = _new_processor(push_client=push, owner_user_id="U-owner")

        # 例外なく完了すれば_send()の再帰防止ガードが機能している。
        result = processor.process(
            _event("U1", "施術で肌荒れしたんですが大丈夫でしょうか"), self._escalation_llm_call(), NOW
        )

        self.assertEqual(result.action, "escalation_replied")
        self.assertEqual([uid for uid, _ in push.sent if uid == "U-owner"], [])
        self.assertEqual(logs.system_event_counts.get("line_push_failed"), 1)


class EscalationWindowFlushTests(unittest.TestCase):
    """owner-notification-channel-design.mdの残課題だったflush_escalation_windows()
    (Cloud Scheduler経由のまとめ通知)のテスト。
    """

    def _escalation_llm_call(self, reason=None, feature_hint=None):
        def call():
            output = {
                "intent": "escalation", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
            }
            if reason:
                output["escalation_reason"] = reason
            if feature_hint:
                output["feature_hint"] = feature_hint
            return output

        return call

    def test_second_escalation_within_window_is_queued_then_flushed_as_digest(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")

        processor.process(_event("U1", "肌荒れの相談"), self._escalation_llm_call(), NOW)
        self.assertEqual(len([t for uid, t in push.sent if uid == "U-owner"]), 1)

        # 5分ウィンドウ内の2回目は即時通知されずキューに貯まる。
        processor.process(
            _event("U1", "デポジット決済できますか"),
            self._escalation_llm_call("unimplemented_feature", "デポジット決済"),
            NOW + timedelta(minutes=2),
        )
        self.assertEqual(len([t for uid, t in push.sent if uid == "U-owner"]), 1)

        sent = processor.flush_escalation_windows(NOW + timedelta(minutes=6))

        self.assertEqual(sent, 1)
        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 2)
        self.assertIn("【まとめてご確認】", owner_messages[-1])
        self.assertIn("未対応機能に関するお問い合わせ", owner_messages[-1])

    def test_flush_returns_zero_when_owner_not_configured(self):
        processor, flow, push, logs = _new_processor(owner_user_id=None)
        processor.process(_event("U1", "肌荒れの相談"), self._escalation_llm_call(), NOW)

        sent = processor.flush_escalation_windows(NOW + timedelta(minutes=6))

        self.assertEqual(sent, 0)

    def test_flush_skips_window_with_only_non_notable_events(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")

        def chitchat_call():
            return {
                "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
                "confirmed": False, "needs_owner_check": False,
            }

        processor.process(_event("U1", "こんにちは!"), chitchat_call, NOW)
        processor.process(_event("U1", "(URLのみのメッセージ)"), chitchat_call, NOW + timedelta(minutes=1))

        sent = processor.flush_escalation_windows(NOW + timedelta(minutes=6))

        self.assertEqual(sent, 0)
        self.assertEqual([uid for uid, _ in push.sent if uid == "U-owner"], [])


class FlowInternalEventOwnerNotificationTests(unittest.TestCase):
    """escalation-notification-templates.md「次のステップ候補」準拠。
    ConversationFlowStateMachine内部(booking_conflict/candidate_selection_unresolved/
    booking_cancelled/booking_change_started)から発火するイベントが、owner_notify_actions経由で
    実際にオーナーへpushされるようになったことを確認する。owner_user_id未設定のテストでは
    従来通りEscalationConsolidatorのウィンドウ記録のみを既存テストで確認済みのため、
    ここではowner_user_id="U-owner"を設定して実際のpushの有無まで検証する。
    """

    def _present_candidates(self, processor, user_id="U1"):
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜", "confirmed": False, "needs_owner_check": False,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        return processor.process(_event(user_id, "来週土曜カットで"), llm_call, NOW)

    def _select_first_candidate(self, processor, user_id="U1"):
        def llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
            }

        return processor.process(_event(user_id, "1番で"), llm_call, NOW)

    def _confirm_details(self, processor, user_id="U1", name="山田"):
        def llm_call():
            return {
                "intent": "new_booking", "name": name, "menu": "カット",
                "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
            }

        return processor.process(_event(user_id, f"{name}です、カットでお願いします"), llm_call, NOW)

    def test_booking_conflict_pushes_owner_notification(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")
        self._present_candidates(processor)
        self._select_first_candidate(processor)

        # 別ユーザーの確定で横から枠を奪い、confirm()を確実に失敗させる
        # (test_booking_conflict_notifies_owner_once_and_represents_fresh_candidatesと同じ手法)。
        held_slot_key = next(iter(flow._slots._slots))
        flow._slots.release(held_slot_key)
        flow._slots.hold(held_slot_key, "OTHER_USER", NOW)
        flow._slots.confirm(held_slot_key, "OTHER_USER", NOW)

        self._confirm_details(processor, name="山田")

        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("予約枠の競合(システム)", owner_messages[0])
        self.assertEqual(logs.system_event_counts.get("booking_conflict"), 1)

    def test_candidate_selection_unresolved_pushes_owner_notification(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")
        self._present_candidates(processor)

        def unresolvable_llm_call():
            return {
                "intent": "new_booking", "name": None, "menu": "カット",
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": False,
            }

        # RECONFIRM_MAX_ATTEMPTS(=2)回までは再確認文言のみで、owner_notify_actionsは空。
        for _ in range(2):
            processor.process(_event("U1", "うーん、どうしよう"), unresolvable_llm_call, NOW)
        self.assertEqual([uid for uid, _ in push.sent if uid == "U-owner"], [])

        # 3回目でcandidate_selection_unresolvedが発火し、オーナーへ即時pushされる。
        processor.process(_event("U1", "うーん、どうしよう"), unresolvable_llm_call, NOW)

        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        self.assertEqual(len(owner_messages), 1)
        self.assertIn("候補選択が確定しなかった(システム)", owner_messages[0])
        self.assertEqual(logs.system_event_counts.get("candidate_selection_unresolved"), 1)

    def test_cancel_after_confirmed_pushes_owner_notification(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")
        self._present_candidates(processor)
        self._select_first_candidate(processor)
        self._confirm_details(processor, name="山田")

        def cancel_llm_call():
            return {
                "intent": "cancel", "name": None, "menu": None,
                "datetime_candidate": None, "confirmed": False, "needs_owner_check": True,
            }

        processor.process(_event("U1", "キャンセルでお願いします"), cancel_llm_call, NOW)

        # この会話は店舗全体で最初の確定でもあるため、consume_first_booking_self_check()由来の
        # 別メッセージもオーナーへ届く(first-booking-self-check-notification-design.md)。
        # ここで見たいのはbooking_cancelledの即時通知そのものなので、該当メッセージだけを見る。
        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        cancel_messages = [m for m in owner_messages if "予約キャンセル(確定分)" in m]
        self.assertEqual(len(cancel_messages), 1)
        self.assertIn("山田様", cancel_messages[0])
        self.assertEqual(logs.system_event_counts.get("booking_cancelled"), 1)

    def test_change_after_confirmed_pushes_owner_notification(self):
        processor, flow, push, logs = _new_processor(owner_user_id="U-owner")
        self._present_candidates(processor)
        self._select_first_candidate(processor)
        self._confirm_details(processor, name="山田")

        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)

        def change_llm_call():
            return {
                "intent": "change", "name": None, "menu": "カット",
                "datetime_candidate": "来週土曜の別の時間に変更したい", "confirmed": False,
                "needs_owner_check": True,
                "requested_date_range": {"start": saturday.isoformat(), "end": saturday.isoformat()},
            }

        processor.process(_event("U1", "来週土曜の別の時間に変更できますか"), change_llm_call, NOW)

        # cancelと同じく、この会話は店舗全体で最初の確定でもあるため
        # 別途first-booking-self-check通知も届く。ここではbooking_change_started分のみ見る。
        owner_messages = [text for uid, text in push.sent if uid == "U-owner"]
        change_messages = [m for m in owner_messages if "予約変更(旧予約解放)" in m]
        self.assertEqual(len(change_messages), 1)
        self.assertIn("山田様", change_messages[0])
        self.assertEqual(logs.system_event_counts.get("booking_change_started"), 1)


if __name__ == "__main__":
    unittest.main()
