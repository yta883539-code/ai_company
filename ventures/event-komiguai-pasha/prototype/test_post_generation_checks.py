#!/usr/bin/env python3
"""post_generation_checks.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(机上で書き起こした、厳守事項を守った前提の
期待JSON出力サンプル)を再利用し、いずれも後処理チェックに違反しないことを確認したうえで、
意図的に厳守事項7・9へ違反させた入力が正しく検出されることを確認する。
forklift-pasha/kura-pasha/course-set-pasha/aircon-pashaのprototype/
test_post_generation_checks.pyと同じ構成を踏襲する。

実行方法: python3 -m unittest test_post_generation_checks -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from post_generation_checks import (  # noqa: E402
    check_no_emoji_anywhere,
    check_no_out_of_scope_topics_in_generated_output,
    run_all_checks,
)


class FixtureCasesTest(unittest.TestCase):
    """schema/validate_test_cases.pyの既存フィクスチャ(G1〜G6・OOS1〜OOS2・II1)は、
    机上で「厳守事項を守った」前提で書かれた出力例のため、いずれの後処理チェックにも
    違反しないはずである。"""

    def test_all_fixture_cases_pass_all_checks(self):
        for case_id, instance in TEST_CASES.items():
            with self.subTest(case=case_id):
                errors = run_all_checks(instance)
                self.assertEqual(errors, [], f"{case_id}: {errors}")


class NoEmojiAnywhereTest(unittest.TestCase):
    def test_emoji_in_checklist_item_is_flagged(self):
        instance = {
            "checklist": [
                {"item": "入場口2箇所がキャパシティに対し十分な処理能力か👍", "highlighted": False},
            ],
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("checklist[0].item", errors[0])

    def test_emoji_in_staffing_plan_body_is_flagged(self):
        instance = {
            "staffing_plan": {
                "focus": "entry",
                "body": "開場直後の入場時集中に重点を置きます⚠️",
                "announcement_text": "分散してお進みください。",
            },
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("staffing_plan.body", errors[0])

    def test_emoji_in_notice_board_text_body_is_flagged(self):
        instance = {
            "notice_board_text": {
                "body": "ご来場の皆様へ、整列にご協力ください🙏",
                "includes_road_use_permit_note": False,
            },
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("notice_board_text.body", errors[0])

    def test_emoji_in_out_of_scope_message_is_flagged(self):
        instance = {
            "out_of_scope_message": "本サービスは一次チェックと文書下書き生成のみを行っております🙏",
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("out_of_scope_message", errors[0])

    def test_emoji_in_missing_fields_request_is_flagged(self):
        instance = {
            "missing_fields_request": "capacityの記載が見当たりません📝",
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing_fields_request", errors[0])

    def test_no_emoji_is_not_flagged(self):
        instance = {
            "checklist": [{"item": "入退場口の処理能力を確認", "highlighted": False}],
            "staffing_plan": {
                "focus": "entry",
                "body": "開場直後の入場時集中に重点を置きます。",
                "announcement_text": "分散してお進みください。",
            },
            "notice_board_text": {
                "body": "整列にご協力ください。",
                "includes_road_use_permit_note": False,
            },
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(errors, [])


class NoOutOfScopeTopicsTest(unittest.TestCase):
    def test_fee_topic_in_staffing_plan_body_is_flagged_when_generated(self):
        instance = {
            "status": "generated",
            "staffing_plan": {
                "focus": "entry",
                "body": "開場直後の入場時集中に重点を置きます。なお月額の料金プランは別途ご案内します。",
                "announcement_text": "分散してお進みください。",
            },
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertTrue(any("staffing_plan.body" in e for e in errors))

    def test_fee_topic_is_not_flagged_when_status_is_not_generated(self):
        instance = {
            "status": "out_of_scope",
            "staffing_plan": {
                "focus": "entry",
                "body": "月額の料金プランについてはご案内しておりません。",
                "announcement_text": "",
            },
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertEqual(errors, [])

    def test_fee_inquiry_note_itself_is_excluded_from_check(self):
        instance = {
            "status": "generated",
            "fee_inquiry_note": (
                "本サービスは一次チェックと文書下書き生成のみを行っております。"
                "料金プランについてのご案内は現時点では行っておりません。"
            ),
            "staffing_plan": {
                "focus": "entry",
                "body": "開場直後の入場時集中に重点を置きます。",
                "announcement_text": "分散してお進みください。",
            },
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertEqual(errors, [])

    def test_no_fee_topic_is_not_flagged(self):
        instance = {
            "status": "generated",
            "staffing_plan": {
                "focus": "entry",
                "body": "開場直後の入場時集中に重点を置きます。",
                "announcement_text": "分散してお進みください。",
            },
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
