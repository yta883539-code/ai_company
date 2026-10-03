#!/usr/bin/env python3
"""post_generation_checks.pyの自動テスト。

schema/validate_test_cases.pyのPOSITIVE_CASES(机上で書き起こした、厳守事項を守った
前提の期待JSON出力サンプル)を再利用し、いずれも後処理チェックに違反しないことを
確認したうえで、意図的に厳守事項6・7へ違反させた入力が正しく検出されることを確認する。
kura-pasha/course-set-pasha/aircon-pashaのprototype/test_post_generation_checks.pyと
同じ構成を踏襲する。

実行方法: python3 -m unittest test_post_generation_checks -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import POSITIVE_CASES  # noqa: E402

from post_generation_checks import (  # noqa: E402
    check_no_emoji_anywhere,
    check_no_out_of_scope_topics_in_generated_output,
    run_all_checks,
)


class FixtureCasesTest(unittest.TestCase):
    """schema/validate_test_cases.pyの既存フィクスチャ(G1〜G4・OOS1・II1〜II3)は、
    机上で「厳守事項を守った」前提で書かれた出力例のため、いずれの後処理チェックにも
    違反しないはずである。"""

    def test_all_fixture_cases_pass_all_checks(self):
        for case_id, instance in POSITIVE_CASES.items():
            with self.subTest(case=case_id):
                errors = run_all_checks(instance)
                self.assertEqual(errors, [], f"{case_id}: {errors}")


class NoEmojiAnywhereTest(unittest.TestCase):
    def test_emoji_in_inspection_record_body_is_flagged(self):
        instance = {
            "inspection_record": {
                "body": "2026-10-03 2号機 始業前点検 山田太郎 異常なし👍",
                "reminder_notice": None,
            }
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("inspection_record.body", errors[0])

    def test_emoji_in_reminder_notice_is_flagged(self):
        instance = {
            "inspection_record": {
                "body": "2025-11-05 2号機 月次自主検査 異常なし",
                "reminder_notice": "次回実施期限が近づいています⚠️",
            }
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("inspection_record.reminder_notice", errors[0])

    def test_emoji_in_out_of_scope_message_is_flagged(self):
        instance = {
            "out_of_scope_message": "本サービスは点検記録の整形と実施期限の管理支援のみを行っております🙏",
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("out_of_scope_message", errors[0])

    def test_emoji_in_missing_fields_request_is_flagged(self):
        instance = {
            "missing_fields_request": "車両番号が読み取れませんでした📝",
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("missing_fields_request", errors[0])

    def test_no_emoji_is_not_flagged(self):
        instance = {
            "inspection_record": {
                "body": "2026-10-03 2号機 始業前点検 山田太郎 異常なし",
                "reminder_notice": "次回実施期限が近づいています。",
            }
        }
        self.assertEqual(check_no_emoji_anywhere(instance), [])

    def test_absent_fields_are_skipped(self):
        instance = {"inspection_record": None, "out_of_scope_message": None, "missing_fields_request": None}
        self.assertEqual(check_no_emoji_anywhere(instance), [])


class OutOfScopeTopicsTest(unittest.TestCase):
    def test_repair_keyword_in_body_is_flagged(self):
        instance = {
            "status": "generated",
            "inspection_record": {
                "body": "ブレーキに異常があったため修理を手配いたします。",
                "reminder_notice": None,
            },
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertTrue(any("inspection_record.body" in e for e in errors))

    def test_parts_estimate_keyword_in_reminder_notice_is_flagged(self):
        instance = {
            "status": "generated",
            "inspection_record": {
                "body": "2026-10-03 2号機 始業前点検 異常なし",
                "reminder_notice": "部品の見積りをご用意します。",
            },
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertTrue(any("inspection_record.reminder_notice" in e for e in errors))

    def test_not_generated_status_is_skipped(self):
        instance = {
            "status": "out_of_scope",
            "inspection_record": None,
            "out_of_scope_message": "本サービスは点検記録の整形と実施期限の管理支援のみを行っております。",
        }
        self.assertEqual(check_no_out_of_scope_topics_in_generated_output(instance), [])

    def test_clean_generated_output_is_not_flagged(self):
        instance = {
            "status": "generated",
            "inspection_record": {
                "body": "2026-10-03 2号機 始業前点検 山田太郎 ブレーキ○、警告灯○、異音なし 異常なし",
                "reminder_notice": None,
            },
        }
        self.assertEqual(check_no_out_of_scope_topics_in_generated_output(instance), [])


if __name__ == "__main__":
    unittest.main()
