#!/usr/bin/env python3
"""workshop_linking.pyの単体テスト。
craftsman-account-linking-design.md(フェーズ25、フェーズ66追記)2〜3節の連携コード発行・
解決・workshop新規作成ロジックの仕様に沿った挙動を確認する。"""

import random
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from usage_counter_workshop import (  # noqa: E402
    InMemoryUserProfileStore,
    InMemoryWorkshopStore,
)
from workshop_linking import (  # noqa: E402
    PROVISIONAL_PLAN_ID_ON_CREATION,
    InMemoryLinkingCodeStore,
    LinkingCodePurgeThrottle,
    LinkingResolution,
    add_member_from_invite_code,
    create_workshop_from_linking_code,
    delete_pending_links_for_user,
    issue_invite_code_for_workshop,
    issue_linking_code_on_follow,
    purge_expired_links,
    resolve_invite_code,
    resolve_linking_code,
)

_NOW = datetime(2026, 9, 9, 12, 0, 0)


class IssueLinkingCodeOnFollowTest(unittest.TestCase):
    def test_issues_a_six_character_code_from_the_restricted_alphabet(self):
        store = InMemoryLinkingCodeStore()
        code = issue_linking_code_on_follow("U1234", store, _NOW, random.Random(1))
        self.assertEqual(len(code), 6)
        for ambiguous_char in "0O1IL":
            self.assertNotIn(ambiguous_char, code)

    def test_saves_the_issued_code_with_user_id_and_issued_at(self):
        store = InMemoryLinkingCodeStore()
        code = issue_linking_code_on_follow("U1234", store, _NOW, random.Random(2))
        self.assertEqual(store.get(code), ("U1234", _NOW))

    def test_regenerates_on_collision_with_an_existing_code(self):
        store = InMemoryLinkingCodeStore()

        class _FixedThenVaryingRng:
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

        store.save("AAAAAA", "U_other", _NOW)
        rng = _FixedThenVaryingRng(first="AAAAAA", rest="BBBBBB")
        code = issue_linking_code_on_follow("U9999", store, _NOW, rng)
        self.assertEqual(code, "BBBBBB")
        self.assertEqual(store.get("BBBBBB"), ("U9999", _NOW))
        self.assertEqual(store.get("AAAAAA"), ("U_other", _NOW))


class ResolveLinkingCodeTest(unittest.TestCase):
    def test_resolves_a_valid_unexpired_code(self):
        store = InMemoryLinkingCodeStore()
        store.save("ABC234", "U1234", _NOW)
        result = resolve_linking_code("ABC234", store, _NOW + timedelta(hours=1))
        self.assertEqual(result, LinkingResolution(ok=True, user_id="U1234"))

    def test_is_case_and_whitespace_insensitive(self):
        store = InMemoryLinkingCodeStore()
        store.save("ABC234", "U1234", _NOW)
        result = resolve_linking_code("  abc234  ", store, _NOW)
        self.assertTrue(result.ok)
        self.assertEqual(result.user_id, "U1234")

    def test_rejects_unknown_code(self):
        store = InMemoryLinkingCodeStore()
        result = resolve_linking_code("ZZZ999", store, _NOW)
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error)

    def test_rejects_missing_or_blank_code(self):
        store = InMemoryLinkingCodeStore()
        for bad_code in (None, "", "   "):
            result = resolve_linking_code(bad_code, store, _NOW)
            self.assertFalse(result.ok)

    def test_rejects_and_purges_expired_code(self):
        store = InMemoryLinkingCodeStore()
        store.save("ABC234", "U1234", _NOW)
        expired_check_time = _NOW + timedelta(hours=24, minutes=1)
        result = resolve_linking_code("ABC234", store, expired_check_time)
        self.assertFalse(result.ok)
        self.assertIn("expired", result.error)
        self.assertIsNone(store.get("ABC234"))

    def test_code_is_one_time_use(self):
        store = InMemoryLinkingCodeStore()
        store.save("ABC234", "U1234", _NOW)
        first = resolve_linking_code("ABC234", store, _NOW)
        second = resolve_linking_code("ABC234", store, _NOW)
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)


