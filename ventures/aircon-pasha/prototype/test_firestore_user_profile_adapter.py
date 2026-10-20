"""firestore_user_profile_adapter.FirestoreUserProfileStore(基盤3メソッド+Stripe顧客ID
グループ)のテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、firestore-provider-adapter-
design.md 5節が前提とした最小インターフェース(collection/document/get/set・
firestore_client.batch()のset/commit)のみを満たす軽量フェイクをここで実装し、
InMemoryUserProfileStore(user_id_linking.py)の基盤3メソッド+Stripe顧客IDグループと
観測可能な振る舞いが一致することを検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_user_profile_adapter import FirestoreUserProfileStore
from user_id_linking import UserProfile


class _FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None):
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
        return _FakeSnapshot(exists=data is not None, data=dict(data) if data else None)

    def set(self, data: dict, merge: bool = False) -> None:
        if merge and self._doc_id in self._store:
            self._store[self._doc_id].update(data)
        else:
            self._store[self._doc_id] = dict(data)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)


class _FakeBatch:
    def __init__(self):
        self._writes: list[tuple] = []

    def set(self, doc_ref: _FakeDocumentRef, data: dict, merge: bool = False) -> None:
        self._writes.append((doc_ref, data, merge))

    def commit(self) -> None:
        for doc_ref, data, merge in self._writes:
            doc_ref.set(data, merge=merge)
        self._writes = []


class _FakeFirestoreClient:
    def __init__(self):
        self._collections: dict[str, dict] = {
            "user_profile": {},
            "stripe_customer_index": {},
        }

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections[name])

    def batch(self) -> _FakeBatch:
        return _FakeBatch()


def _make_profile(**overrides) -> UserProfile:
    defaults = dict(
        business_name="エアコンクリーニング太郎商店",
        business_type="individual",
        email="taro@example.com",
        linked_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


class FirestoreUserProfileStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.store = FirestoreUserProfileStore(self.client)

    def test_save_then_get_round_trips_all_fields(self):
        profile = _make_profile()
        self.store.save("U1", profile)
        got = self.store.get("U1")
        self.assertEqual(got, profile)

    def test_get_unknown_user_id_returns_none(self):
        self.assertIsNone(self.store.get("U_unknown"))

    def test_exists_true_after_save_false_before(self):
        self.assertFalse(self.store.exists("U1"))
        self.store.save("U1", _make_profile())
        self.assertTrue(self.store.exists("U1"))

    def test_get_backward_compatible_with_missing_keys(self):
        # design.md 19.3節: フィールド追加前に書き込まれた既存ドキュメント相当
        # (is_following等のキーが無いdict)でも、dataclass既定値で補われる。
        self.client._collections["user_profile"]["U_old"] = {
            "business_name": "旧店舗",
            "business_type": "individual",
            "email": "old@example.com",
            "linked_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        }
        got = self.store.get("U_old")
        self.assertEqual(got.business_name, "旧店舗")
        self.assertTrue(got.is_following)
        self.assertEqual(got.trial_generation_count, 0)
        self.assertIsNone(got.stripe_customer_id)

    def test_set_stripe_customer_id_then_forward_lookup(self):
        self.store.save("U1", _make_profile())
        self.store.set_stripe_customer_id("U1", "cus_123")
        self.assertEqual(self.store.get_stripe_customer_id("U1"), "cus_123")

    def test_set_stripe_customer_id_then_reverse_lookup(self):
        self.store.save("U1", _make_profile())
        self.store.set_stripe_customer_id("U1", "cus_123")
        self.assertEqual(self.store.get_user_id_by_stripe_customer_id("cus_123"), "U1")

    def test_get_user_id_by_unknown_stripe_customer_id_returns_none(self):
        self.assertIsNone(self.store.get_user_id_by_stripe_customer_id("cus_unknown"))

    def test_get_stripe_customer_id_for_unknown_user_returns_none(self):
        self.assertIsNone(self.store.get_stripe_customer_id("U_unknown"))

    def test_set_stripe_customer_id_does_not_clobber_other_fields(self):
        profile = _make_profile(current_plan_id="plan_basic")
        self.store.save("U1", profile)
        self.store.set_stripe_customer_id("U1", "cus_123")
        got = self.store.get("U1")
        self.assertEqual(got.current_plan_id, "plan_basic")
        self.assertEqual(got.stripe_customer_id, "cus_123")

    def test_set_stripe_customer_id_independent_per_user(self):
        self.store.save("U1", _make_profile())
        self.store.save("U2", _make_profile(business_name="別店舗"))
        self.store.set_stripe_customer_id("U1", "cus_1")
        self.store.set_stripe_customer_id("U2", "cus_2")
        self.assertEqual(self.store.get_user_id_by_stripe_customer_id("cus_1"), "U1")
        self.assertEqual(self.store.get_user_id_by_stripe_customer_id("cus_2"), "U2")


if __name__ == "__main__":
    unittest.main()
