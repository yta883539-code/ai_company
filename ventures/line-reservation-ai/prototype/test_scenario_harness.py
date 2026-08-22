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


if __name__ == "__main__":
    unittest.main()
