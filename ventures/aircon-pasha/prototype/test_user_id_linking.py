#!/usr/bin/env python3
"""user_id_linking.pyの単体テスト。
user-account-linking-design.mdの連携コード発行・解決ロジックの仕様に沿った挙動を確認する。"""

import random
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from user_id_linking import (  # noqa: E402
    InMemoryLinkingCodeStore,
    InMemoryUserProfileStore,
    LinkingResolution,
    PendingLink,
    UserProfile,
    _CODE_ALPHABET,
    issue_linking_code_on_form_submission,
    purge_expired_links,
    resolve_linking_code,
)

_NOW = datetime(2026, 8, 23, 12, 0, 0)


class IssueLinkingCodeOnFormSubmissionTest(unittest.TestCase):
    def test_issues_a_six_character_code_from_the_restricted_alphabet(self):
        store = InMemoryLinkingCodeStore()
        code = issue_linking_code_on_form_submission(
            "form-1", "テストクリーニング", "独立系", "owner@example.com",
            store, _NOW, random.Random(1),
        )
        self.assertEqual(len(code), 6)
        for ambiguous_char in "0O1IL":
            self.assertNotIn(ambiguous_char, code)

    def test_saves_the_issued_code_with_form_fields_and_issued_at(self):
        store = InMemoryLinkingCodeStore()
        code = issue_linking_code_on_form_submission(
            "form-2", "テストクリーニング", "独立系", "owner@example.com",
            store, _NOW, random.Random(2),
        )
        entry = store.get(code)
        self.assertEqual(entry.form_submission_id, "form-2")
        self.assertEqual(entry.business_name, "テストクリーニング")
        self.assertEqual(entry.business_type, "独立系")
        self.assertEqual(entry.email, "owner@example.com")
        self.assertEqual(entry.issued_at, _NOW)

    def test_regenerates_on_collision_with_an_existing_code(self):
        store = InMemoryLinkingCodeStore()

        class _FixedThenVaryingRng:
            """最初の1回は既存コードと同じ値を返し、以降は別の値を返すダミーrng。"""

            def __init__(self, first, rest):
                self._first = first
                self._rest = rest
                self._char_index = 0

            def choice(self, seq):
                if self._char_index < len(self._first):
                    value = self._first[self._char_index]
                else:
                    value = self._rest[self._char_index - len(self._first)]
                self._char_index += 1
                return value

        existing_code = "AB2345"
        store.save(
            existing_code,
            PendingLink(
                form_submission_id="form-0", business_name="他社", business_type="独立系",
                email="other@example.com", issued_at=_NOW,
            ),
        )
        rng = _FixedThenVaryingRng(existing_code, "CD6789")

        code = issue_linking_code_on_form_submission(
            "form-3", "テストクリーニング", "独立系", "owner@example.com", store, _NOW, rng,
        )

        self.assertEqual(code, "CD6789")
        self.assertEqual(store.get(existing_code).form_submission_id, "form-0")

    def test_raises_when_collisions_exceed_the_retry_budget(self):
        store = InMemoryLinkingCodeStore()

        class _AlwaysSameRng:
            def choice(self, seq):
                return "A"

        store.save(
            "AAAAAA",
            PendingLink(
                form_submission_id="form-0", business_name="他社", business_type="独立系",
                email="other@example.com", issued_at=_NOW,
            ),
        )
        with self.assertRaises(RuntimeError):
            issue_linking_code_on_form_submission(
                "form-4", "テストクリーニング", "独立系", "owner@example.com",
                store, _NOW, _AlwaysSameRng(),
            )


