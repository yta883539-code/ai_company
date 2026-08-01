#!/usr/bin/env python3
"""prototype/engine.py の自動テストスイート(unittest、外部ライブラリ非依存)。

位置づけ:
- これまでengine.pyの`_demo()`はprint文中心で、要所にassertを挟むのみだった
  (実行しないと壊れたことに気づけず、どの振る舞いが壊れたかも出力を目視するまで分からない)。
  本ファイルはそこから独立した、`python3 -m unittest`で実行できる正式なテストスイートとして
  主要な振る舞いをTestCaseに切り出したもの。
- `_demo()`はデモ・動作確認用の読み物として引き続き残し、置き換えない。
- 実LLM呼び出しは行わない(engine.py本体の方針を踏襲)。

実行方法: python3 -m unittest ventures/line-reservation-ai/prototype/test_engine.py -v
          (もしくはprototype/ディレクトリで python3 -m unittest test_engine -v)
"""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "schema"))

from engine import (  # noqa: E402
    AvailabilitySearcher,
    BookingSlotManager,
    BusinessHoursConfigError,
    ConversationFlowError,
    ConversationFlowStateMachine,
    EscalationConsolidator,
    NotificationLogAggregator,
    RECONFIRM_MAX_ATTEMPTS,
    format_confirmation_message,
    format_faq_parking_message,
    process_llm_output,
    resolve_candidate_selection,
    search_candidates_from_llm_output,
)

T0 = datetime(2026, 7, 31, 10, 0, 0)


class ProcessLlmOutputTest(unittest.TestCase):
    def test_succeeds_after_one_retry(self):
        attempts = iter([
            {"intent": "new_booking"},  # 必須フィールド不足 → NG
            {"intent": "new_booking", "name": "田中", "menu": "カット",
             "datetime_candidate": "来週土曜15時台の候補", "confirmed": False,
             "needs_owner_check": False},
        ])
        result = process_llm_output(lambda: next(attempts))
        self.assertFalse(result.used_fallback)
        self.assertEqual(result.retry_count, 1)

    def test_falls_back_after_exhausting_retries(self):
        attempts = iter([{"intent": "unknown_intent"}, {"intent": "unknown_intent"}])
        result = process_llm_output(lambda: next(attempts))
        self.assertTrue(result.used_fallback)
        self.assertEqual(result.output["intent"], "escalation")
        self.assertTrue(result.output["needs_owner_check"])


class EscalationConsolidatorTest(unittest.TestCase):
    def test_first_event_is_immediate_then_window_queues(self):
        c = EscalationConsolidator()
        first = c.on_event("user_sato", {"escalation_reason": None}, T0)
        self.assertEqual(first, [("immediate", {"escalation_reason": None})])

        second = c.on_event("user_sato", {"escalation_reason": None}, T0 + timedelta(minutes=2))
        self.assertEqual(second, [])  # ウィンドウ内 → キューに貯まるのみ

        flushed = c.flush_due_windows(T0 + timedelta(minutes=6))
        self.assertEqual(len(flushed), 1)
        user_id, queued = flushed[0]
        self.assertEqual(user_id, "user_sato")
        self.assertEqual(len(queued), 1)

    def test_refire_limit_switches_to_immediate(self):
        c = EscalationConsolidator()
        c.on_event("user_x", {}, T0)  # 1回目: immediate、ウィンドウを開く
        # ウィンドウ(5分)経過後に再発火させる
        c.on_event("user_x", {}, T0 + timedelta(minutes=6))  # refire 1
        c.on_event("user_x", {}, T0 + timedelta(minutes=12))  # refire 2
        third = c.on_event("user_x", {}, T0 + timedelta(minutes=18))  # refire 3 → 都度通知
        self.assertEqual(len(third), 1)
        self.assertEqual(third[0][0], "immediate_refire")

    def test_reset_after_30_minutes_of_silence(self):
        c = EscalationConsolidator()
        c.on_event("user_y", {}, T0)
        # 30分以上何も起きなければリセットされ、次のイベントは再び"immediate"(新規扱い)になる
        after_silence = c.on_event("user_y", {}, T0 + timedelta(minutes=31))
        self.assertEqual(after_silence, [("immediate", {})])


