#!/usr/bin/env python3
"""application_form_submission_flow.pyの単体テスト。
application-form-submission-flow-design.mdの正規化ルール・書き込みフローの
仕様に沿った挙動を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from application_form_submission_flow import (  # noqa: E402
    FormSubmissionResult,
    InMemoryUserProfileStore,
    handle_form_submission,
    normalize_gym_area_pairs_raw,
)


class NormalizeGymAreaPairsRawTest(unittest.TestCase):
    def test_strips_surrounding_whitespace(self):
        self.assertEqual(
            normalize_gym_area_pairs_raw("  クライミングジムA/○○区  "),
            "クライミングジムA/○○区",
        )

    def test_strips_whitespace_around_each_comma_separated_element(self):
        self.assertEqual(
            normalize_gym_area_pairs_raw(
                "クライミングジムA/○○区 ,  ボルダリングジムB/△△市"
            ),
            "クライミングジムA/○○区, ボルダリングジムB/△△市",
        )

    def test_none_becomes_empty_string(self):
        self.assertEqual(normalize_gym_area_pairs_raw(None), "")

    def test_blank_string_becomes_empty_string(self):
        self.assertEqual(normalize_gym_area_pairs_raw("   "), "")

    def test_commas_only_become_empty_string(self):
        self.assertEqual(normalize_gym_area_pairs_raw(",,,"), "")

    def test_mixed_empty_and_valid_elements_drops_empty_ones(self):
        self.assertEqual(
            normalize_gym_area_pairs_raw("クライミングジムA/○○区,, ,"),
            "クライミングジムA/○○区",
        )


class InMemoryUserProfileStoreTest(unittest.TestCase):
    def test_unregistered_user_returns_empty_string_and_not_configured(self):
        store = InMemoryUserProfileStore()
        self.assertEqual(store.get_gym_area_pairs("U_unknown"), "")
        self.assertFalse(store.is_configured("U_unknown"))

    def test_set_then_get_round_trips(self):
        store = InMemoryUserProfileStore()
        store.set_gym_area_pairs("U1", "クライミングジムA/○○区")
        self.assertEqual(store.get_gym_area_pairs("U1"), "クライミングジムA/○○区")
        self.assertTrue(store.is_configured("U1"))

    def test_set_empty_string_makes_not_configured(self):
        store = InMemoryUserProfileStore()
        store.set_gym_area_pairs("U1", "クライミングジムA/○○区")
        store.set_gym_area_pairs("U1", "")
        self.assertEqual(store.get_gym_area_pairs("U1"), "")
        self.assertFalse(store.is_configured("U1"))

    def test_resubmission_overwrites_rather_than_appends(self):
        # design 3節: 複数回の申込フォーム再提出は全体を上書きする(追記ではない)。
        store = InMemoryUserProfileStore()
        store.set_gym_area_pairs("U1", "クライミングジムA/○○区")
        store.set_gym_area_pairs("U1", "ボルダリングジムB/△△市")
        self.assertEqual(store.get_gym_area_pairs("U1"), "ボルダリングジムB/△△市")

    def test_unlinked_stripe_customer_id_returns_none(self):
        # stripe-customer-id-linking-design.md 2節。
        store = InMemoryUserProfileStore()
        self.assertIsNone(store.get_user_id_by_stripe_customer_id("cus_unknown"))

    def test_set_stripe_customer_id_enables_reverse_lookup(self):
        store = InMemoryUserProfileStore()
        store.set_stripe_customer_id("U1", "cus_A")
        self.assertEqual(store.get_user_id_by_stripe_customer_id("cus_A"), "U1")

    def test_unregistered_user_email_returns_none(self):
        store = InMemoryUserProfileStore()
        self.assertIsNone(store.get_email("U_unknown"))

    def test_email_set_then_get_round_trips(self):
        store = InMemoryUserProfileStore()
        store.set_email("U1", "owner@example.com")
        self.assertEqual(store.get_email("U1"), "owner@example.com")

    def test_email_resubmission_overwrites(self):
        store = InMemoryUserProfileStore()
        store.set_email("U1", "old@example.com")
        store.set_email("U1", "new@example.com")
        self.assertEqual(store.get_email("U1"), "new@example.com")

    def test_relinking_same_user_to_new_customer_id_updates_forward_lookup(self):
        # Checkoutのやり直し等で同一user_idに新しいstripe_customer_idが割り当たった場合、
        # 新しい方からの逆引きが有効になる(古いcustomer_idの逆引きエントリの明示的な
        # 削除は行わない。実害はない旨はstripe-customer-id-linking-design.md参照)。
        store = InMemoryUserProfileStore()
        store.set_stripe_customer_id("U1", "cus_old")
        store.set_stripe_customer_id("U1", "cus_new")
        self.assertEqual(store.get_user_id_by_stripe_customer_id("cus_new"), "U1")

    def test_unrecorded_user_is_following_defaults_true(self):
        # blocked-but-billing-detection-design.md: 未記録のuser_idは安全側でTrue扱い。
        store = InMemoryUserProfileStore()
        self.assertTrue(store.get_is_following("U_unknown"))

    def test_set_is_following_false_then_true_round_trips(self):
        store = InMemoryUserProfileStore()
        store.set_is_following("U1", False)
        self.assertFalse(store.get_is_following("U1"))
        store.set_is_following("U1", True)
        self.assertTrue(store.get_is_following("U1"))

    def test_all_user_ids_collects_across_all_fields(self):
        store = InMemoryUserProfileStore()
        store.set_gym_area_pairs("U1", "クライミングジムA/○○区")
        store.set_email("U2", "owner@example.com")
        store.set_stripe_customer_id("U3", "cus_A")
        store.set_is_following("U4", False)
        self.assertEqual(list(store.all_user_ids()), ["U1", "U2", "U3", "U4"])

    def test_all_user_ids_empty_store_returns_empty(self):
        store = InMemoryUserProfileStore()
        self.assertEqual(list(store.all_user_ids()), [])


class HandleFormSubmissionTest(unittest.TestCase):
    def test_valid_payload_writes_normalized_value_and_returns_ok(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {
                "user_id": "U1234567890abcdef",
                "gym_area_pairs_raw": " クライミングジムA/○○区 ,ボルダリングジムB/△△市 ",
                "email": " owner@example.com ",
            },
            store,
        )
        self.assertEqual(
            result,
            FormSubmissionResult(
                ok=True,
                user_id="U1234567890abcdef",
                normalized_gym_area_pairs="クライミングジムA/○○区, ボルダリングジムB/△△市",
                email="owner@example.com",
            ),
        )
        self.assertEqual(
            store.get_gym_area_pairs("U1234567890abcdef"),
            "クライミングジムA/○○区, ボルダリングジムB/△△市",
        )
        self.assertTrue(store.is_configured("U1234567890abcdef"))
        self.assertEqual(store.get_email("U1234567890abcdef"), "owner@example.com")

    def test_missing_gym_area_pairs_raw_defaults_to_empty_and_stays_unconfigured(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {"user_id": "U1", "email": "owner@example.com"}, store
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.normalized_gym_area_pairs, "")
        self.assertFalse(store.is_configured("U1"))

    def test_missing_user_id_is_rejected_without_writing(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {
                "gym_area_pairs_raw": "クライミングジムA/○○区",
                "email": "owner@example.com",
            },
            store,
        )
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertFalse(store.is_configured("U_anything"))

    def test_blank_user_id_is_rejected(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {
                "user_id": "   ",
                "gym_area_pairs_raw": "クライミングジムA/○○区",
                "email": "owner@example.com",
            },
            store,
        )
        self.assertFalse(result.ok)

    def test_non_string_gym_area_pairs_raw_is_rejected_without_writing(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {"user_id": "U1", "gym_area_pairs_raw": 12345, "email": "owner@example.com"},
            store,
        )
        self.assertFalse(result.ok)
        self.assertFalse(store.is_configured("U1"))

    def test_missing_email_is_rejected_without_writing(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {"user_id": "U1", "gym_area_pairs_raw": "クライミングジムA/○○区"}, store
        )
        self.assertFalse(result.ok)
        self.assertIsNotNone(result.error)
        self.assertFalse(store.is_configured("U1"))
        self.assertIsNone(store.get_email("U1"))

    def test_blank_email_is_rejected(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {"user_id": "U1", "gym_area_pairs_raw": "クライミングジムA/○○区", "email": "   "},
            store,
        )
        self.assertFalse(result.ok)
        self.assertIsNone(store.get_email("U1"))

    def test_non_string_email_is_rejected_without_writing(self):
        store = InMemoryUserProfileStore()
        result = handle_form_submission(
            {"user_id": "U1", "gym_area_pairs_raw": "クライミングジムA/○○区", "email": 12345},
            store,
        )
        self.assertFalse(result.ok)
        self.assertIsNone(store.get_email("U1"))

    def test_resubmission_via_handler_overwrites(self):
        store = InMemoryUserProfileStore()
        handle_form_submission(
            {
                "user_id": "U1",
                "gym_area_pairs_raw": "クライミングジムA/○○区",
                "email": "old@example.com",
            },
            store,
        )
        handle_form_submission(
            {"user_id": "U1", "gym_area_pairs_raw": "", "email": "new@example.com"},
            store,
        )
        self.assertEqual(store.get_gym_area_pairs("U1"), "")
        self.assertFalse(store.is_configured("U1"))
        self.assertEqual(store.get_email("U1"), "new@example.com")


if __name__ == "__main__":
    unittest.main()
