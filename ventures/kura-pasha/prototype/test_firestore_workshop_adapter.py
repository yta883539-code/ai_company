"""firestore_workshop_adapter.FirestoreWorkshopStore(基盤グループ)のテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、workshop-store-firestore-
adapter-design.md 2節が前提とした最小インターフェース(collection/document/get/
set/update・collection.stream())のみを満たす軽量フェイクをここで実装し、
InMemoryWorkshopStore(usage_counter_workshop.py)の基盤グループと観測可能な
振る舞いが一致することを検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_workshop_adapter import ArrayUnion, FirestoreWorkshopStore
from usage_counter_workshop import PendingContractorTransfer


class _FakeSnapshot:
    def __init__(self, doc_id: str, exists: bool, data: dict | None):
        self.id = doc_id
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


class _FakeDocumentRef:
    def __init__(self, store: dict, doc_id: str):
        self._store = store
        self._doc_id = doc_id

    def get(self):
        data = self._store.get(self._doc_id)
        return _FakeSnapshot(self._doc_id, exists=data is not None, data=dict(data) if data else None)

    def set(self, data: dict, merge: bool = False) -> None:
        if merge and self._doc_id in self._store:
            self._store[self._doc_id].update(data)
        else:
            self._store[self._doc_id] = dict(data)

    def update(self, data: dict) -> None:
        # design.md 2節`add_member_user_id`相当: ArrayUnionセンチネルを認識して
        # 重複排除しながらマージする(実Firestoreサーバー側の挙動を模す)。
        existing = self._store.setdefault(self._doc_id, {})
        for key, value in data.items():
            if isinstance(value, ArrayUnion):
                current = list(existing.get(key, []))
                for item in value.values:
                    if item not in current:
                        current.append(item)
                existing[key] = current
            else:
                existing[key] = value


class _FakeCollection:
    def __init__(self, expected_name: str, name: str, store: dict):
        assert name == expected_name
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)

    def stream(self):
        return [
            _FakeSnapshot(doc_id, exists=True, data=dict(data))
            for doc_id, data in self._store.items()
        ]


class _FakeFirestoreClient:
    def __init__(self):
        self._store: dict = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection("craftsman_workshop", name, self._store)


class FirestoreWorkshopStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.store = FirestoreWorkshopStore(self.client)

    def test_set_members_then_get_contractor_and_member_ids(self):
        self.store.set_members("w1", "U_owner", ["U_member1"], {"U_owner": "親方太郎"})
        self.assertEqual(self.store.get_contractor_user_id("w1"), "U_owner")
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])
        self.assertEqual(self.store.get_member_display_name("w1", "U_owner"), "親方太郎")

    def test_set_members_deduplicates_contractor_from_member_list(self):
        # 契約者自身がmember_user_idsにも含まれていても1件のみ(InMemory実装と同じ挙動)。
        self.store.set_members("w1", "U_owner", ["U_owner", "U_member1"])
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])

    def test_set_contractor_user_id_overwrites(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_contractor_user_id("w1", "U_new_owner")
        self.assertEqual(self.store.get_contractor_user_id("w1"), "U_new_owner")

    def test_get_contractor_user_id_for_unknown_workshop_raises(self):
        # design.md 23.3節: fail-closed(安全側デフォルトに合流させず例外を伝播させる)。
        with self.assertRaises(KeyError):
            self.store.get_contractor_user_id("unknown")

    def test_get_plan_id_for_unknown_workshop_raises(self):
        with self.assertRaises(KeyError):
            self.store.get_plan_id("unknown")

    def test_get_member_user_ids_for_unknown_workshop_is_empty(self):
        self.assertEqual(self.store.get_member_user_ids("unknown"), [])

    def test_add_member_user_id_appends_new_member(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.add_member_user_id("w1", "U_member2")
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member2"])

    def test_add_member_user_id_is_idempotent(self):
        # ArrayUnionと同じ重複排除契約(design.md 2節・3節の検討事項)。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.add_member_user_id("w1", "U_member1")
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])

    def test_get_member_display_name_for_unknown_user_is_none(self):
        self.store.set_members("w1", "U_owner", [], {"U_owner": "親方太郎"})
        self.assertIsNone(self.store.get_member_display_name("w1", "U_unknown"))

    def test_set_plan_then_get_plan_id(self):
        self.store.set_plan("w1", "standard")
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    def test_workshop_name_roundtrip_and_default_none(self):
        self.assertIsNone(self.store.get_workshop_name("w1"))
        self.store.set_workshop_name("w1", "鍛治屋 寅吉")
        self.assertEqual(self.store.get_workshop_name("w1"), "鍛治屋 寅吉")

    def test_first_generation_notice_sent_roundtrip_and_default_false(self):
        self.assertFalse(self.store.get_first_generation_notice_sent("w1"))
        self.store.set_first_generation_notice_sent("w1")
        self.assertTrue(self.store.get_first_generation_notice_sent("w1"))

    def test_all_workshop_ids_lists_created_workshops(self):
        self.store.set_members("w1", "U_owner1", [])
        self.store.set_members("w2", "U_owner2", [])
        self.assertEqual(sorted(self.store.all_workshop_ids()), ["w1", "w2"])

    def test_fields_do_not_clobber_each_other_via_merge(self):
        # merge=Trueによる部分更新方針(design.md 2節・27節)の確認: 異なるタイミングで
        # 書き込まれる複数フィールドが、互いの値を消さずに共存できること。
        self.store.set_members("w1", "U_owner", ["U_member1"], {"U_owner": "親方太郎"})
        self.store.set_plan("w1", "light")
        self.store.set_workshop_name("w1", "鍛治屋 寅吉")
        self.store.set_first_generation_notice_sent("w1")

        self.assertEqual(self.store.get_contractor_user_id("w1"), "U_owner")
        self.assertEqual(self.store.get_plan_id("w1"), "light")
        self.assertEqual(self.store.get_workshop_name("w1"), "鍛治屋 寅吉")
        self.assertTrue(self.store.get_first_generation_notice_sent("w1"))
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])

    def test_pending_reduction_effective_at_roundtrip_and_default_none(self):
        self.assertIsNone(self.store.get_pending_reduction_effective_at("w1"))
        effective_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.store.set_pending_reduction_effective_at("w1", effective_at)
        self.assertEqual(self.store.get_pending_reduction_effective_at("w1"), effective_at)

    def test_specified_retention_member_name_roundtrip_and_default_none(self):
        self.assertIsNone(self.store.get_specified_retention_member_name("w1"))
        self.store.set_specified_retention_member_name("w1", "U_member1")
        self.assertEqual(self.store.get_specified_retention_member_name("w1"), "U_member1")

    def test_apply_member_reduction_replaces_member_ids(self):
        self.store.set_members("w1", "U_owner", ["U_member1", "U_member2"])
        self.store.apply_member_reduction("w1", ["U_owner"])
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner"])

    def test_apply_member_reduction_clears_pending_effective_at_and_retention_name(self):
        # フェーズ223(design.md 19節)の確定仕様: サイクル1回限りの入力として両方クリアする。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_pending_reduction_effective_at(
            "w1", datetime(2026, 11, 1, tzinfo=timezone.utc)
        )
        self.store.set_specified_retention_member_name("w1", "U_member1")

        self.store.apply_member_reduction("w1", ["U_owner"])

        self.assertIsNone(self.store.get_pending_reduction_effective_at("w1"))
        self.assertIsNone(self.store.get_specified_retention_member_name("w1"))

    def test_apply_member_reduction_does_not_clobber_unrelated_fields(self):
        # merge=True方針(design.md 2節・27節)の確認: plan_id等の無関係フィールドは消えない。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_plan("w1", "standard")
        self.store.apply_member_reduction("w1", ["U_owner"])
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    # --- design.md 7節: 契約者引き継ぎ系グループ(pending_contractor_transfer) ---

    def test_pending_contractor_transfer_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_pending_contractor_transfer("w1"))

    def test_pending_contractor_transfer_roundtrip(self):
        self.store.set_members("w1", "U_owner", ["U_member1"])
        pending = PendingContractorTransfer(
            candidate_user_id="U_member1",
            candidate_member_name="弟子次郎",
            requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
        )
        self.store.set_pending_contractor_transfer("w1", pending)

        result = self.store.get_pending_contractor_transfer("w1")
        self.assertEqual(result, pending)

    def test_clear_pending_contractor_transfer_resets_to_none(self):
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_pending_contractor_transfer(
            "w1",
            PendingContractorTransfer(
                candidate_user_id="U_member1",
                candidate_member_name="弟子次郎",
                requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
            ),
        )
        self.store.clear_pending_contractor_transfer("w1")
        self.assertIsNone(self.store.get_pending_contractor_transfer("w1"))

    def test_set_pending_contractor_transfer_does_not_clobber_unrelated_fields(self):
        # merge=True方針(design.md 2節・27節)の確認: plan_id等の無関係フィールドは消えない。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_plan("w1", "standard")
        self.store.set_pending_contractor_transfer(
            "w1",
            PendingContractorTransfer(
                candidate_user_id="U_member1",
                candidate_member_name="弟子次郎",
                requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
            ),
        )
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    def test_clear_pending_contractor_transfer_does_not_clobber_unrelated_fields(self):
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_plan("w1", "standard")
        self.store.set_pending_contractor_transfer(
            "w1",
            PendingContractorTransfer(
                candidate_user_id="U_member1",
                candidate_member_name="弟子次郎",
                requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
            ),
        )
        self.store.clear_pending_contractor_transfer("w1")
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    # --- design.md 9節: trial系グループ(trial_start_at・trial_generation_used) ---

    def test_get_trial_start_at_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_trial_start_at("w1"))

    def test_trial_start_at_roundtrip(self):
        self.store.set_members("w1", "U_owner", [])
        trial_start_at = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
        self.store.set_trial_start_at("w1", trial_start_at)
        self.assertEqual(self.store.get_trial_start_at("w1"), trial_start_at)

    def test_get_trial_generation_used_default_false(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertFalse(self.store.get_trial_generation_used("w1"))

    def test_trial_generation_used_roundtrip(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_trial_generation_used("w1")
        self.assertTrue(self.store.get_trial_generation_used("w1"))

    def test_set_trial_generation_used_explicit_value(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_trial_generation_used("w1", used=True)
        self.assertTrue(self.store.get_trial_generation_used("w1"))

    def test_trial_fields_do_not_clobber_unrelated_fields(self):
        # merge=True方針(design.md 2節・27節)の確認: plan_id等の無関係フィールドは消えない。
        self.store.set_members("w1", "U_owner", [])
        self.store.set_plan("w1", "standard")
        self.store.set_trial_start_at("w1", datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc))
        self.store.set_trial_generation_used("w1")
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    def test_trial_start_at_and_generation_used_are_independent(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_trial_start_at("w1", datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc))
        self.assertFalse(self.store.get_trial_generation_used("w1"))
        self.store.set_trial_generation_used("w1")
        self.assertEqual(
            self.store.get_trial_start_at("w1"),
            datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