class CreateWorkshopFromLinkingCodeTest(unittest.TestCase):
    """craftsman-account-linking-design.md 2〜3節・7節(フェーズ66追記)。"""

    def _make_stores(self):
        return InMemoryLinkingCodeStore(), InMemoryUserProfileStore(), InMemoryWorkshopStore()

    def test_creates_a_single_member_workshop_for_the_resolved_user(self):
        linking_store, profile_store, workshop_store = self._make_stores()
        linking_store.save("ABC234", "U1234", _NOW)

        result = create_workshop_from_linking_code(
            "ABC234",
            linking_store,
            profile_store,
            workshop_store,
            _NOW,
            workshop_id_factory=lambda: "W-fixed",
        )

        self.assertTrue(result.ok)
        self.assertFalse(result.already_linked)
        self.assertEqual(result.workshop_id, "W-fixed")
        self.assertEqual(workshop_store.get_contractor_user_id("W-fixed"), "U1234")
        self.assertEqual(workshop_store.get_member_user_ids("W-fixed"), ["U1234"])
        self.assertEqual(profile_store.get_workshop_id("U1234"), "W-fixed")

    def test_sets_provisional_plan_trial_start_and_trialing_status(self):
        linking_store, profile_store, workshop_store = self._make_stores()
        linking_store.save("ABC234", "U1234", _NOW)

        result = create_workshop_from_linking_code(
            "ABC234", linking_store, profile_store, workshop_store, _NOW
        )

        self.assertEqual(
            workshop_store.get_plan_id(result.workshop_id), PROVISIONAL_PLAN_ID_ON_CREATION
        )
        self.assertEqual(workshop_store.get_trial_start_at(result.workshop_id), _NOW)
        self.assertEqual(workshop_store.get_subscription_status(result.workshop_id), "trialing")

    def test_code_is_consumed_and_cannot_be_reused(self):
        linking_store, profile_store, workshop_store = self._make_stores()
        linking_store.save("ABC234", "U1234", _NOW)

        create_workshop_from_linking_code(
            "ABC234", linking_store, profile_store, workshop_store, _NOW
        )
        second = create_workshop_from_linking_code(
            "ABC234", linking_store, profile_store, workshop_store, _NOW
        )

        self.assertFalse(second.ok)

    def test_invalid_code_does_not_create_a_workshop(self):
        linking_store, profile_store, workshop_store = self._make_stores()

        result = create_workshop_from_linking_code(
            "ZZZ999", linking_store, profile_store, workshop_store, _NOW
        )

        self.assertFalse(result.ok)
        self.assertIsNone(result.workshop_id)
        self.assertIsNone(profile_store.get_workshop_id("U1234"))

    def test_resolving_an_already_linked_user_does_not_create_a_second_workshop(self):
        """design未明記だが、二重タップ等で解決処理が再実行された場合の防御的分岐。"""
        linking_store, profile_store, workshop_store = self._make_stores()
        profile_store.link("U1234", "W-existing")
        linking_store.save("ABC234", "U1234", _NOW)

        result = create_workshop_from_linking_code(
            "ABC234", linking_store, profile_store, workshop_store, _NOW
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.already_linked)
        self.assertEqual(result.workshop_id, "W-existing")

    def test_default_workshop_id_factory_produces_unique_ids(self):
        linking_store, profile_store, workshop_store = self._make_stores()
        linking_store.save("CODE01", "U-a", _NOW)
        linking_store.save("CODE02", "U-b", _NOW)

        first = create_workshop_from_linking_code(
            "CODE01", linking_store, profile_store, workshop_store, _NOW
        )
        second = create_workshop_from_linking_code(
            "CODE02", linking_store, profile_store, workshop_store, _NOW
        )

        self.assertNotEqual(first.workshop_id, second.workshop_id)


class IssueInviteCodeForWorkshopTest(unittest.TestCase):
    """craftsman-account-linking-design.md 5節・11.1節(フェーズ97)。"""

    def _make_multi_craftsman_workshop(self, workshop_store, workshop_id="W1", contractor="U-contractor"):
        workshop_store.set_members(workshop_id, contractor_user_id=contractor, member_user_ids=[contractor])
        workshop_store.set_plan(workshop_id, "multi_craftsman")

    def test_issues_code_for_contractor_of_multi_craftsman_workshop(self):
        workshop_store = InMemoryWorkshopStore()
        self._make_multi_craftsman_workshop(workshop_store)
        invite_store = InMemoryLinkingCodeStore()

        result = issue_invite_code_for_workshop(
            "W1", "U-contractor", workshop_store, invite_store, _NOW, random.Random(1)
        )

        self.assertTrue(result.ok)
        self.assertEqual(len(result.code), 6)
        self.assertEqual(invite_store.get(result.code), ("W1", _NOW))

    def test_rejects_non_contractor(self):
        workshop_store = InMemoryWorkshopStore()
        self._make_multi_craftsman_workshop(workshop_store)
        invite_store = InMemoryLinkingCodeStore()

        result = issue_invite_code_for_workshop(
            "W1", "U-other-member", workshop_store, invite_store, _NOW, random.Random(1)
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "not_contractor")
        self.assertIsNone(result.code)

    def test_rejects_non_multi_craftsman_plan(self):
        workshop_store = InMemoryWorkshopStore()
        workshop_store.set_members("W1", contractor_user_id="U-contractor", member_user_ids=["U-contractor"])
        workshop_store.set_plan("W1", "standard")
        invite_store = InMemoryLinkingCodeStore()

        result = issue_invite_code_for_workshop(
            "W1", "U-contractor", workshop_store, invite_store, _NOW, random.Random(1)
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "upgrade_required")

    def test_rejects_issuance_when_member_limit_already_reached(self):
        workshop_store = InMemoryWorkshopStore()
        workshop_store.set_members(
            "W1",
            contractor_user_id="U-contractor",
            member_user_ids=["U-contractor", "M2", "M3", "M4", "M5"],
        )
        workshop_store.set_plan("W1", "multi_craftsman")
        invite_store = InMemoryLinkingCodeStore()

        result = issue_invite_code_for_workshop(
            "W1", "U-contractor", workshop_store, invite_store, _NOW, random.Random(1)
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "member_limit_reached")
        self.assertIsNone(result.code)
        self.assertEqual(list(invite_store.items()), [])

    def test_allows_issuance_one_below_the_member_limit(self):
        workshop_store = InMemoryWorkshopStore()
        workshop_store.set_members(
            "W1",
            contractor_user_id="U-contractor",
            member_user_ids=["U-contractor", "M2", "M3", "M4"],
        )
        workshop_store.set_plan("W1", "multi_craftsman")
        invite_store = InMemoryLinkingCodeStore()

        result = issue_invite_code_for_workshop(
            "W1", "U-contractor", workshop_store, invite_store, _NOW, random.Random(1)
        )

        self.assertTrue(result.ok)


