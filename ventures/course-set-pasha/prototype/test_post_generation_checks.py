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
    check_emoji_usage_rules,
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

    def test_comma_separated_same_sentence_area_mixup_is_detected(self):
        """post-generation-checks-cross-area-review.mdの「残る既知の限界」だった、
        読点区切りで1文にまとまっている場合(「エリアDは変更なし、エリアCは新着課題を
        追加しました。」)でも、エリアCの新着扱い(=違反)を見逃さないことを確認する回帰テスト。
        unchanged_areasに両エリアを含めることで、エリア名の出現位置を境界とした
        セグメント分割が働く。"""
        instance = {
            "sns_post": {
                "body": "エリアDは変更なし、エリアCは新着課題を追加しました。",
                "hashtags": [],
                "mentions_photo": False,
            },
            "line_web_notice": {"body": ""},
            "unchanged_areas": ["エリアC", "エリアD"],
        }
        errors = check_unchanged_areas_not_mentioned_as_new(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("エリアC", errors[0])

    def test_comma_separated_same_sentence_genuinely_unchanged_area_is_allowed(self):
        """上記と同じ文で、真に変更なしのエリアDの方は誤検出されないことを確認する。"""
        instance = {
            "sns_post": {
                "body": "エリアDは変更なし、エリアCは新着課題を追加しました。",
                "hashtags": [],
                "mentions_photo": False,
            },
            "line_web_notice": {"body": ""},
            "unchanged_areas": ["エリアD"],
        }
        errors = check_unchanged_areas_not_mentioned_as_new(instance)
        self.assertEqual(errors, [])

    def test_area_own_sentence_with_comma_is_not_over_split(self):
        """対象エリア自身の文が読点を含む場合(「エリアCは、新着課題を追加しました。」)に、
        他に既知のエリア名が無いときは文全体を1セグメントとして扱い、誤って分断して
        キーワードを見逃さないことを確認する。"""
        instance = {
            "sns_post": {
                "body": "エリアCは、新着課題を追加しました。",
                "hashtags": [],
                "mentions_photo": False,
            },
            "line_web_notice": {"body": ""},
            "unchanged_areas": ["エリアC"],
        }
        errors = check_unchanged_areas_not_mentioned_as_new(instance)
        self.assertEqual(len(errors), 1)

    def test_changed_area_from_history_rows_bounds_segment(self):
        """other_known_area_namesはunchanged_areasだけでなくhistory_rows(実際に変更した
        エリア)からも収集されることを確認する。変更エリアAの言及がunchanged_areasに
        列挙されていなくても、対象エリアCのセグメント境界として機能する。"""
        instance = {
            "sns_post": {
                "body": "エリアAは新着課題を追加、エリアCは変更ありません。",
                "hashtags": [],
                "mentions_photo": False,
            },
            "line_web_notice": {"body": ""},
            "unchanged_areas": ["エリアC"],
            "history_rows": [
                {
                    "revision_date": "2026-08-08",
                    "area": "エリアA",
                    "tape_color_or_grade_band": "赤",
                    "count": 5,
                    "feature_keywords": [],
                }
            ],
        }
        errors = check_unchanged_areas_not_mentioned_as_new(instance)
        self.assertEqual(errors, [])


class EmojiUsageRulesTest(unittest.TestCase):
    def test_sns_post_with_two_emoji_is_allowed(self):
        instance = {
            "sns_post": {
                "body": "エリアAに新着課題を追加しました🧗✨",
                "hashtags": [],
                "mentions_photo": False,
            }
        }
        self.assertEqual(check_emoji_usage_rules(instance), [])

    def test_sns_post_with_no_emoji_is_allowed(self):
        instance = {
            "sns_post": {
                "body": "エリアAに新着課題を追加しました。",
                "hashtags": [],
                "mentions_photo": False,
            }
        }
        self.assertEqual(check_emoji_usage_rules(instance), [])

    def test_sns_post_with_three_emoji_is_flagged(self):
        instance = {
            "sns_post": {
                "body": "エリアAに新着課題を追加しました🧗✨🔥",
                "hashtags": [],
                "mentions_photo": False,
            }
        }
        errors = check_emoji_usage_rules(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("sns_post", errors[0])

    def test_line_web_notice_with_emoji_is_flagged(self):
        instance = {
            "line_web_notice": {"body": "エリアAに新着課題を追加しました✨"},
        }
        errors = check_emoji_usage_rules(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("line_web_notice", errors[0])

    def test_line_web_notice_without_emoji_is_allowed(self):
        instance = {"line_web_notice": {"body": "エリアAに新着課題を追加しました。"}}
        self.assertEqual(check_emoji_usage_rules(instance), [])

    def test_history_rows_feature_keyword_with_emoji_is_flagged(self):
        instance = {
            "history_rows": [
                {
                    "revision_date": "2026-08-09",
                    "area": "エリアA",
                    "tape_color_or_grade_band": "赤",
                    "count": 5,
                    "feature_keywords": ["パワフル系🔥"],
                }
            ]
        }
        errors = check_emoji_usage_rules(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("history_rows", errors[0])

    def test_no_fields_present_is_skipped(self):
        self.assertEqual(check_emoji_usage_rules({}), [])


if __name__ == "__main__":
    unittest.main()