class ResolveLinkingCodeTest(unittest.TestCase):
    def _issue(self, store, code="AB12CD", issued_at=_NOW):
        store.save(
            code,
            PendingLink(
                form_submission_id="form-1", business_name="テストクリーニング",
                business_type="独立系", email="owner@example.com", issued_at=issued_at,
            ),
        )

    def test_resolves_a_matching_code_and_creates_the_user_profile(self):
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()
        self._issue(linking_store, code="AB12CD")

        result = resolve_linking_code(
            "AB12CD", "u-1", linking_store, profile_store, _NOW + timedelta(minutes=5)
        )

        self.assertEqual(result, LinkingResolution(ok=True))
        profile = profile_store.get("u-1")
        self.assertEqual(profile.business_name, "テストクリーニング")
        self.assertEqual(profile.business_type, "独立系")
        self.assertEqual(profile.email, "owner@example.com")
        self.assertIsNone(profile.stripe_customer_id)
        self.assertIsNone(profile.current_plan_id)

    def test_is_case_insensitive_and_trims_whitespace(self):
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()
        self._issue(linking_store, code="AB12CD")

        result = resolve_linking_code(
            " ab12cd \n", "u-1", linking_store, profile_store, _NOW
        )

        self.assertTrue(result.ok)

    def test_code_is_single_use(self):
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()
        self._issue(linking_store, code="AB12CD")
        resolve_linking_code("AB12CD", "u-1", linking_store, profile_store, _NOW)

        second_result = resolve_linking_code(
            "AB12CD", "u-2", linking_store, profile_store, _NOW
        )

        self.assertFalse(second_result.ok)
        self.assertFalse(profile_store.exists("u-2"))

    def test_expired_code_is_rejected_and_purged(self):
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()
        self._issue(linking_store, code="AB12CD", issued_at=_NOW)

        result = resolve_linking_code(
            "AB12CD", "u-1", linking_store, profile_store, _NOW + timedelta(hours=24, minutes=1)
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "linking_code expired")
        self.assertIsNone(linking_store.get("AB12CD"))
        self.assertFalse(profile_store.exists("u-1"))

    def test_unknown_code_is_rejected(self):
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()

        result = resolve_linking_code(
            "ZZ9999", "u-1", linking_store, profile_store, _NOW
        )

        self.assertFalse(result.ok)

    def test_ordinary_memo_text_is_not_mistaken_for_a_code(self):
        """design 3節: 形式一致のみでは連携コードと判定しない(辞書引き一致を必須とする)。"""
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()

        result = resolve_linking_code(
            "壁掛け型2.2kW分解洗浄実施", "u-1", linking_store, profile_store, _NOW
        )

        self.assertFalse(result.ok)

    def test_code_alphabet_excludes_digits_common_in_equipment_specs(self):
        """user-account-linking-design.md「未検証・残課題」(境界値確認)への対応。

        施工メモの号数・電圧表記(例:「壁掛け2.2kW」「100V」)には`0`・`1`が高頻度で
        登場するが、コード生成用アルファベット(_CODE_ALPHABET)は視認性除外ルールにより
        `0`・`1`・`O`・`I`・`L`を含まない。したがって、これらの文字を含むメモの書き出し
        文言は、正規化(strip+upper)後も実際に発行されたコードとは原理的に一致しえない
        ことをここで確定する(「偶然一致する可能性はごく低い」という設計コメントの根拠を
        実コードで裏付ける)。
        """
        for excluded_char in "01OIL":
            self.assertNotIn(excluded_char, _CODE_ALPHABET)
        self.assertEqual(len(_CODE_ALPHABET), 31)  # 26+10-5

    def test_realistic_memo_openings_are_rejected_even_when_a_pending_code_exists(self):
        """辞書引き一致の境界値確認: 実際にコードが1件発行されている状態でも、施工メモに
        典型的に現れる書き出し文言(号数・電圧・数量表記)はいずれも連携コードと誤認されない
        ことを確認する(design 3節の「辞書引き一致を必須とする」方針の実効性確認)。"""
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()
        self._issue(linking_store, code="AB23CD")

        realistic_memo_openings = [
            "壁掛型2.2",  # 号数表記
            "100V電源",  # 電圧表記(0/1を含む)
            "2台目",  # 数量表記
            "室外機",
            "AB23CE",  # 実在コードに酷似するが1文字違う(誤入力に近い境界値)
        ]
        for text in realistic_memo_openings:
            with self.subTest(text=text):
                result = resolve_linking_code(text, "u-1", linking_store, profile_store, _NOW)
                self.assertFalse(result.ok)
        # 誤判定を試みても本来のコードは消費されずに残っている(取り違えで使い潰されない)。
        self.assertIsNotNone(linking_store.get("AB23CD"))


class PurgeExpiredLinksTest(unittest.TestCase):
    def test_removes_only_expired_entries(self):
        store = InMemoryLinkingCodeStore()
        store.save(
            "FRESH1",
            PendingLink(
                form_submission_id="form-1", business_name="A", business_type="独立系",
                email="a@example.com", issued_at=_NOW,
            ),
        )
        store.save(
            "OLD0001"[:6],
            PendingLink(
                form_submission_id="form-2", business_name="B", business_type="独立系",
                email="b@example.com", issued_at=_NOW - timedelta(hours=25),
            ),
        )

        removed = purge_expired_links(store, _NOW)

        self.assertEqual(removed, 1)
        self.assertIsNotNone(store.get("FRESH1"))
        self.assertIsNone(store.get("OLD000"))