class ResolveInviteCodeTest(unittest.TestCase):
    def test_resolves_a_valid_unexpired_code_to_workshop_id(self):
        store = InMemoryLinkingCodeStore()
        store.save("ABC234", "W1", _NOW)
        result = resolve_invite_code("ABC234", store, _NOW + timedelta(hours=1))
        self.assertTrue(result.ok)
        self.assertEqual(result.workshop_id, "W1")

    def test_rejects_expired_code(self):
        store = InMemoryLinkingCodeStore()
        store.save("ABC234", "W1", _NOW)
        result = resolve_invite_code("ABC234", store, _NOW + timedelta(hours=24, minutes=1))
        self.assertFalse(result.ok)
        self.assertIn("expired", result.error)

    def test_code_is_one_time_use(self):
        store = InMemoryLinkingCodeStore()
        store.save("ABC234", "W1", _NOW)
        first = resolve_invite_code("ABC234", store, _NOW)
        second = resolve_invite_code("ABC234", store, _NOW)
        self.assertTrue(first.ok)
        self.assertFalse(second.ok)


class AddMemberFromInviteCodeTest(unittest.TestCase):
    """craftsman-account-linking-design.md 11.2節(フェーズ97)。"""

    def _make_stores(self):
        return InMemoryLinkingCodeStore(), InMemoryUserProfileStore(), InMemoryWorkshopStore()

    def test_adds_unlinked_user_as_new_member(self):
        invite_store, profile_store, workshop_store = self._make_stores()
        workshop_store.set_members("W1", contractor_user_id="U-contractor", member_user_ids=["U-contractor"])
        invite_store.save("ABC234", "W1", _NOW)

        result = add_member_from_invite_code(
            "ABC234", "U-new", invite_store, profile_store, workshop_store, _NOW
        )

        self.assertTrue(result.ok)
        self.assertFalse(result.already_member)
        self.assertEqual(result.workshop_id, "W1")
        self.assertEqual(workshop_store.get_member_user_ids("W1"), ["U-contractor", "U-new"])
        self.assertEqual(profile_store.get_workshop_id("U-new"), "W1")

    def test_is_idempotent_when_already_a_member_of_the_same_workshop(self):
        invite_store, profile_store, workshop_store = self._make_stores()
        workshop_store.set_members("W1", contractor_user_id="U-contractor", member_user_ids=["U-contractor", "U-new"])
        profile_store.link("U-new", "W1")
        invite_store.save("ABC234", "W1", _NOW)

        result = add_member_from_invite_code(
            "ABC234", "U-new", invite_store, profile_store, workshop_store, _NOW
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.already_member)
        self.assertEqual(workshop_store.get_member_user_ids("W1"), ["U-contractor", "U-new"])

    def test_rejects_user_already_belonging_to_a_different_workshop(self):
        invite_store, profile_store, workshop_store = self._make_stores()
        workshop_store.set_members("W1", contractor_user_id="U-contractor", member_user_ids=["U-contractor"])
        profile_store.link("U-elsewhere", "W-other")
        invite_store.save("ABC234", "W1", _NOW)

        result = add_member_from_invite_code(
            "ABC234", "U-elsewhere", invite_store, profile_store, workshop_store, _NOW
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "already_in_another_workshop")
        self.assertEqual(workshop_store.get_member_user_ids("W1"), ["U-contractor"])
        self.assertEqual(profile_store.get_workshop_id("U-elsewhere"), "W-other")

    def test_invalid_code_adds_no_member(self):
        invite_store, profile_store, workshop_store = self._make_stores()
        workshop_store.set_members("W1", contractor_user_id="U-contractor", member_user_ids=["U-contractor"])

        result = add_member_from_invite_code(
            "ZZZ999", "U-new", invite_store, profile_store, workshop_store, _NOW
        )

        self.assertFalse(result.ok)
        self.assertIsNone(profile_store.get_workshop_id("U-new"))

    def test_rejects_new_member_when_member_limit_already_reached(self):
        """design 11.7節(フェーズ102)の多重防御: 発行時点では上限未満でも、他の招待
        コード経由で先にメンバーが追加され上限に達した後にこちらが使われた場合は
        ここで拒否する(招待コード自体は使い切りのため消費される)。"""
        invite_store, profile_store, workshop_store = self._make_stores()
        workshop_store.set_members(
            "W1",
            contractor_user_id="U-contractor",
            member_user_ids=["U-contractor", "M2", "M3", "M4", "M5"],
        )
        invite_store.save("ABC234", "W1", _NOW)

        result = add_member_from_invite_code(
            "ABC234", "U-new", invite_store, profile_store, workshop_store, _NOW
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "member_limit_reached")
        self.assertEqual(
            workshop_store.get_member_user_ids("W1"),
            ["U-contractor", "M2", "M3", "M4", "M5"],
        )
        self.assertIsNone(profile_store.get_workshop_id("U-new"))