class NotificationLogAggregatorTest(unittest.TestCase):
    def test_unique_topic_counting_and_category_split(self):
        logs = NotificationLogAggregator()
        # 同日中の同一topic重複は1件扱い
        logs.record("user_tanaka", {"intent": "faq", "needs_owner_check": True,
                                     "faq_segments": [{"topic": "parking", "resolved": False}]}, T0)
        logs.record("user_tanaka", {"intent": "faq", "needs_owner_check": True,
                                     "faq_segments": [{"topic": "parking", "resolved": False}]},
                    T0 + timedelta(hours=1))
        self.assertEqual(logs.unique_unresolved_topic_count(), 1)

        logs.record("user_a", {"intent": "escalation", "needs_owner_check": True,
                                "escalation_reason": "unimplemented_feature"}, T0)
        self.assertEqual(logs.unimplemented_feature_count, 1)

        logs.record("user_b", {"intent": "escalation", "needs_owner_check": True,
                                "escalation_reason": None}, T0)
        self.assertEqual(logs.consultation_count, 1)

        logs.record("user_c", {"intent": "escalation", "needs_owner_check": True,
                                "escalation_reason": "booking_conflict"}, T0)
        self.assertEqual(logs.system_event_counts.get("booking_conflict"), 1)
        self.assertEqual(logs.system_event_total(), 1)
        # システム内部イベントは一般相談件数に混ざらない
        self.assertEqual(logs.consultation_count, 1)


class BookingSlotManagerTest(unittest.TestCase):
    def test_hold_confirm_and_conflict(self):
        slots = BookingSlotManager()
        key = ("shop_1", "2026-08-09", "15:30")
        self.assertTrue(slots.hold(key, "user_tanaka", T0))
        self.assertFalse(slots.hold(key, "user_suzuki", T0 + timedelta(minutes=1)))
        self.assertTrue(slots.confirm(key, "user_tanaka", T0 + timedelta(minutes=3)))

    def test_pending_times_out_and_frees_slot(self):
        slots = BookingSlotManager()
        key = ("shop_1", "2026-08-09", "17:00")
        slots.hold(key, "user_sato", T0)
        self.assertIsNone(slots.status(key, T0 + timedelta(minutes=7)))
        self.assertTrue(slots.hold(key, "user_takahashi", T0 + timedelta(minutes=7)))
        self.assertFalse(slots.confirm(key, "user_sato", T0 + timedelta(minutes=8)))