class InMemoryUserProfileStoreStripeCustomerIdTest(unittest.TestCase):
    """checkout-session-completed-handling-design.md 1節で追加した
    set_stripe_customer_id()/get_user_id_by_stripe_customer_id()の単体テスト。"""

    def _seed_profile(self, store, user_id="u-1"):
        store.save(
            user_id,
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=_NOW,
            ),
        )

    def test_sets_forward_field_and_reverse_lookup(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        store.set_stripe_customer_id("u-1", "cus_1")

        self.assertEqual(store.get("u-1").stripe_customer_id, "cus_1")
        self.assertEqual(store.get_user_id_by_stripe_customer_id("cus_1"), "u-1")

    def test_unknown_user_id_is_a_noop(self):
        store = InMemoryUserProfileStore()

        store.set_stripe_customer_id("no-such-user", "cus_1")

        self.assertIsNone(store.get_user_id_by_stripe_customer_id("cus_1"))

    def test_unknown_stripe_customer_id_returns_none(self):
        store = InMemoryUserProfileStore()

        self.assertIsNone(store.get_user_id_by_stripe_customer_id("cus_unknown"))

    def test_reassigning_stripe_customer_id_drops_old_reverse_entry(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")
        store.set_stripe_customer_id("u-1", "cus_old")

        store.set_stripe_customer_id("u-1", "cus_new")

        self.assertIsNone(store.get_user_id_by_stripe_customer_id("cus_old"))
        self.assertEqual(store.get_user_id_by_stripe_customer_id("cus_new"), "u-1")


class InMemoryUserProfileStoreTrialFieldsTest(unittest.TestCase):
    """trial-end-scheduler-design.md(フェーズ133)向けにフェーズ134で追加した
    trial_start_at/trial_end_notified_at/upgraded_atの単体テスト。"""

    def _seed_profile(self, store, user_id="u-1"):
        store.save(
            user_id,
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=_NOW,
            ),
        )

    def test_new_fields_default_to_none(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        profile = store.get("u-1")

        self.assertIsNone(profile.trial_start_at)
        self.assertIsNone(profile.trial_end_notified_at)
        self.assertIsNone(profile.upgraded_at)

    def test_set_trial_start_at(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        store.set_trial_start_at("u-1", _NOW)

        self.assertEqual(store.get("u-1").trial_start_at, _NOW)

    def test_set_trial_end_notified_at(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        store.set_trial_end_notified_at("u-1", _NOW)

        self.assertEqual(store.get("u-1").trial_end_notified_at, _NOW)

    def test_set_upgraded_at(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        store.set_upgraded_at("u-1", _NOW)

        self.assertEqual(store.get("u-1").upgraded_at, _NOW)

    def test_setters_are_a_noop_for_unknown_user_id(self):
        store = InMemoryUserProfileStore()

        store.set_trial_start_at("no-such-user", _NOW)
        store.set_trial_end_notified_at("no-such-user", _NOW)
        store.set_upgraded_at("no-such-user", _NOW)

        self.assertIsNone(store.get("no-such-user"))


class InMemoryUserProfileStorePaymentFailureReminderFieldTest(unittest.TestCase):
    """payment-failure-reminder-scheduler-design.md(フェーズ143)向けに追加した
    payment_failure_reminder_sent_atの単体テスト。"""

    def _seed_profile(self, store, user_id="u-1"):
        store.save(
            user_id,
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=_NOW,
            ),
        )

    def test_defaults_to_none(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        self.assertIsNone(store.get_payment_failure_reminder_sent_at("u-1"))

    def test_set_and_get(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        store.set_payment_failure_reminder_sent_at("u-1", _NOW)

        self.assertEqual(store.get_payment_failure_reminder_sent_at("u-1"), _NOW)
        self.assertEqual(store.get("u-1").payment_failure_reminder_sent_at, _NOW)

    def test_set_none_clears_the_field(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")
        store.set_payment_failure_reminder_sent_at("u-1", _NOW)

        store.set_payment_failure_reminder_sent_at("u-1", None)

        self.assertIsNone(store.get_payment_failure_reminder_sent_at("u-1"))

    def test_setter_is_a_noop_for_unknown_user_id(self):
        store = InMemoryUserProfileStore()

        store.set_payment_failure_reminder_sent_at("no-such-user", _NOW)

        self.assertIsNone(store.get_payment_failure_reminder_sent_at("no-such-user"))


class InMemoryUserProfileStoreCurrentPlanIdFieldTest(unittest.TestCase):
    """user-account-linking-design.md 4節向けに追加した`current_plan_id`の単体テスト
    (フェーズ161、subscription_plan_sync.pyの`CurrentPlanStoreProtocol`を本クラスが
    構造的に満たすためのメソッド)。"""

    def _seed_profile(self, store, user_id="u-1"):
        store.save(
            user_id,
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=_NOW,
            ),
        )

    def test_defaults_to_none(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        self.assertIsNone(store.get_current_plan_id("u-1"))

    def test_set_and_get(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")

        store.set_current_plan_id("u-1", "スタンダード")

        self.assertEqual(store.get_current_plan_id("u-1"), "スタンダード")
        self.assertEqual(store.get("u-1").current_plan_id, "スタンダード")

    def test_set_none_clears_the_field(self):
        store = InMemoryUserProfileStore()
        self._seed_profile(store, "u-1")
        store.set_current_plan_id("u-1", "スモール")

        store.set_current_plan_id("u-1", None)

        self.assertIsNone(store.get_current_plan_id("u-1"))

    def test_setter_is_a_noop_for_unknown_user_id(self):
        store = InMemoryUserProfileStore()

        store.set_current_plan_id("no-such-user", "スモール")

        self.assertIsNone(store.get_current_plan_id("no-such-user"))


if __name__ == "__main__":
    unittest.main()
