"""firestore_access_token_store.FirestoreAccessTokenStoreのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。test_firestore_fleet_operator_adapter.pyと
同じ軽量フェイク(collection/document/get/set、collection.where(...).limit(...).stream())を
ここでも実装し、InMemoryAccessTokenStore(access_token_store.py)と観測可能な振る舞いが
一致することを検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_access_token_store import FirestoreAccessTokenStore


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

    def stream(self):
        return iter(
            _FakeSnapshot(exists=True, data=dict(data), doc_id=doc_id)
            for doc_id, data in self._store.items()
        )


class _FakeFirestoreClient:
    def __init__(self):
        self._collections: dict[str, dict] = {"fleet_operator": {}}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections[name])


class FirestoreAccessTokenStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.store = FirestoreAccessTokenStore(self.client)

    def test_get_access_token_unknown_internal_id_returns_none(self):
        self.assertIsNone(self.store.get_access_token("UNKNOWN"))

    def test_set_then_get_access_token_round_trips(self):
        self.store.set_access_token("F1", "token_1")
        self.assertEqual(self.store.get_access_token("F1"), "token_1")

    def test_set_access_token_overwrites(self):
        self.store.set_access_token("F1", "token_old")
        self.store.set_access_token("F1", "token_new")
        self.assertEqual(self.store.get_access_token("F1"), "token_new")

    def test_get_internal_id_by_access_token_round_trips(self):
        self.store.set_access_token("F1", "token_1")
        self.assertEqual(self.store.get_internal_id_by_access_token("token_1"), "F1")

    def test_get_internal_id_by_access_token_unknown_returns_none(self):
        self.assertIsNone(self.store.get_internal_id_by_access_token("no_such_token"))

    def test_set_access_token_overwrite_old_token_no_longer_resolves(self):
        # design.md 2.3節: Firestoreはライブクエリのため、上書きされた瞬間に旧トークン
        # での照会は自動的に0件になる(InMemory版が持つ逆引きインデックスの明示的な
        # 清掃処理は不要)。
        self.store.set_access_token("F1", "token_old")
        self.store.set_access_token("F1", "token_new")
        self.assertIsNone(self.store.get_internal_id_by_access_token("token_old"))
        self.assertEqual(self.store.get_internal_id_by_access_token("token_new"), "F1")

    def test_access_token_independent_per_internal_id(self):
        self.store.set_access_token("F1", "token_1")
        self.store.set_access_token("F2", "token_2")
        self.assertEqual(self.store.get_internal_id_by_access_token("token_1"), "F1")
        self.assertEqual(self.store.get_internal_id_by_access_token("token_2"), "F2")

    def test_get_last_accessed_at_unset_returns_none(self):
        self.assertIsNone(self.store.get_last_accessed_at("F1"))

    def test_last_accessed_at_round_trip(self):
        at = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.store.set_last_accessed_at("F1", at)
        self.assertEqual(self.store.get_last_accessed_at("F1"), at)

    def test_last_accessed_at_does_not_clobber_access_token(self):
        self.store.set_access_token("F1", "token_1")
        at = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.store.set_last_accessed_at("F1", at)
        self.assertEqual(self.store.get_access_token("F1"), "token_1")
        self.assertEqual(self.store.get_last_accessed_at("F1"), at)

    def test_access_token_does_not_clobber_last_accessed_at(self):
        at = datetime(2026, 10, 24, tzinfo=timezone.utc)
        self.store.set_last_accessed_at("F1", at)
        self.store.set_access_token("F1", "token_1")
        self.assertEqual(self.store.get_last_accessed_at("F1"), at)
        self.assertEqual(self.store.get_access_token("F1"), "token_1")


if __name__ == "__main__":
    unittest.main()