class ConversationFlowStateMachineTest(unittest.TestCase):
    def test_happy_path_to_confirmed(self):
        flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
        key = ("shop_1", "2026-08-09", "14:00")
        flow.present_candidates("user_tanaka", now=T0)
        result = flow.select_slot("user_tanaka", key, T0)
        self.assertTrue(result.success)
        self.assertTrue(flow.provide_details("user_tanaka", "田中", "カット", T0 + timedelta(minutes=2)))
        self.assertEqual(flow.stage("user_tanaka"), "confirmed")

    def test_select_slot_conflict_keeps_stage_and_returns_message(self):
        slots = BookingSlotManager()
        flow = ConversationFlowStateMachine(slots, EscalationConsolidator())
        key = ("shop_1", "2026-08-09", "14:00")
        flow.present_candidates("user_tanaka", now=T0)
        flow.select_slot("user_tanaka", key, T0)
        flow.provide_details("user_tanaka", "田中", "カット", T0 + timedelta(minutes=1))

        flow.present_candidates("user_yamada", now=T0 + timedelta(minutes=1))
        result = flow.select_slot("user_yamada", key, T0 + timedelta(minutes=1),
                                   slot_label="8/9(土) 14:00〜", alt_candidates="8/9(土) 17:00")
        self.assertFalse(result.success)
        self.assertIn("8/9(土) 14:00〜", result.message)
        self.assertEqual(flow.stage("user_yamada"), "candidates_presented")

    def test_confirm_conflict_reverts_to_candidates_presented(self):
        slots = BookingSlotManager()
        consolidator = EscalationConsolidator()
        flow = ConversationFlowStateMachine(slots, consolidator)
        key = ("shop_1", "2026-08-09", "16:00")

        flow.present_candidates("user_sato", now=T0)
        flow.select_slot("user_sato", key, T0)  # pending取得成功、7分放置してタイムアウトさせる

        flow.present_candidates("user_takahashi", now=T0 + timedelta(minutes=7))
        flow.select_slot("user_takahashi", key, T0 + timedelta(minutes=7))
        self.assertTrue(
            flow.provide_details("user_takahashi", "高橋", "カラー", T0 + timedelta(minutes=8))
        )

        # 佐藤さんが遅れてconfirmしようとしても、枠は既に高橋さんに確定済みなので失敗する
        confirmed = flow.provide_details("user_sato", "佐藤", "パーマ", T0 + timedelta(minutes=9))
        self.assertFalse(confirmed)
        self.assertEqual(flow.stage("user_sato"), "candidates_presented")
        # 横取りした高橋さんの確定は維持される(誤って解放されない)
        self.assertEqual(slots.status(key, T0 + timedelta(minutes=9)), "confirmed")

    def test_reconfirm_loop_escalates_after_max_attempts(self):
        candidates = [
            _fake_candidate(("shop_1", "2026-08-09", "14:00"), "8/9(土) 14:00〜"),
            _fake_candidate(("shop_1", "2026-08-09", "17:00"), "8/9(土) 17:00〜"),
        ]
        flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
        flow.present_candidates("user_takahashi_r", candidates, now=T0)

        for _ in range(RECONFIRM_MAX_ATTEMPTS):
            result = flow.select_slot_from_reply("user_takahashi_r", "午後がいいです", T0)
            self.assertFalse(result.success)
            self.assertEqual(flow.stage("user_takahashi_r"), "candidates_presented")

        escalated = flow.select_slot_from_reply("user_takahashi_r", "午後がいいです", T0)
        self.assertFalse(escalated.success)
        self.assertIn("担当より改めてご連絡", escalated.message)
        # エスカレーション後もcandidates_presentedのまま(呼び出し側が候補を再提示する想定)
        self.assertEqual(flow.stage("user_takahashi_r"), "candidates_presented")

    def test_unexpected_stage_call_raises(self):
        flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
        with self.assertRaises(ConversationFlowError):
            flow.provide_details("nobody", "名前", "メニュー", T0)

    def test_release_idle_conversations_frees_hold_but_keeps_confirmed(self):
        slots = BookingSlotManager()
        flow = ConversationFlowStateMachine(slots, EscalationConsolidator())

        idle_key = ("shop_1", "2026-08-09", "18:30")
        flow.present_candidates("user_nakamura", now=T0)
        flow.select_slot("user_nakamura", idle_key, T0)

        confirmed_key = ("shop_1", "2026-08-09", "19:00")
        flow.present_candidates("user_kobayashi", now=T0)
        flow.select_slot("user_kobayashi", confirmed_key, T0)
        flow.provide_details("user_kobayashi", "小林", "カット", T0 + timedelta(minutes=2))

        released = flow.release_idle_conversations(T0 + timedelta(minutes=31))
        released_ids = {r.user_id: r.stage for r in released}
        self.assertEqual(released_ids.get("user_nakamura"), "awaiting_details")
        self.assertIsNone(flow.stage("user_nakamura"))
        self.assertEqual(flow.stage("user_kobayashi"), "confirmed")  # confirmed済みは対象外

    def test_archive_completed_conversations_waits_one_day_past_visit(self):
        flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
        key = ("shop_1", "2026-07-31", "16:00")
        flow.present_candidates("user_sato", now=T0)
        flow.select_slot("user_sato", key, T0)
        flow.provide_details("user_sato", "佐藤", "カラー", T0 + timedelta(minutes=1))

        same_day = flow.archive_completed_conversations(T0 + timedelta(hours=8))
        self.assertEqual(same_day, [])
        self.assertEqual(flow.stage("user_sato"), "confirmed")

        two_days_later = flow.archive_completed_conversations(T0 + timedelta(days=2))
        self.assertEqual(two_days_later, ["user_sato"])
        self.assertIsNone(flow.stage("user_sato"))

    def test_maybe_run_idle_cleanup_throttles_within_min_interval(self):
        flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
        flow.present_candidates("user_endo", now=T0)

        first = flow.maybe_run_idle_cleanup(T0)
        self.assertEqual(first, [])  # まだ誰も失効していない

        skipped = flow.maybe_run_idle_cleanup(T0 + timedelta(minutes=2))
        self.assertIsNone(skipped)  # 間引き対象

        third = flow.maybe_run_idle_cleanup(T0 + timedelta(minutes=31))
        self.assertEqual([r.user_id for r in third], ["user_endo"])


