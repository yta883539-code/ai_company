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


if __name__ == "__main__":
    unittest.main()
