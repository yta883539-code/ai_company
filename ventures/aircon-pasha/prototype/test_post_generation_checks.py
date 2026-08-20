#!/usr/bin/env python3
"""post_generation_checks.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(机上で書き起こした期待JSON出力サンプル、
G1〜G3・OOS1・II1)を再利用し、いずれも後処理チェックに違反しないことを確認したうえで、
意図的に厳守事項1・3・4・6へ違反させた入力が正しく検出されることを確認する。
course-set-pasha/prototype/test_post_generation_checks.pyと同じ構成を踏襲した。

実行方法: python3 -m unittest test_post_generation_checks -v
"""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from post_generation_checks import (  # noqa: E402
    check_additional_treatment_mentioned_in_text,
    check_model_type_mentioned_in_text,
    check_next_recommended_date_estimate_consistency,
    check_next_recommended_date_history_care_guide_consistency,
    check_no_out_of_scope_topics_in_generated_output,
    check_refrigerant_electrical_professional_judgement,
    run_all_checks,
)


class FixtureCasesTest(unittest.TestCase):
    """schema/validate_test_cases.pyの既存フィクスチャは、机上で「厳守事項を守った」
    前提で書かれた出力例のため、いずれの後処理チェックにも違反しないはずである。"""

    def test_all_fixture_cases_pass_all_checks(self):
        for case_id, instance in TEST_CASES.items():
            with self.subTest(case=case_id):
                errors = run_all_checks(instance)
                self.assertEqual(errors, [], f"{case_id}: {errors}")


class RefrigerantElectricalProfessionalJudgementTest(unittest.TestCase):
    def test_judgement_keyword_near_topic_keyword_is_flagged(self):
        instance = {
            "completion_report": {
                "body": "冷媒を確認したところ異常なしでしたので、そのまま分解洗浄いたしました。",
                "mentions_refrigerant_or_electrical": False,
            }
        }
        errors = check_refrigerant_electrical_professional_judgement(instance)
        self.assertEqual(len(errors), 1)

    def test_plain_mention_without_judgement_is_not_flagged(self):
        instance = {
            "completion_report": {
                "body": "冷媒配管まわりも含めて分解洗浄いたしました。",
                "mentions_refrigerant_or_electrical": True,
            }
        }
        errors = check_refrigerant_electrical_professional_judgement(instance)
        self.assertEqual(errors, [])

    def test_flag_true_without_body_mention_is_flagged(self):
        instance = {
            "completion_report": {
                "body": "フィルター・熱交換器まで分解洗浄いたしました。",
                "mentions_refrigerant_or_electrical": True,
            }
        }
        errors = check_refrigerant_electrical_professional_judgement(instance)
        self.assertEqual(len(errors), 1)

    def test_no_completion_report_is_skipped(self):
        self.assertEqual(
            check_refrigerant_electrical_professional_judgement({"completion_report": None}), []
        )


class NextRecommendedDateEstimateConsistencyTest(unittest.TestCase):
    def test_estimate_true_without_disclaimer_is_flagged(self):
        instance = {
            "care_guide": {
                "body": "次回の分解洗浄は1〜2年に1回程度が一般的な目安です。",
                "next_recommended_date_is_estimate": True,
            }
        }
        errors = check_next_recommended_date_estimate_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_estimate_false_with_disclaimer_is_flagged(self):
        instance = {
            "care_guide": {
                "body": "次回の分解洗浄は来年同時期を目安にご検討ください"
                        "(今回のメモに次回推奨時期の記載が無いため、あくまで一般的な目安です)。",
                "next_recommended_date_is_estimate": False,
            }
        }
        errors = check_next_recommended_date_estimate_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_estimate_true_with_disclaimer_is_not_flagged(self):
        instance = {
            "care_guide": {
                "body": "今回のメモに次回推奨時期の記載が無いため、あくまで一般的な目安として"
                        "1〜2年に1回程度をおすすめします。",
                "next_recommended_date_is_estimate": True,
            }
        }
        self.assertEqual(check_next_recommended_date_estimate_consistency(instance), [])


class NoOutOfScopeTopicsTest(unittest.TestCase):
    def test_reservation_keyword_in_generated_output_is_flagged(self):
        instance = {
            "status": "generated",
            "completion_report": {"body": "次回のご予約受付は当店LINEにて承っております。"},
            "care_guide": {"body": "フィルターは月1回程度お手入れください。"},
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertEqual(len(errors), 1)

    def test_out_of_scope_status_is_skipped(self):
        instance = {
            "status": "out_of_scope",
            "completion_report": None,
            "care_guide": None,
        }
        self.assertEqual(check_no_out_of_scope_topics_in_generated_output(instance), [])


class ModelTypeMentionedInTextTest(unittest.TestCase):
    def test_missing_model_type_in_body_is_flagged(self):
        instance = {
            "history_row": {"model_type_and_capacity": "壁掛け型2.2kW"},
            "completion_report": {"body": "エアコンの分解洗浄を実施いたしました。"},
        }
        errors = check_model_type_mentioned_in_text(instance)
        self.assertEqual(len(errors), 1)

    def test_null_model_type_is_skipped(self):
        instance = {
            "history_row": {"model_type_and_capacity": None},
            "completion_report": {"body": "エアコンの分解洗浄を実施いたしました。"},
        }
        self.assertEqual(check_model_type_mentioned_in_text(instance), [])


class AdditionalTreatmentMentionedInTextTest(unittest.TestCase):
    def test_missing_additional_treatment_in_body_is_flagged(self):
        instance = {
            "history_row": {"additional_treatment": "防カビコートあり"},
            "completion_report": {"body": "フィルター・熱交換器まで分解洗浄いたしました。"},
        }
        errors = check_additional_treatment_mentioned_in_text(instance)
        self.assertEqual(len(errors), 1)

    def test_no_additional_treatment_value_is_skipped(self):
        instance = {
            "history_row": {"additional_treatment": "なし"},
            "completion_report": {"body": "フィルター・熱交換器まで分解洗浄いたしました。"},
        }
        self.assertEqual(check_additional_treatment_mentioned_in_text(instance), [])


class NextRecommendedDateHistoryCareGuideConsistencyTest(unittest.TestCase):
    def test_not_estimate_but_empty_history_date_is_flagged(self):
        instance = {
            "care_guide": {"next_recommended_date_is_estimate": False},
            "history_row": {"next_recommended_date": None},
        }
        errors = check_next_recommended_date_history_care_guide_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_not_estimate_with_history_date_is_ok(self):
        instance = {
            "care_guide": {"next_recommended_date_is_estimate": False},
            "history_row": {"next_recommended_date": "2027-08"},
        }
        self.assertEqual(
            check_next_recommended_date_history_care_guide_consistency(instance), []
        )

    def test_estimate_with_empty_history_date_is_ok(self):
        instance = {
            "care_guide": {"next_recommended_date_is_estimate": True},
            "history_row": {"next_recommended_date": None},
        }
        self.assertEqual(
            check_next_recommended_date_history_care_guide_consistency(instance), []
        )

    def test_missing_sections_are_skipped(self):
        self.assertEqual(
            check_next_recommended_date_history_care_guide_consistency({}), []
        )


class RunAllChecksTest(unittest.TestCase):
    def test_multiple_violations_are_all_collected(self):
        instance = copy.deepcopy(TEST_CASES["G1_basic"])
        instance["completion_report"]["body"] = "冷媒を点検したところ異常なしでした。"
        instance["care_guide"]["next_recommended_date_is_estimate"] = True
        errors = run_all_checks(instance)
        self.assertGreaterEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
