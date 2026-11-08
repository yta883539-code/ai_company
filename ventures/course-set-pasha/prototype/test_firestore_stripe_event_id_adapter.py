"""firestore_stripe_event_id_adapter.FirestoreStripeEventIdStoreのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。既存の他アダプタテストと同じ軽量フェイク
(collection/document/get/set のみを満たす最小インターフェース)を使い、
InMemoryStripeEventIdStore(stripe_webhook.py)と観測可能な振る舞いが一致することを検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_stripe_event_id_adapter import FirestoreStripeEventIdStore


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

    def set(self, data: dict) -> None:
        self._store[self._doc_id] = dict(data)


class _FakeCollection:
    def __init__(self, expected_name: str, name: str, store: dict):
        assert name == expected_name
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)


class _RaisingCollection:
    """get()呼び出し時に常に例外を送出するコレクション(読み取り失敗のフォールバック検証用)。"""

    def document(self, doc_id: str):
        return self

    def get(self):
        raise RuntimeError("simulated network error")


class _FakeFirestoreClient:
    def __init__(self, collection_name: str, *, raise_on_get: bool = False):
        self._collection_name = collection_name
        self._store: dict = {}
        self._raise_on_get = raise_on_get

    def collection(self, name: str):
        if self._raise_on_get:
            return _RaisingCollection()
        return _FakeCollection(self._collection_name, name, self._store)


class FirestoreStripeEventIdStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient("processed_stripe_events")
        self.store = FirestoreStripeEventIdStore(self.client)

    def test_has_processed_for_unknown_id_is_false(self):
        self.assertFalse(self.store.has_processed("evt_1"))

    def test_mark_processed_then_has_processed_is_true(self):
        self.store.mark_processed("evt_1")
        self.assertTrue(self.store.has_processed("evt_1"))

    def test_mark_processed_writes_processed_at(self):
        before = datetime.now(timezone.utc)
        self.store.mark_processed("evt_1")
        after = datetime.now(timezone.utc)
        processed_at = self.client._store["evt_1"]["processed_at"]
        self.assertTrue(before <= processed_at <= after)

    def test_mark_processed_is_idempotent_on_repeated_calls(self):
        self.store.mark_processed("evt_1")
        self.store.mark_processed("evt_1")
        self.assertTrue(self.store.has_processed("evt_1"))
        self.assertEqual(len(self.client._store), 1)

    def test_distinct_event_ids_are_independent(self):
        self.store.mark_processed("evt_1")
        self.assertFalse(self.store.has_processed("evt_2"))

    def test_has_processed_on_read_error_falls_back_to_false(self):
        raising_client = _FakeFirestoreClient("processed_stripe_events", raise_on_get=True)
        store = FirestoreStripeEventIdStore(raising_client)
        self.assertFalse(store.has_processed("evt_1"))


if __name__ == "__main__":
    unittest.main()
