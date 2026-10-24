"""firestore_user_profile_adapter.FirestoreUserProfileStoreのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。firestore-provider-adapter-design.md
5.2節・6.2節が前提とした最小インターフェース(collection/document/get/set/delete)のみを
満たす軽量フェイクをここで実装し、InMemoryUserProfileStore(application_form_submission_
flow.py)と観測可能な振る舞いが一致すること、同一ドキュメントを共有する他フィールド
グループを消さないこと(5.3節のmerge安全性)、およびStripe顧客IDの再紐付け時に
stripe_customer_index側の旧エントリが削除されること(6.3節)を検証する。
"""

import unittest

from firestore_user_profile_adapter import FirestoreUserProfileStore


class _FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


class _FakeDocumentRef:
    def __init__(self, store: dict, key):
        self._store = store
        self._key = key

    def get(self):
        data = self._store.get(self._key)
        return _FakeSnapshot(exists=data is not None, data=dict(data) if data else None)

    def set(self, data: dict) -> None:
        self._store[self._key] = dict(data)

    def delete(self) -> None:
        self._store.pop(self._key, None)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)


class _FakeFirestoreClient:
    def __init__(self):
        self._user_profile_store: dict = {}
        self._stripe_index_store: dict = {}

    def collection(self, name: str) -> _FakeCollection:
        if name == "user_profile":
            return _FakeCollection(self._user_profile_store)
        assert name == "stripe_customer_index"
        return _FakeCollection(self._stripe_index_store)


class FirestoreUserProfileStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.store = FirestoreUserProfileStore(self.client)

    def test_get_gym_area_pairs_for_unknown_user_is_empty_string(self):
        self.assertEqual(self.store.get_gym_area_pairs("u1"), "")

    def test_get_email_for_unknown_user_is_none(self):
        self.assertIsNone(self.store.get_email("u1"))

    def test_set_then_get_gym_area_pairs(self):
        self.store.set_gym_area_pairs("u1", "shinjuku:east,shibuya:west")
        self.assertEqual(
            self.store.get_gym_area_pairs("u1"), "shinjuku:east,shibuya:west"
        )

    def test_set_then_get_email(self):
        self.store.set_email("u1", "owner@example.com")
        self.assertEqual(self.store.get_email("u1"), "owner@example.com")

    def test_resubmission_overwrites_gym_area_pairs_entirely(self):
        self.store.set_gym_area_pairs("u1", "shinjuku:east")
        self.store.set_gym_area_pairs("u1", "shibuya:west")
        self.assertEqual(self.store.get_gym_area_pairs("u1"), "shibuya:west")

    def test_set_email_does_not_erase_gym_area_pairs(self):
        self.store.set_gym_area_pairs("u1", "shinjuku:east")
        self.store.set_email("u1", "owner@example.com")
        self.assertEqual(self.store.get_gym_area_pairs("u1"), "shinjuku:east")
        self.assertEqual(self.store.get_email("u1"), "owner@example.com")

    def test_set_gym_area_pairs_does_not_erase_other_group_fields(self):
        self.client.collection("user_profile").document("u1").set(
            {"stripe_customer_id": "cus_abc123"}
        )
        self.store.set_gym_area_pairs("u1", "shinjuku:east")
        snapshot = self.client.collection("user_profile").document("u1").get()
        self.assertEqual(snapshot.to_dict().get("stripe_customer_id"), "cus_abc123")
        self.assertEqual(self.store.get_gym_area_pairs("u1"), "shinjuku:east")

    def test_independent_per_user_id(self):
        self.store.set_gym_area_pairs("u1", "shinjuku:east")
        self.store.set_email("u2", "other@example.com")
        self.assertEqual(self.store.get_gym_area_pairs("u2"), "")
        self.assertIsNone(self.store.get_email("u1"))

    def test_get_stripe_customer_id_for_unknown_user_is_none(self):
        self.assertIsNone(self.store.get_stripe_customer_id("u1"))

    def test_get_user_id_by_stripe_customer_id_for_unknown_customer_is_none(self):
        self.assertIsNone(self.store.get_user_id_by_stripe_customer_id("cus_unknown"))

    def test_set_then_get_stripe_customer_id(self):
        self.store.set_stripe_customer_id("u1", "cus_abc123")
        self.assertEqual(self.store.get_stripe_customer_id("u1"), "cus_abc123")

    def test_set_stripe_customer_id_populates_reverse_lookup(self):
        self.store.set_stripe_customer_id("u1", "cus_abc123")
        self.assertEqual(
            self.store.get_user_id_by_stripe_customer_id("cus_abc123"), "u1"
        )

    def test_rebinding_stripe_customer_id_removes_previous_reverse_lookup_entry(self):
        self.store.set_stripe_customer_id("u1", "cus_old")
        self.store.set_stripe_customer_id("u1", "cus_new")
        self.assertIsNone(self.store.get_user_id_by_stripe_customer_id("cus_old"))
        self.assertEqual(
            self.store.get_user_id_by_stripe_customer_id("cus_new"), "u1"
        )
        self.assertEqual(self.store.get_stripe_customer_id("u1"), "cus_new")

    def test_set_stripe_customer_id_does_not_erase_gym_area_pairs(self):
        self.store.set_gym_area_pairs("u1", "shinjuku:east")
        self.store.set_stripe_customer_id("u1", "cus_abc123")
        self.assertEqual(self.store.get_gym_area_pairs("u1"), "shinjuku:east")

    def test_setting_same_stripe_customer_id_twice_is_idempotent(self):
        self.store.set_stripe_customer_id("u1", "cus_abc123")
        self.store.set_stripe_customer_id("u1", "cus_abc123")
        self.assertEqual(
            self.store.get_user_id_by_stripe_customer_id("cus_abc123"), "u1"
        )


if __name__ == "__main__":
    unittest.main()
