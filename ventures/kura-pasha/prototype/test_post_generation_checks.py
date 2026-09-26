#!/usr/bin/env python3
"""post_generation_checks.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(机上で書き起こした期待JSON出力サンプル、
G1・G2・OOS1・C1〜C5・M1・M2・CT1・CT2・CTC1〜CTC3・CTE1・CO1〜CO3・WIR1・WIR2)を
再利用し、いずれも後処理チェックに違反しないことを確認したうえで、意図的に
厳守事項6・7a(iv)・7b(i)・7c(i)・8へ違反させた入力が正しく検出されることを確認する。
course-set-pasha/prototype/test_post_generation_checks.pyと同じ構成を踏襲する。

実行方法: python3 -m unittest test_post_generation_checks -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from post_generation_checks import (  # noqa: E402
    check_checkout_notice_no_url,
    check_delivery_notice_category_text_consistency,
    check_no_emoji_anywhere,
    check_no_out_of_scope_topics_in_generated_output,
    check_no_third_party_name_leak_in_customer_facing_notices,
    check_subscription_notice_consistency,
    check_workshop_invite_notice_no_code,
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


class NoEmojiAnywhereTest(unittest.TestCase):
    def test_emoji_in_order_summary_body_is_flagged(self):
        instance = {"order_summary": {"body": "区分:新規制作 🐴 鞍の型:ブリティッシュ"}}
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("order_summary.body", errors[0])

    def test_emoji_in_care_notice_is_flagged(self):
        instance = {"care_notice": "定期的にオイルで保湿してください✨"}
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("care_notice", errors[0])

    def test_emoji_in_checkout_notice_body_is_flagged(self):
        instance = {
            "checkout_notice": {"body": "お申し込みのご案内をお送りしますね🎉", "kind": "checkout_intent"}
        }
        errors = check_no_emoji_anywhere(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("checkout_notice.body", errors[0])

    def test_no_emoji_is_not_flagged(self):
        instance = {
            "order_summary": {"body": "区分:新規制作/鞍の型:ブリティッシュ"},
            "care_notice": "定期的にオイル・クリームで革に保湿を与えてください。",
        }
        self.assertEqual(check_no_emoji_anywhere(instance), [])

    def test_absent_fields_are_skipped(self):
        instance = {"order_summary": None, "care_notice": None}
        self.assertEqual(check_no_emoji_anywhere(instance), [])


class OutOfScopeTopicsTest(unittest.TestCase):
    def test_payment_keyword_in_delivery_notice_is_flagged(self):
        instance = {
            "status": "generated",
            "delivery_notice": {"body": "決済が完了しましたらお渡しします。"},
        }
        errors = check_no_out_of_scope_topics_in_generated_output(instance)
        self.assertEqual(len(errors), 1)

    def test_non_generated_status_is_skipped(self):
        instance = {
            "status": "out_of_scope",
            "delivery_notice": {"body": "決済が完了しましたらお渡しします。"},
        }
        self.assertEqual(check_no_out_of_scope_topics_in_generated_output(instance), [])

    def test_clean_text_is_not_flagged(self):
        instance = {
            "status": "generated",
            "order_summary": {"body": "区分:新規制作/鞍の型:ブリティッシュ"},
        }
        self.assertEqual(check_no_out_of_scope_topics_in_generated_output(instance), [])


class DeliveryNoticeCategoryTextConsistencyTest(unittest.TestCase):
    def test_repair_without_repair_word_is_flagged(self):
        instance = {"delivery_notice": {"category": "repair", "body": "新しい鞍をお届けします。"}}
        errors = check_delivery_notice_category_text_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_new_with_repair_word_is_flagged(self):
        instance = {"delivery_notice": {"category": "new", "body": "修理箇所の補修が完了しました。"}}
        errors = check_delivery_notice_category_text_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_repair_with_repair_word_is_not_flagged(self):
        instance = {"delivery_notice": {"category": "repair", "body": "修理箇所の補修が完了しました。"}}
        self.assertEqual(check_delivery_notice_category_text_consistency(instance), [])

    def test_no_delivery_notice_is_skipped(self):
        self.assertEqual(check_delivery_notice_category_text_consistency({"delivery_notice": None}), [])


class SubscriptionNoticeConsistencyTest(unittest.TestCase):
    def test_unclear_with_portal_mention_is_flagged(self):
        instance = {
            "subscription_procedure_notice": {
                "kind": "cancellation_unclear",
                "body": "解約でしたら下記リンクからお手続きください。",
                "includes_portal_link": False,
            }
        }
        errors = check_subscription_notice_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_unclear_with_completion_wording_is_flagged(self):
        instance = {
            "subscription_procedure_notice": {
                "kind": "cancellation_unclear",
                "body": "解約手続き完了です。",
                "includes_portal_link": False,
            }
        }
        errors = check_subscription_notice_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_intent_true_without_link_mention_is_flagged(self):
        instance = {
            "subscription_procedure_notice": {
                "kind": "cancellation_intent",
                "body": "解約を承りました。",
                "includes_portal_link": True,
            }
        }
        errors = check_subscription_notice_consistency(instance)
        self.assertEqual(len(errors), 1)

    def test_no_notice_is_skipped(self):
        self.assertEqual(check_subscription_notice_consistency({"subscription_procedure_notice": None}), [])


class CheckoutNoticeNoUrlTest(unittest.TestCase):
    def test_includes_checkout_url_true_is_flagged(self):
        instance = {"checkout_notice": {"body": "承知しました。", "includes_checkout_url": True}}
        errors = check_checkout_notice_no_url(instance)
        self.assertEqual(len(errors), 1)

    def test_url_in_body_is_flagged(self):
        instance = {
            "checkout_notice": {
                "body": "こちらから申し込みできます https://example.com/checkout",
                "includes_checkout_url": False,
            }
        }
        errors = check_checkout_notice_no_url(instance)
        self.assertEqual(len(errors), 1)

    def test_clean_notice_is_not_flagged(self):
        instance = {"checkout_notice": {"body": "お申し込みのご案内をお送りしますね。", "includes_checkout_url": False}}
        self.assertEqual(check_checkout_notice_no_url(instance), [])


class WorkshopInviteNoticeNoCodeTest(unittest.TestCase):
    def test_includes_invite_code_true_is_flagged(self):
        instance = {"workshop_invite_notice": {"body": "承知しました。", "includes_invite_code": True}}
        errors = check_workshop_invite_notice_no_code(instance)
        self.assertEqual(len(errors), 1)

    def test_code_lookalike_in_body_is_flagged(self):
        instance = {
            "workshop_invite_notice": {
                "body": "招待コードはABC234です。",
                "includes_invite_code": False,
            }
        }
        errors = check_workshop_invite_notice_no_code(instance)
        self.assertEqual(len(errors), 1)

    def test_url_in_body_is_flagged(self):
        instance = {
            "workshop_invite_notice": {
                "body": "招待はこちらから bit.ly/abc123",
                "includes_invite_code": False,
            }
        }
        errors = check_workshop_invite_notice_no_code(instance)
        self.assertEqual(len(errors), 1)

    def test_clean_notice_is_not_flagged(self):
        instance = {
            "workshop_invite_notice": {
                "body": "招待コードを発行しますね。少々お待ちください。",
                "includes_invite_code": False,
            }
        }
        self.assertEqual(check_workshop_invite_notice_no_code(instance), [])


class ThirdPartyNameLeakTest(unittest.TestCase):
    def test_name_leak_in_delivery_notice_is_flagged(self):
        instance = {
            "order_summary": {"third_party_names": ["田中花子"]},
            "delivery_notice": {"body": "田中花子様の鞍と合わせてお使いください。"},
            "care_notice": "定期的にオイルで保湿してください。",
        }
        errors = check_no_third_party_name_leak_in_customer_facing_notices(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("delivery_notice.body", errors[0])

    def test_name_leak_in_care_notice_is_flagged(self):
        instance = {
            "order_summary": {"third_party_names": ["田中花子"]},
            "delivery_notice": {"body": "納品案内です。"},
            "care_notice": "田中花子様の分と同じお手入れをしてください。",
        }
        errors = check_no_third_party_name_leak_in_customer_facing_notices(instance)
        self.assertEqual(len(errors), 1)
        self.assertIn("care_notice", errors[0])

    def test_generalized_wording_is_not_flagged(self):
        instance = {
            "order_summary": {"third_party_names": ["田中花子"]},
            "delivery_notice": {"body": "所有者様の鞍と合わせてお使いください。"},
            "care_notice": "定期的にオイルで保湿してください。",
        }
        self.assertEqual(check_no_third_party_name_leak_in_customer_facing_notices(instance), [])

    def test_empty_names_list_is_not_flagged(self):
        instance = {
            "order_summary": {"third_party_names": []},
            "delivery_notice": {"body": "納品案内です。"},
            "care_notice": "お手入れ案内です。",
        }
        self.assertEqual(check_no_third_party_name_leak_in_customer_facing_notices(instance), [])

    def test_missing_field_is_treated_as_empty(self):
        instance = {
            "order_summary": {},
            "delivery_notice": {"body": "納品案内です。"},
            "care_notice": "お手入れ案内です。",
        }
        self.assertEqual(check_no_third_party_name_leak_in_customer_facing_notices(instance), [])

    def test_no_order_summary_is_skipped(self):
        instance = {"order_summary": None, "delivery_notice": {"body": "田中花子様"}}
        self.assertEqual(check_no_third_party_name_leak_in_customer_facing_notices(instance), [])


if __name__ == "__main__":
    unittest.main()