class PurgeExpiredLinksTest(unittest.TestCase):
    def test_removes_only_entries_past_the_ttl(self):
        store = InMemoryLinkingCodeStore()
        store.save("FRESH1", "U-fresh", _NOW)
        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))
        store.save("EDGE01", "U-edge", _NOW - timedelta(hours=24))

        purged = purge_expired_links(store, _NOW)

        self.assertEqual(purged, 1)
        self.assertIsNone(store.get("OLD001"))
        self.assertIsNotNone(store.get("FRESH1"))
        self.assertIsNotNone(store.get("EDGE01"))

    def test_returns_zero_when_nothing_is_expired(self):
        store = InMemoryLinkingCodeStore()
        store.save("FRESH1", "U-fresh", _NOW)

        self.assertEqual(purge_expired_links(store, _NOW), 0)

    def test_purged_code_can_no_longer_be_resolved(self):
        store = InMemoryLinkingCodeStore()
        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))

        purge_expired_links(store, _NOW)
        resolution = resolve_linking_code("OLD001", store, _NOW)

        self.assertFalse(resolution.ok)


class DeletePendingLinksForUserTest(unittest.TestCase):
    def test_deletes_all_codes_for_the_given_user(self):
        store = InMemoryLinkingCodeStore()
        store.save("CODE01", "U-bye", _NOW)
        store.save("CODE02", "U-bye", _NOW)
        store.save("CODE03", "U-stay", _NOW)

        deleted = delete_pending_links_for_user("U-bye", store)

        self.assertEqual(deleted, 2)
        self.assertIsNone(store.get("CODE01"))
        self.assertIsNone(store.get("CODE02"))
        self.assertIsNotNone(store.get("CODE03"))

    def test_returns_zero_when_user_has_no_pending_links(self):
        store = InMemoryLinkingCodeStore()
        store.save("CODE01", "U-other", _NOW)

        self.assertEqual(delete_pending_links_for_user("U-bye", store), 0)


class LinkingCodePurgeThrottleTest(unittest.TestCase):
    def test_first_call_runs_immediately_and_returns_purged_count(self):
        store = InMemoryLinkingCodeStore()
        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))
        throttle = LinkingCodePurgeThrottle()

        result = throttle.maybe_run(store, _NOW)

        self.assertEqual(result, 1)
        self.assertIsNone(store.get("OLD001"))

    def test_second_call_within_min_interval_is_skipped(self):
        store = InMemoryLinkingCodeStore()
        throttle = LinkingCodePurgeThrottle()
        throttle.maybe_run(store, _NOW)

        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))
        skipped = throttle.maybe_run(store, _NOW + timedelta(minutes=30))

        self.assertIsNone(skipped)
        self.assertIsNotNone(store.get("OLD001"))

    def test_call_after_min_interval_runs_again(self):
        store = InMemoryLinkingCodeStore()
        throttle = LinkingCodePurgeThrottle()
        throttle.maybe_run(store, _NOW)

        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))
        result = throttle.maybe_run(store, _NOW + timedelta(hours=1, minutes=1))

        self.assertEqual(result, 1)
        self.assertIsNone(store.get("OLD001"))


if __name__ == "__main__":
    unittest.main()
