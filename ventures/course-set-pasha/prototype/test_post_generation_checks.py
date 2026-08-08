#!/usr/bin/env python3
"""post_generation_checks.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(机上で書き起こした期待JSON出力サンプル、
G1〜G4・OOS1・II1)を再利用し、いずれも後処理チェックに違反しないことを確認したうえで、
意図的に厳守事項2・3へ違反させた入力が正しく検出されることを確認する。

実行方法: python3 -m unittest test_post_generation_checks -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from post_generation_checks import (  # noqa: E402
    check_mentions_photo_consistency,
    check_unchanged_areas_not_mentioned_as_new,
    run_all_checks,
)


class FixtureCasesTest(unittest.TestCase):
    """schema/validate_test_cases.mdの既存フィクスチャは、机上で「厳守事項を守った」
    前提で書かれた出力例のため、いずれの後処理チェックにも違反しないはずである。"""

    def test_all_fixture_cases_pass_all_checks(self):
        for case_id, instance in TEST_CASES.items():
            with self.subTest(case=case_id):
                errors = run_all_checks(instance)
                self.assertEqual(errors, [], f"{case_id}: {errors}")


class MentionsPhotoConsistencyTest(unittest.TestCase):
    def test_true_without_body_reference_is_flagged(self):
        instance = {
            "sns_post": {
                "body": "エリアAに新着課題を追加しました。",
                "hashtags": [],
                "mentions_photo": True,
            }
        }
        errors = check_mentions_photo_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_false_with_body_reference_is_flagged(self):
        instance = {
            "sns_post": {
                "body": "写真の課題をご覧ください。",
                "hashtags": [],
                "mentions_photo": False,
            }
        }
        errors = check_mentions_photo_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_no_sns_post_is_skipped(self):
        instance = {"sns_post": None}
        self.assertEqual(check_mentions_photo_consistency(instance), [])


class UnchangedAreasNotMentionedAsNewTest(unittest.TestCase):
    def test_unchanged_area_mentioned_as_new_is_flagged(self):
        instance = {
            "sns_post": {
                "body": "エリアCに新着課題を追加しました。",
                "hashtags": [],
                "mentions_photo": False,
            },
            "line_web_notice": {"body": ""},
            "unchanged_areas": ["エリアC"],
        }
        errors = check_unchanged_areas_not_mentioned_as_new(instance)
        self.assertEqual(len(errors), 1)

    def test_unchanged_area_mentioned_with_unchanged_wording_is_allowed(self):
        instance = {
            "sns_post": {
                "body": "エリアBの新着課題をご紹介。エリアCは変更ありません。",
                "hashtags": [],
                "mentions_photo": False,
            },
            "line_web_notice": {"body": ""},
            "unchanged_areas": ["エリアC"],
        }
        errors = check_unchanged_areas_not_mentioned_as_new(instance)
        self.assertEqual(errors, [])

    def test_no_unchanged_areas_is_skipped(self):
        instance = {"sns_post": {"body": "", "hashtags": [], "mentions_photo": False}, "unchanged_areas": []}
        self.assertEqual(check_unchanged_areas_not_mentioned_as_new(instance), [])

    def test_unrelated_areas_unchanged_wording_does_not_mask_real_violation(self):
        """別エリア(D)の「変更ありません」が、対象エリア(C)自身の新着扱い(=違反)を
        誤って見逃させないことを確認する回帰テスト。"""
        instance = {
            "sns_post": {
                "body": "エリアDは変更ありません。エリアCに新着課題を追加しました。",
                "hashtags": [],
                "mentions_photo": False,
            },
            "line_web_notice": {"body": ""},
            "unchanged_areas": ["エリアC"],
        }
        errors = check_unchanged_areas_not_mentioned_as_new(instance)
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