class AvailabilitySearcherTest(unittest.TestCase):
    def test_excludes_confirmed_slot(self):
        searcher = AvailabilitySearcher(business_hours=(9 * 60, 19 * 60))
        slots = BookingSlotManager()
        booked = ("shop_1", "2026-08-09", "15:30")
        slots.hold(booked, "user_existing", T0)
        slots.confirm(booked, "user_existing", T0)

        found = searcher.find_candidates(
            store_id="shop_1", date_range=(date(2026, 8, 9), date(2026, 8, 10)),
            time_of_day_preference="afternoon", menu_duration_minutes=60,
            booking_slots=slots, now=T0, max_candidates=3,
        )
        self.assertTrue(all(c.slot_key != booked for c in found))

    def test_excludes_closed_weekday(self):
        searcher = AvailabilitySearcher(business_hours=(9 * 60, 19 * 60), closed_weekdays=frozenset({6}))
        found = searcher.find_candidates(
            store_id="shop_1", date_range=(date(2026, 8, 9), date(2026, 8, 10)),
            time_of_day_preference="afternoon", menu_duration_minutes=60,
            booking_slots=BookingSlotManager(), now=T0, max_candidates=3,
        )
        self.assertTrue(all(c.slot_key[1] != "2026-08-09" for c in found))  # 8/9(日)は定休日

    def test_weekday_business_hours_override(self):
        searcher = AvailabilitySearcher(
            business_hours=(9 * 60, 19 * 60), weekday_business_hours={5: (10 * 60, 15 * 60)},
        )
        outside_hours = searcher.find_candidates(
            store_id="shop_1", date_range=(date(2026, 8, 8), date(2026, 8, 8)),
            time_of_day_preference="evening", menu_duration_minutes=60,
            booking_slots=BookingSlotManager(), now=T0, max_candidates=5,
        )
        self.assertEqual(outside_hours, [])

        within_hours = searcher.find_candidates(
            store_id="shop_1", date_range=(date(2026, 8, 8), date(2026, 8, 8)),
            time_of_day_preference=None, menu_duration_minutes=60,
            booking_slots=BookingSlotManager(), now=T0, max_candidates=5,
        )
        self.assertTrue(all(10 * 60 <= c.start_minutes and c.start_minutes + 60 <= 15 * 60
                             for c in within_hours))

    def test_lunch_break_excluded_from_candidates(self):
        searcher = AvailabilitySearcher(business_hours=[(9 * 60, 12 * 60), (15 * 60, 19 * 60)])
        found = searcher.find_candidates(
            store_id="shop_1", date_range=(date(2026, 8, 10), date(2026, 8, 10)),
            time_of_day_preference=None, menu_duration_minutes=60,
            booking_slots=BookingSlotManager(), now=T0, max_candidates=20,
        )
        self.assertTrue(all(not (12 * 60 <= c.start_minutes < 15 * 60) for c in found))
        self.assertIn(11 * 60, [c.start_minutes for c in found])
        self.assertIn(15 * 60, [c.start_minutes for c in found])

    def test_rejects_overlapping_and_inverted_ranges_but_allows_adjacent(self):
        with self.assertRaises(BusinessHoursConfigError):
            AvailabilitySearcher(business_hours=[(9 * 60, 15 * 60), (12 * 60, 19 * 60)])
        with self.assertRaises(BusinessHoursConfigError):
            AvailabilitySearcher(business_hours=(15 * 60, 9 * 60))
        with self.assertRaises(BusinessHoursConfigError):
            AvailabilitySearcher(business_hours=(9 * 60, 19 * 60),
                                  weekday_business_hours={5: (10 * 60, 10 * 60)})
        # 隣接するだけ(終了=次の開始)は重複扱いにせず許可する
        try:
            AvailabilitySearcher(
                business_hours=(9 * 60, 19 * 60),
                weekday_business_hours={5: [(9 * 60, 12 * 60), (12 * 60, 15 * 60)]},
            )
        except BusinessHoursConfigError:
            self.fail("隣接区間(重複なし)はBusinessHoursConfigErrorを送出しないはず")


