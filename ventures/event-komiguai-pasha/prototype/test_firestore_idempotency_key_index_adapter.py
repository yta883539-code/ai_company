"""firestore_idempotency_key_index_adapter.FirestoreIdempotencyKeyIndexStoreのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。kura-pasha/test_firestore_stripe_event_id_
adapter.pyと同じ軽量フェイク(collection/document/create/get のみを満たす最小インター
フェース)を使い、InMemoryIdempotencyKeyIndexStoreと観測可能な振る舞いが一致すること
(reserve_or_getの返り値)を検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_idempotency_key_index_adapter import FirestoreIdempotencyKeyIndexStore
from idempotency_key_index_store import AlreadyReservedError


class _AlreadyExists(Exception):
    """実SDKのgoogle.api_core.exceptions.AlreadyExists相当のフェイク例外。"""


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

    def create(self, data: dict) -> None:
        if self._doc_id in self._store:
            raise _AlreadyExists(self._doc_id)
        self._store[self._doc_id] = dict(data)

    def get(self):
        data = self._store.get(self._doc_id)
        return _FakeSnapshot(exists=data is not None, data=dict(data) if data else None)


class _FakeCollection:
    def __init__(self, expected_name: str, name: str, store: dict):
        assert name == expected_name
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)


class _RaisingOnGetCollection:
    """create()は常に失敗し、続くget()も常に例外を送出するコレクション
    (読み取りフォールバックそのものが失敗するケースの検証用)。"""

    def document(self, doc_id: str):
        return self

    def create(self, data: dict) -> None:
        raise _AlreadyExists("simulated")

    def get(self):
        raise RuntimeError("simulated network error")


class _FakeFirestoreClient:
    def __init__(self, *, raise_on_get: bool = False):
        self._store: dict = {}
        self._raise_on_get = raise_on_get

    def collection(self, name: str):
        assert name == "idempotency_key_index"
        if self._raise_on_get:
            return _RaisingOnGetCollection()
        return _FakeCollection("idempotency_key_index", name, self._store)


class FirestoreIdempotencyKeyIndexStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.store = FirestoreIdempotencyKeyIndexStore(self.client)
        self.now = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)

    def test_first_call_creates_document_and_returns_same_document_id(self):
        result = self.store.reserve_or_get(
            "idem-1",
            collection="one_time_draft",
            document_id="draft-aaaa",
            created_at=self.now,
        )
        self.assertEqual(result, "draft-aaaa")
        self.assertEqual(self.client._store["idem-1"]["documentId"], "draft-aaaa")

    def test_second_call_with_same_key_returns_first_document_id(self):
        self.store.reserve_or_get(
            "idem-1",
            collection="one_time_draft",
            document_id="draft-aaaa",
            created_at=self.now,
        )
        result = self.store.reserve_or_get(
            "idem-1",
            collection="one_time_draft",
            document_id="draft-bbbb",
            created_at=self.now,
        )
        self.assertEqual(result, "draft-aaaa")
        # 先行ドキュメントは上書きされない(衝突時は新規作成をスキップするのみ)。
        self.assertEqual(self.client._store["idem-1"]["documentId"], "draft-aaaa")

    def test_expire_at_is_written_only_when_given(self):
        self.store.reserve_or_get(
            "idem-draft",
            collection="one_time_draft",
            document_id="draft-aaaa",
            created_at=self.now,
            expire_at=self.now,
        )
        self.store.reserve_or_get(
            "idem-inquiry",
            collection="inquiry",
            document_id="inquiry-bbbb",
            created_at=self.now,
        )
        self.assertIn("expireAt", self.client._store["idem-draft"])
        self.assertNotIn("expireAt", self.client._store["idem-inquiry"])

    def test_create_failure_then_get_failure_raises_already_reserved_error(self):
        raising_client = _FakeFirestoreClient(raise_on_get=True)
        store = FirestoreIdempotencyKeyIndexStore(raising_client)
        with self.assertRaises(AlreadyReservedError):
            store.reserve_or_get(
                "idem-1",
                collection="one_time_draft",
                document_id="draft-aaaa",
                created_at=self.now,
            )


if __name__ == "__main__":
    unittest.main()
