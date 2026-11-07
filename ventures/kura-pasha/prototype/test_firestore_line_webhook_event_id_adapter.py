"""firestore_line_webhook_event_id_adapter.FirestoreLineWebhookEventIdStoreのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。test_firestore_linking_code_adapter.pyと
同じ軽量フェイク(collection/document/get/set のみを満たす最小インターフェース)を使い、
InMemoryLineWebhookEventIdStore(cloud_function_webhook.py)と観測可能な振る舞いが
(TTL超過時の能動的失効を除き)一致することを検証する。
"""

import unittest
from datetime import datetime, timedelta, timezone

from firestore_line_webhook_event_id_adapter import FirestoreLineWebhookEventIdStore


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


class FirestoreLineWebhookEventIdStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient("line_webhook_event_ids")
        self.store = FirestoreLineWebhookEventIdStore(self.client)

    def test_has_processed_for_unknown_id_is_false(self):
        self.assertFalse(self.store.has_processed("event-1"))

    def test_mark_processed_then_has_processed_is_true(self):
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        self.store.mark_processed("event-1", now=now)
        self.assertTrue(self.store.has_processed("event-1"))

    def test_mark_processed_writes_processed_at_and_expires_at(self):
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        self.store.mark_processed("event-1", now=now)
        data = self.client._store["event-1"]
        self.assertEqual(data["processed_at"], now)
        self.assertEqual(
            data["expires_at"], now + timedelta(seconds=7 * 24 * 60 * 60)
        )

    def test_has_processed_does_not_actively_expire(self):
        # Firestoreネイティブ TTLポリシーに失効を委譲する設計のため、本アダプタ自身は
        # expires_atを過ぎていてもドキュメントが物理的に残っていればTrueを返す
        # (design.md 2節: このラグは安全側にしか作用しないため許容する)。
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        self.store.mark_processed("event-1", now=now)
        far_future = now + timedelta(days=365)
        self.assertTrue(self.store.has_processed("event-1", now=far_future))

    def test_mark_processed_without_now_uses_current_time(self):
        before = datetime.now(timezone.utc)
        self.store.mark_processed("event-1")
        after = datetime.now(timezone.utc)
        processed_at = self.client._store["event-1"]["processed_at"]
        self.assertTrue(before <= processed_at <= after)

    def test_custom_ttl_seconds_is_reflected_in_expires_at(self):
        now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
        store = FirestoreLineWebhookEventIdStore(self.client, ttl_seconds=3600)
        store.mark_processed("event-2", now=now)
        data = self.client._store["event-2"]
        self.assertEqual(data["expires_at"], now + timedelta(seconds=3600))

    def test_has_processed_on_read_error_falls_back_to_false(self):
        raising_client = _FakeFirestoreClient("line_webhook_event_ids", raise_on_get=True)
        store = FirestoreLineWebhookEventIdStore(raising_client)
        self.assertFalse(store.has_processed("event-1"))


if __name__ == "__main__":
    unittest.main()
