#!/usr/bin/env python3
"""prototype/scenario_harness.py の自動テストスイート(unittest、外部ライブラリ非依存)。

multi-turn-scenario-harness-design.mdで設計したN1→(選択)→N3の3ターンシナリオを試作し、
ハーネス自体が実際に複数ターンの状態遷移を連鎖・検証できることを確認する。

実行方法: python3 -m unittest test_scenario_harness -v
          (prototype/ディレクトリで実行)
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import ConversationEventProcessor, InMemoryLinePushClient  # noqa: E402
from engine import (  # noqa: E402
    SLOT_CONFLICT_MESSAGE_TEMPLATE,
    AvailabilitySearcher,
    BookingSlotManager,
    ConversationFlowStateMachine,
    EscalationConsolidator,
    NotificationLogAggregator,
)
from scenario_harness import ScenarioTurn, run_scenario  # noqa: E402

STORE_ID = "store-1"
MENU_DURATIONS = {"カット": 30, "カラー": 90}
NOW = datetime(2026, 8, 3, 10, 0)  # 月曜


def _new_processor():
    logs = NotificationLogAggregator()
    flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator(), logs=logs)
    searcher = AvailabilitySearcher(business_hours=(9 * 60, 18 * 60), slot_interval_minutes=30)
    push = InMemoryLinePushClient()
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
    return processor, flow, push


class N1ToN3ScenarioTest(unittest.TestCase):
    def _next_saturday(self) -> str:
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)
        return saturday.isoformat()

    def test_n1_search_to_n3_confirmation_across_three_real_turns(self):
        processor, flow, push = _new_processor()
        saturday = self._next_saturday()

        turns = [
            # ターン1: N1(「来週土曜15時にカットお願いしたいです。田中です。」)相当。
            # datetime_candidateは自然文の要旨のみで、AvailabilitySearcherへの入力は
            # requested_date_range/time_of_day_preferenceが担う(slot-search-component-
            # design.md準拠)。
            ScenarioTurn(
                message="来週土曜15時にカットお願いしたいです。田中です。",
                llm_output={
                    "intent": "new_booking",
                    "name": "田中",
                    "menu": "カット",
                    "datetime_candidate": "来週土曜15時",
                    "confirmed": False,
                    "needs_owner_check": False,
                    "requested_date_range": {"start": saturday, "end": saturday},
                    "time_of_day_preference": "afternoon",
                },
                expect_action="candidates_presented",
                expect_stage="candidates_presented",
            ),
            # ターン2: multi-turn-scenario-harness-design.md「発見」の通り、実装上
            # resolve_candidate_selection()は返信文言(番号・候補ラベルの日付時刻表記との
            # 一致)でのみ選択を特定するため、N3原文の指示語「その時間でお願いします」ではなく
            # 明示的な番号指定に置き換える。
            ScenarioTurn(
                message="1番で",
                llm_output={
                    "intent": "new_booking",
                    "name": None,
                    "menu": None,
                    "datetime_candidate": "1番目",
                    "confirmed": False,
                    "needs_owner_check": False,
                },
                expect_action="held",
                expect_stage="awaiting_details",
            ),
            # ターン3: N3の期待構造化出力(conversation-samples-test-cases.md記載)をそのまま
            # 転記。
            ScenarioTurn(
                message="その時間でお願いします",
                llm_output={
                    "intent": "new_booking",
                    "name": "田中",
                    "menu": "カット",
                    "datetime_candidate": "来週土曜15時",
                    "confirmed": True,
                    "needs_owner_check": False,
                },
                expect_action="confirmed",
                expect_stage="confirmed",
            ),
        ]

        results = run_scenario(processor, turns, NOW)

        self.assertEqual(len(results), 3)
        for step in results:
            self.assertEqual(step.schema_errors, [])
            self.assertEqual(step.cross_field_errors, [])

        self.assertIn("田中様", push.sent[-1][1])
        self.assertIn("カット", push.sent[-1][1])


class E3BookingConflictScenarioTest(unittest.TestCase):
    """conversation-samples-test-cases.md E3(二重予約、仮押さえ中の枠への競合)を、
    multi-turn-scenario-harness-design.md「残る課題」で挙げていた「他の崩れ系ケースを
    同じハーネスで再現する」の第一弾として、2ユーザーの会話をprocessor.process()のみで
    interleaveして再現する。

    既存のtest_cloud_function_process_event.pyのbooking_conflictテストは、確定操作時
    (provide_details→confirm())の競合をflow._slots.hold()/confirm()への直接操作で
    人工的に再現するのに対し、本テストはE3の入力例(「顧客Bが、顧客Aが仮押さえ中の枠を
    指定」)に忠実な選択操作時(select_slot_from_reply→hold())の競合を、内部状態への
    直接操作なしに2顧客分のprocessor.process()呼び出しのみで再現する点が異なる。
    AvailabilitySearcher.find_candidates()はbooking_slots.status()がNoneの枠のみを
    返す(engine.py 1364行目)ため、Bの検索がAのhold()より後だと競合枠がそもそも候補に
    出てこず本ケースを再現できない。そのため両者の検索(candidates_presented)を先に
    済ませてから、Aが選択→holdした「後」にBが同じ候補ラベルを選択する順序にしている。
    """

    def _next_saturday(self) -> str:
        saturday = NOW.date() + timedelta(days=(5 - NOW.weekday()) % 7 or 7)
        return saturday.isoformat()

    def _search_turn(self, user_id: str, message: str, saturday: str) -> ScenarioTurn:
        return ScenarioTurn(
            user_id=user_id,
            message=message,
            llm_output={
                "intent": "new_booking",
                "name": None,
                "menu": "カット",
                "datetime_candidate": "来週土曜午後の空き候補(複数)",
                "confirmed": False,
                "needs_owner_check": False,
                "requested_date_range": {"start": saturday, "end": saturday},
                "time_of_day_preference": "afternoon",
            },
            expect_action="candidates_presented",
            expect_stage="candidates_presented",
        )

    def test_second_customer_selecting_slot_already_held_by_first_gets_conflict_message(self):
        processor, flow, push = _new_processor()
        saturday = self._next_saturday()

        turns = [
            # 1. 顧客A・顧客Bとも同じ時間帯を検索し、同一の候補一覧(スロットはまだ誰も
            #    保持していない)を受け取る。E3の「顧客Bが顧客Aの仮押さえ中の枠を指定」を
            #    再現するための前提(=Bが候補を見た時点ではその枠はまだ空いていた)。
            self._search_turn("U_A", "来週土曜の午後にカットお願いしたいです。", saturday),
            self._search_turn("U_B", "土曜の午後、カットで空いてますか?", saturday),
            # 2. 顧客Aが1番目の候補を選び、hold()に成功する。
            ScenarioTurn(
                user_id="U_A",
                message="1番で",
                llm_output={
                    "intent": "new_booking", "name": None, "menu": None,
                    "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
                },
                expect_action="held",
                expect_stage="awaiting_details",
            ),
            # 3. 顧客Bが(Aの選択を知らないまま)自分の候補一覧の1番目、
            #    つまりAが今まさに保持した同じ枠を選ぶ。hold()が失敗し、
            #    候補提示状態のまま謝罪・代替案内メッセージが返る(needs_owner_checkなし、
            #    E3の期待挙動どおりシステム側で自動的に保留する)。
            ScenarioTurn(
                user_id="U_B",
                message="1番で",
                llm_output={
                    "intent": "new_booking", "name": None, "menu": None,
                    "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,
                },
                expect_action="reask",
                expect_stage="candidates_presented",
            ),
            # 4. Aは競合の影響を受けず、そのまま確定できる。
            ScenarioTurn(
                user_id="U_A",
                message="田中です",
                llm_output={
                    "intent": "new_booking", "name": "田中", "menu": "カット",
                    "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
                },
                expect_action="confirmed",
                expect_stage="confirmed",
            ),
            # 5. Bは自分の候補一覧から別の(まだ空いている)枠を選び直せば、通常どおりholdできる。
            #    競合が発生してもB側の会話状態(candidates_presented)自体は壊れないことの確認。
            ScenarioTurn(
                user_id="U_B",
                message="2番で",
                llm_output={
                    "intent": "new_booking", "name": None, "menu": None,
                    "datetime_candidate": "2番目", "confirmed": False, "needs_owner_check": False,
                },
                expect_action="held",
                expect_stage="awaiting_details",
            ),
        ]

        results = run_scenario(processor, turns, NOW)

        self.assertEqual(len(results), 6)
        for step in results:
            self.assertEqual(step.schema_errors, [])
            self.assertEqual(step.cross_field_errors, [])

        # Bへの案内メッセージは、内部操作で再現した既存テスト(booking_conflict、確定操作時の
        # 競合)が使うBOOKING_CONFLICT_RETRY_MESSAGEとは別の、選択操作時競合用の文言
        # (SLOT_CONFLICT_MESSAGE_TEMPLATE)であることを確認する。
        conflict_message = [msg for uid, msg in push.sent if uid == "U_B"][-2]
        self.assertIn("埋まってしまいました", conflict_message)
        self.assertNotIn("{slot_label}", conflict_message)  # フォーマット未適用の取りこぼしが無いこと
        self.assertTrue(
            conflict_message.startswith(SLOT_CONFLICT_MESSAGE_TEMPLATE.split("{slot_label}")[0])
        )

        # Aは正常に確定済み。
        self.assertEqual(flow.stage("U_A"), "confirmed")
        self.assertIn("田中様", [msg for uid, msg in push.sent if uid == "U_A"][-1])


class E1AmbiguousDatetimeScenarioTest(unittest.TestCase):
    """conversation-samples-test-cases.md E1(曖昧な日時表現)。
    multi-turn-scenario-harness-design.md「残る課題」で挙げていたE1のハーネス化に着手した
    ところ、E1の「期待される構造化出力」記載どおりの`menu: null`をそのまま投入すると、
    当時の実装ではドキュメントが想定する`candidates_presented`(複数候補提示)ではなく
    `forwarded_to_owner`(detail=`unregistered_menu`)になっていた(「メニュー未言及」と
    「メニュー未登録」を区別していなかったため)。menu-unmentioned-vs-unregistered-design.md
    でオプションb(メニュー未言及時は検索前に聞き返す)を採用し実装したため、現在は
    `menu: null`単独ターンでは`reask`(detail=`menu_not_mentioned`)になり、次ターンで
    メニューが判明すれば同じ日時範囲を引き継いで候補提示まで進む。本クラスでは
    (1)聞き返しになること、(2)聞き返し後にメニューが判明すると日時範囲を引き継いで候補提示
    まで進むこと、(3)メニューが最初から判明していれば単一ターンで候補提示に至ること、の
    3つを確認する。
    """

    def _next_week_weekday_range(self) -> tuple:
        # 「来週の平日」= 次の月曜日から金曜日まで。
        next_monday = NOW.date() + timedelta(days=(7 - NOW.weekday()) % 7 or 7)
        next_friday = next_monday + timedelta(days=4)
        return next_monday.isoformat(), next_friday.isoformat()

    def test_e1_literal_menu_null_reasks_for_menu_instead_of_forwarding(self):
        """conversation-samples-test-cases.mdのE1期待出力を一字一句そのまま投入した場合、
        `menu: null`は「未登録メニュー」ではなく「メニュー未言及」として扱われ、
        オーナー転送ではなく聞き返し(reask)になる。"""
        processor, flow, push = _new_processor()
        start, end = self._next_week_weekday_range()

        turns = [
            ScenarioTurn(
                message="来週の平日午後とかで空いてればお願いしたいです",
                llm_output={
                    "intent": "new_booking",
                    "name": None,
                    "menu": None,
                    "datetime_candidate": "来週平日午後の空き候補(複数)",
                    "confirmed": False,
                    "needs_owner_check": False,
                    "requested_date_range": {"start": start, "end": end},
                    "time_of_day_preference": "afternoon",
                },
                expect_action="reask",
            ),
        ]

        results = run_scenario(processor, turns, NOW)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].schema_errors, [])
        self.assertEqual(results[0].cross_field_errors, [])
        self.assertEqual(results[0].dispatch.detail, "menu_not_mentioned")
        self.assertIsNone(flow.stage("U1"))

    def test_e1_menu_follows_reask_carries_over_date_range_to_candidates(self):
        """聞き返し(reask)の後、次ターンで顧客がメニューのみ返信した場合、1ターン目で
        伝えた日時範囲(来週の平日午後)を引き継いで候補提示まで進む(オーナー転送を
        避けられる、というオプションb採用の狙い通りの挙動を確認する)。"""
        processor, flow, push = _new_processor()
        start, end = self._next_week_weekday_range()

        turns = [
            ScenarioTurn(
                message="来週の平日午後とかで空いてればお願いしたいです",
                llm_output={
                    "intent": "new_booking",
                    "name": None,
                    "menu": None,
                    "datetime_candidate": "来週平日午後の空き候補(複数)",
                    "confirmed": False,
                    "needs_owner_check": False,
                    "requested_date_range": {"start": start, "end": end},
                    "time_of_day_preference": "afternoon",
                },
                expect_action="reask",
            ),
            ScenarioTurn(
                message="カットでお願いします",
                llm_output={
                    "intent": "new_booking",
                    "name": None,
                    "menu": "カット",
                    "datetime_candidate": None,
                    "confirmed": False,
                    "needs_owner_check": False,
                },
                expect_action="candidates_presented",
                expect_stage="candidates_presented",
            ),
        ]

        results = run_scenario(processor, turns, NOW)

        self.assertEqual(len(results), 2)
        for step in results:
            self.assertEqual(step.schema_errors, [])
            self.assertEqual(step.cross_field_errors, [])
        # 1ターン目のREASK_MENU_MESSAGEのみが送られ、2ターン目は再度日時を尋ねずそのまま
        # 候補提示に進んだこと(=日時範囲の引き継ぎが機能したこと)をpush内容からも確認する。
        self.assertEqual(len(push.sent), 2)
        self.assertIn("メニュー", push.sent[0][1])
        self.assertIn("番号でお知らせください", push.sent[1][1])

    def test_e1_with_menu_known_stops_at_candidates_presented(self):
        """E1が意図する「複数候補を提示し選択を待つ(confirmed: falseのまま)」という挙動
        自体は、メニューが判明していれば(=会話中の別ターンで既に聞き取り済み、または
        今回のように発言に含まれていれば)実際に確認できる。複数日(平日5日分)にまたがる
        範囲指定のため、単一日に限定されない候補一覧が提示されることを確認する。"""
        processor, flow, push = _new_processor()
        start, end = self._next_week_weekday_range()

        turns = [
            ScenarioTurn(
                message="来週の平日午後とかでカットお願いしたいです",
                llm_output={
                    "intent": "new_booking",
                    "name": None,
                    "menu": "カット",
                    "datetime_candidate": "来週平日午後の空き候補(複数)",
                    "confirmed": False,
                    "needs_owner_check": False,
                    "requested_date_range": {"start": start, "end": end},
                    "time_of_day_preference": "afternoon",
                },
                expect_action="candidates_presented",
                expect_stage="candidates_presented",
            ),
        ]

        results = run_scenario(processor, turns, NOW)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].schema_errors, [])
        self.assertEqual(results[0].cross_field_errors, [])
        presented_message = push.sent[-1][1]
        # 平日5日分の候補が並ぶため、単一の日付だけでなく複数の候補行(番号付き)が
        # 含まれることを確認する。
        self.assertGreaterEqual(sum(presented_message.count(f"{n}.") for n in range(1, 6)), 2)
        self.assertEqual(flow.stage("U1"), "candidates_presented")


if __name__ == "__main__":
    unittest.main()
