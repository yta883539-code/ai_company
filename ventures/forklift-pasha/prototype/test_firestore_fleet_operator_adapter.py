"""firestore_fleet_operator_adapter.FirestoreFleetOperatorStore(基盤グループ: email・
plan_id・stripe_customer_id〈順引き+逆引き〉・trial_start_atの4フィールド、計9メソッド)の
テスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、fleet-operator-store-firestore-
adapter-design.md 3節が前提とした最小インターフェース(collection/document/get/set、
collection.where(...).limit(...).stream())のみを満たす軽量フェイクをここで実装し、
InMemoryFleetOperatorStore(trial_management.py)の基盤グループと観測可能な振る舞いが
一致することを検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_fleet_operator_adapter import FirestoreFleetOperatorStore


class _FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None, doc_id: str | None = None):
        self.exists = exists
        self._data = data
        self.id = doc_id

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


class _FakeQuery:
    def __init__(self, store: dict, field: str, value):
        self._store = store
        self._field = field
        self._value = value
        self._limit = None

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def stream(self):
        results = [
            _FakeSnapshot(exists=True, data=dict(data), doc_id=doc_id)
            for doc_id, data in self._store.items()
            if data.get(self._field) == self._value
        ]
        if self._limit is not None:
            results = results[: self._limit]
        return iter(results)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)

    def where(self, field: str, op: str, value) -> _FakeQuery:
        assert op == "=="
        return _FakeQuery(self._store, field, value)


class _FakeFirestoreClient:
    def __init__(self):
        self._collections: dict[str, dict] = {"fleet_operator": {}}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections[name])


class FirestoreFleetOperatorStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.store = FirestoreFleetOperatorStore(self.client)

    def test_get_email_unknown_internal_id_returns_none(self):
        self.assertIsNone(self.store.get_email("UNKNOWN"))

    def test_set_then_get_email_round_trips(self):
        self.store.set_email("F1", "owner@example.com")
        self.assertEqual(self.store.get_email("F1"), "owner@example.com")

    def test_set_email_overwrites(self):
        self.store.set_email("F1", "old@example.com")
        self.store.set_email("F1", "new@example.com")
        self.assertEqual(self.store.get_email("F1"), "new@example.com")

    def test_set_plan_id_does_not_clobber_email(self):
        self.store.set_email("F1", "owner@example.com")
        self.store.set_plan_id("F1", "light")
        self.assertEqual(self.store.get_email("F1"), "owner@example.com")
        self.assertEqual(self.store.get_plan_id("F1"), "light")

    def test_get_plan_id_unset_returns_none(self):
        self.assertIsNone(self.store.get_plan_id("F1"))

    def test_set_plan_id_overwrites(self):
        self.store.set_plan_id("F1", "light")
        self.store.set_plan_id("F1", "standard")
        self.assertEqual(self.store.get_plan_id("F1"), "standard")

    def test_stripe_customer_id_round_trip_and_reverse_lookup(self):
        self.store.set_stripe_customer_id("F1", "cus_123")
        self.assertEqual(self.store.get_stripe_customer_id("F1"), "cus_123")
        self.assertEqual(
            self.store.get_internal_id_by_stripe_customer_id("cus_123"), "F1"
        )

    def test_reverse_lookup_unknown_stripe_customer_id_returns_none(self):
        self.assertIsNone(self.store.get_internal_id_by_stripe_customer_id("cus_999"))

    def test_set_stripe_customer_id_overwrite_old_id_no_longer_resolves(self):
        # design.md 3.2節: Firestoreはライブクエリのため、上書きされた瞬間に旧IDでの
        # 単一フィールドクエリは自動的に0件になる(逆引き専用インデックスの明示的な
        # 清掃処理は不要)。
        self.store.set_stripe_customer_id("F1", "cus_old")
        self.store.set_stripe_customer_id("F1", "cus_new")
        self.assertIsNone(self.store.get_internal_id_by_stripe_customer_id("cus_old"))
        self.assertEqual(
            self.store.get_internal_id_by_stripe_customer_id("cus_new"), "F1"
        )

    def test_stripe_customer_id_independent_per_internal_id(self):
        self.store.set_stripe_customer_id("F1", "cus_1")
        self.store.set_stripe_customer_id("F2", "cus_2")
        self.assertEqual(
            self.store.get_internal_id_by_stripe_customer_id("cus_1"), "F1"
        )
        self.assertEqual(
            self.store.get_internal_id_by_stripe_customer_id("cus_2"), "F2"
        )

    def test_trial_start_at_round_trip(self):
        at = datetime(2026, 10, 23, tzinfo=timezone.utc)
        self.store.set_trial_start_at("F1", at)
        self.assertEqual(self.store.get_trial_start_at("F1"), at)

    def test_get_trial_start_at_unset_returns_none(self):
        self.assertIsNone(self.store.get_trial_start_at("F1"))

    def test_trial_start_at_does_not_clobber_other_fields(self):
        self.store.set_email("F1", "owner@example.com")
        self.store.set_plan_id("F1", "light")
        at = datetime(2026, 10, 23, tzinfo=timezone.utc)
        self.store.set_trial_start_at("F1", at)
        self.assertEqual(self.store.get_email("F1"), "owner@example.com")
        self.assertEqual(self.store.get_plan_id("F1"), "light")

    def test_fields_independent_per_internal_id(self):
        self.store.set_email("F1", "a@example.com")
        self.store.set_email("F2", "b@example.com")
        self.assertEqual(self.store.get_email("F1"), "a@example.com")
        self.assertEqual(self.store.get_email("F2"), "b@example.com")


if __name__ == "__main__":
    unittest.main()