class SearchCandidatesFromLlmOutputTest(unittest.TestCase):
    def test_returns_none_when_date_range_missing(self):
        searcher = AvailabilitySearcher(business_hours=(9 * 60, 19 * 60))
        output = {"requested_date_range": None, "time_of_day_preference": "afternoon"}
        result = search_candidates_from_llm_output(
            searcher, BookingSlotManager(), "shop_1", output, 60, T0
        )
        self.assertIsNone(result)

    def test_connects_llm_output_to_search(self):
        searcher = AvailabilitySearcher(business_hours=(9 * 60, 19 * 60))
        output = {
            "requested_date_range": {"start": "2026-08-09", "end": "2026-08-09"},
            "time_of_day_preference": "afternoon",
        }
        result = search_candidates_from_llm_output(
            searcher, BookingSlotManager(), "shop_1", output, 60, T0
        )
        self.assertTrue(len(result) > 0)
        self.assertTrue(all(c.slot_key[1] == "2026-08-09" for c in result))


class ResolveCandidateSelectionTest(unittest.TestCase):
    def setUp(self):
        self.candidates = [
            _fake_candidate(("shop_1", "2026-08-09", "14:00"), "8/9(土) 14:00〜"),
            _fake_candidate(("shop_1", "2026-08-09", "17:00"), "8/9(土) 17:00〜"),
            _fake_candidate(("shop_1", "2026-08-10", "14:00"), "8/10(日) 14:00〜"),
        ]

    def test_plain_digit(self):
        self.assertEqual(resolve_candidate_selection("2", self.candidates),
                          self.candidates[1].slot_key)

    def test_fullwidth_ordinal(self):
        self.assertEqual(resolve_candidate_selection("２番目でお願いします", self.candidates),
                          self.candidates[1].slot_key)

    def test_kanji_digit(self):
        self.assertEqual(resolve_candidate_selection("三番でお願いします", self.candidates),
                          self.candidates[2].slot_key)

    def test_natural_text_date_and_time_match(self):
        result = resolve_candidate_selection("8/9の14:00〜でお願いします", self.candidates)
        self.assertEqual(result, self.candidates[0].slot_key)

    def test_weekday_suffix_does_not_break_matching(self):
        # ラベル自体に曜日"(土)"が含まれていても、曜日抜きの返信で一致すること
        result = resolve_candidate_selection("8/9の17:00でお願いします", self.candidates)
        self.assertEqual(result, self.candidates[1].slot_key)

    def test_unresolvable_reply_returns_none(self):
        self.assertIsNone(resolve_candidate_selection("午後がいいです", self.candidates))


class ToneRenderingTest(unittest.TestCase):
    def test_known_tone_selects_matching_variant(self):
        formal = format_confirmation_message("8/9(土) 15:30〜", "カット", "田中", tone="formal")
        casual = format_confirmation_message("8/9(土) 15:30〜", "カット", "田中", tone="casual")
        self.assertNotEqual(formal, casual)
        self.assertIn("田中様", formal)
        self.assertIn("田中様", casual)

    def test_unknown_tone_falls_back_to_standard(self):
        unknown = format_faq_parking_message("3", tone="loud")
        standard = format_faq_parking_message("3", tone="standard")
        self.assertEqual(unknown, standard)


def _fake_candidate(slot_key, label):
    from engine import _Candidate  # noqa: E402 (テスト専用にプライベート型を直接利用)
    return _Candidate(slot_key=slot_key, label=label, start_minutes=0)


if __name__ == "__main__":
    unittest.main()
