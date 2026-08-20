#!/usr/bin/env python3
"""user_id_linking.pyの単体テスト。
line-user-id-linking-design.mdの連携コード発行・解決ロジックの仕様に沿った挙動を確認する。"""

import random
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from application_form_submission_flow import InMemoryUserProfileStore  # noqa: E402
from user_id_linking import (  # noqa: E402
    InMemoryLinkingCodeStore,
    LinkingCodePurgeThrottle,
    LinkingResolution,
    handle_form_submission_with_linking_code,
    issue_linking_code_on_follow,
    purge_expired_links,
    resolve_linking_code,
)

_NOW = datetime(2026, 8, 20, 12, 0, 0)


class IssueLinkingCodeOnFollowTest(unittest.TestCase):
    def test_issues_a_six_character_code_from_the_restricted_alphabet(self):
        store = InMemoryLinkingCodeStore()
        code = issue_linking_code_on_follow(
            "U1234", store, _NOW, random.Random(1)
        )
        self.assertEqual(len(code), 6)
        for ambiguous_char in "0O1IL":
            self.assertNotIn(ambiguous_char, code)

    def test_saves_the_issued_code_with_user_id_and_issued_at(self):
        store = InMemoryLinkingCodeStore()
        code = issue_linking_code_on_follow(
            "U1234", store, _NOW, random.Random(2)
        )
        self.assertEqual(store.get(code), ("U1234", _NOW))

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

        # 既存コード"AAAAAA"を占有させておく
        store.save("AAAAAA", "U_other", _NOW)
        rng = _FixedThenVaryingRng(first="AAAAAA", rest="BBBBBB")
        code = issue_linking_code_on_follow("U9999", store, _NOW, rng)
        self.assertEqual(code, "BBBBBB")
        self.assertEqual(store.get("BBBBBB"), ("U9999", _NOW))
        # 既存コードは上書きされていない
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


class HandleFormSubmissionWithLinkingCodeTest(unittest.TestCase):
    def test_resolves_code_then_writes_gym_area_pairs(self):
        linking_store = InMemoryLinkingCodeStore()
        linking_store.save("ABC234", "U1234", _NOW)
        profile_store = InMemoryUserProfileStore()

        result = handle_form_submission_with_linking_code(
            {"linking_code": "ABC234", "gym_area_pairs_raw": "ジムA/○○区"},
            profile_store,
            linking_store,
            _NOW,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.user_id, "U1234")
        self.assertEqual(profile_store.get_gym_area_pairs("U1234"), "ジムA/○○区")

    def test_invalid_code_does_not_write_anything(self):
        linking_store = InMemoryLinkingCodeStore()
        profile_store = InMemoryUserProfileStore()

        result = handle_form_submission_with_linking_code(
            {"linking_code": "ZZZ999", "gym_area_pairs_raw": "ジムA/○○区"},
            profile_store,
            linking_store,
            _NOW,
        )

        self.assertFalse(result.ok)
        self.assertIsNone(result.user_id)
        self.assertEqual(profile_store.get_gym_area_pairs("U1234"), "")


class PurgeExpiredLinksTest(unittest.TestCase):
    def test_removes_only_entries_past_the_ttl(self):
        store = InMemoryLinkingCodeStore()
        store.save("FRESH1", "U-fresh", _NOW)
        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))
        store.save("EDGE01", "U-edge", _NOW - timedelta(hours=24))  # 境界ちょうどは残す

        purged = purge_expired_links(store, _NOW)

        self.assertEqual(purged, 1)
        self.assertIsNone(store.get("OLD001"))
        self.assertIsNotNone(store.get("FRESH1"))
        self.assertIsNotNone(store.get("EDGE01"))

    def test_returns_zero_when_nothing_is_expired(self):
        store = InMemoryLinkingCodeStore()
        store.save("FRESH1", "U-fresh", _NOW)

        self.assertEqual(purge_expired_links(store, _NOW), 0)

    def test_is_idempotent_with_lazy_deletion_on_resolve(self):
        store = InMemoryLinkingCodeStore()
        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))

        # resolve側の遅延削除で先に消えても、続くパージは0件でエラーにならない。
        resolve_linking_code("OLD001", store, _NOW)
        self.assertEqual(purge_expired_links(store, _NOW), 0)

    def test_purged_code_can_no_longer_be_resolved(self):
        store = InMemoryLinkingCodeStore()
        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))

        purge_expired_links(store, _NOW)
        resolution = resolve_linking_code("OLD001", store, _NOW)

        self.assertFalse(resolution.ok)


class LinkingCodePurgeThrottleTest(unittest.TestCase):
    """linking-code-purge-trigger-design.mdで採用したprocess_memo_event便乗トリガーの
    間引き(MIN_INTERVAL=1時間)を検証する。"""

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
        self.assertIsNotNone(store.get("OLD001"))  # 間引かれたので削除されていない

    def test_call_after_min_interval_runs_again(self):
        store = InMemoryLinkingCodeStore()
        throttle = LinkingCodePurgeThrottle()
        throttle.maybe_run(store, _NOW)

        store.save("OLD001", "U-old", _NOW - timedelta(hours=25))
        result = throttle.maybe_run(store, _NOW + timedelta(hours=1, minutes=1))

        self.assertEqual(result, 1)
        self.assertIsNone(store.get("OLD001"))

    def test_returns_zero_not_none_when_run_but_nothing_expired(self):
        # スキップ(None)と「実行したが対象0件」(0)を呼び出し側が区別できることを確認する。
        store = InMemoryLinkingCodeStore()
        throttle = LinkingCodePurgeThrottle()

        self.assertEqual(throttle.maybe_run(store, _NOW), 0)


if __name__ == "__main__":
    unittest.main()
