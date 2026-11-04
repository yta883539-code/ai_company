#!/usr/bin/env python3
"""post_generation_checks.pyの自動テスト。

validate_test_cases.pyのTEST_CASES(机上で書き起こした期待JSON出力サンプル、N1・N2・N3・
N4_skip・N4_join・E1・E2・E3・E4)を再利用し、いずれも絵文字不使用チェックに違反しないことを
確認したうえで、意図的に絵文字を混入させた入力が検出されることを確認する。

実行方法: python3 -m unittest test_post_generation_checks -v
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_test_cases import TEST_CASES  # noqa: E402

from post_generation_checks import (  # noqa: E402
    check_no_emoji_anywhere,
    check_no_heading_brackets_anywhere,
    run_all_checks,
)


class FixtureCasesTest(unittest.TestCase):
    """validate_test_cases.pyの既存フィクスチャは、机上で「ですます調・絵文字不使用」
    前提で書かれた出力例のため、いずれも絵文字不使用チェックに違反しないはずである。"""

    def test_all_fixture_cases_pass_all_checks(self):
        for case_id, raw_instance in TEST_CASES.items():
            instance = {k: v for k, v in raw_instance.items() if not k.startswith("_")}
            with self.subTest(case=case_id):
                errors = run_all_checks(instance)
                self.assertEqual(errors, [], f"{case_id}: {errors}")


class CheckNoEmojiAnywhereTest(unittest.TestCase):
    def test_out_of_scope_message_with_emoji_is_flagged(self):
        instance = {
            "status": "out_of_scope",
            "out_of_scope_message": "実際の予約・決済代行は行っておりません😊",
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("out_of_scope_message", errors[0])

    def test_nested_itinerary_draft_field_with_emoji_is_flagged(self):
        instance = {
            "itinerary_draft": [
                {
                    "venue_name_input": "東京ドーム",
                    "nearest_station_note": "水道橋駅から徒歩5分前後✨",
                }
            ]
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("itinerary_draft[0].nearest_station_note", errors[0])

    def test_list_of_strings_with_emoji_is_flagged(self):
        instance = {
            "itinerary_draft": [
                {"lodging_area_candidates": ["水道橋駅周辺🎉", "後楽園駅周辺"]}
            ]
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("lodging_area_candidates[0]", errors[0])

    def test_day_timetable_action_with_emoji_is_flagged(self):
        instance = {
            "day_timetable": [
                {
                    "venue_name_input": "東京ドーム",
                    "timetable": [{"time_label": "開場目安", "action": "会場入り🙌"}],
                }
            ]
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)

    def test_multiple_emoji_in_single_field_are_counted(self):
        instance = {"missing_fields_request": "会場名をお知らせください😀😀"}
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("2個", errors[0])

    def test_text_without_emoji_is_not_flagged(self):
        instance = {
            "out_of_scope_message": "本サービスは遠征プランの下書き生成支援のみを行っております。",
            "cost_estimate": {"note": "予算総額の目安内訳です。"},
        }
        self.assertEqual(check_no_emoji_anywhere(instance), [])

    def test_non_string_values_are_ignored(self):
        instance = {
            "status": "generated",
            "hashigo_check": {"applicable": False, "risk_level": None, "note": None},
        }
        self.assertEqual(check_no_emoji_anywhere(instance), [])


class CheckNoHeadingBracketsAnywhereTest(unittest.TestCase):
    def test_out_of_scope_message_with_heading_brackets_is_flagged(self):
        instance = {
            "status": "out_of_scope",
            "out_of_scope_message": "【ご確認ください】実際の予約・決済代行は行っておりません。",
        }
        errors = check_no_heading_brackets_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("out_of_scope_message", errors[0])

    def test_nested_itinerary_draft_field_with_heading_brackets_is_flagged(self):
        instance = {
            "itinerary_draft": [
                {
                    "venue_name_input": "東京ドーム",
                    "nearest_station_note": "【注意】水道橋駅から徒歩5分前後。",
                }
            ]
        }
        errors = check_no_heading_brackets_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("itinerary_draft[0].nearest_station_note", errors[0])

    def test_multiple_brackets_in_single_field_are_counted(self):
        instance = {"missing_fields_request": "【必須】会場名をお知らせください【任意】日程も"}
        errors = check_no_heading_brackets_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("4個", errors[0])

    def test_text_without_heading_brackets_is_not_flagged(self):
        instance = {
            "out_of_scope_message": "本サービスは遠征プランの下書き生成支援のみを行っております。",
            "cost_estimate": {"note": "予算総額の目安内訳です。"},
        }
        self.assertEqual(check_no_heading_brackets_anywhere(instance), [])

    def test_all_fixture_cases_pass_heading_brackets_check(self):
        for case_id, raw_instance in TEST_CASES.items():
            instance = {k: v for k, v in raw_instance.items() if not k.startswith("_")}
            with self.subTest(case=case_id):
                errors = check_no_heading_brackets_anywhere(instance)
                self.assertEqual(errors, [], f"{case_id}: {errors}")


class SingleFixtureMutationTest(unittest.TestCase):
    """既存フィクスチャ(N1)を複製し、1フィールドだけ絵文字を混入させても検出できることを
    確認する(フィクスチャ全体が絵文字を含まない前提に依存しすぎていないかの確認)。"""

    def test_mutated_n1_transport_note_is_flagged(self):
        instance = copy.deepcopy(TEST_CASES["N1"])
        instance = {k: v for k, v in instance.items() if not k.startswith("_")}
        instance["itinerary_draft"][0]["transport_note"] += "🚄"
        errors = run_all_checks(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("transport_note", errors[0])


if __name__ == "__main__":
    unittest.main()
