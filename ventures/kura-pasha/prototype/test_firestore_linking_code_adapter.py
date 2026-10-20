"""firestore_linking_code_adapter.FirestorePendingLinkStore・FirestoreWorkshopInviteStoreの
テスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、linking-code-store-firestore-
adapter-design.md 2節・invite-code-store-firestore-adapter-design.md 2節が前提とした
最小インターフェース(collection/document/get/set/delete・collection.stream())のみを
満たす軽量フェイクをここで実装し、InMemoryLinkingCodeStore(workshop_linking.py)と
観測可能な振る舞いが一致することを検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_linking_code_adapter import (
    FirestorePendingLinkStore,
    FirestoreWorkshopInviteStore,
)


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

    def set(self, data: dict) -> None:
        self._store[self._doc_id] = dict(data)

    def delete(self) -> None:
        self._store.pop(self._doc_id, None)


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
    def __init__(self, collection_name: str):
        self._collection_name = collection_name
        self._store: dict = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collection_name, name, self._store)


class FirestorePendingLinkStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient("pending_links")
        self.store = FirestorePendingLinkStore(self.client)

    def test_get_for_unknown_code_is_none(self):
        self.assertIsNone(self.store.get("ABC123"))

    def test_save_then_get_roundtrip(self):
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.store.save("ABC123", "U_user1", issued_at)
        self.assertEqual(self.store.get("ABC123"), ("U_user1", issued_at))

    def test_delete_removes_entry(self):
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.store.save("ABC123", "U_user1", issued_at)
        self.store.delete("ABC123")
        self.assertIsNone(self.store.get("ABC123"))

    def test_delete_of_unknown_code_is_noop(self):
        self.store.delete("NOPE99")  # 例外を送出しないことのみ確認

    def test_get_with_missing_field_falls_back_to_none(self):
        # issued_atのみ欠けた不整合なドキュメントを直接差し込む(手動復旧ミス等を想定)。
        self.client._store["BROKEN"] = {"user_id": "U_user1"}
        self.assertIsNone(self.store.get("BROKEN"))

    def test_items_lists_all_entries(self):
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.store.save("ABC123", "U_user1", issued_at)
        self.store.save("XYZ789", "U_user2", issued_at)
        self.assertEqual(
            sorted(self.store.items()),
            sorted(
                [
                    ("ABC123", "U_user1", issued_at),
                    ("XYZ789", "U_user2", issued_at),
                ]
            ),
        )

    def test_items_skips_entries_with_missing_fields(self):
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.store.save("ABC123", "U_user1", issued_at)
        self.client._store["BROKEN"] = {"user_id": "U_user2"}
        self.assertEqual(list(self.store.items()), [("ABC123", "U_user1", issued_at)])


class FirestoreWorkshopInviteStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient("pending_workshop_invites")
        self.store = FirestoreWorkshopInviteStore(self.client)

    def test_get_for_unknown_code_is_none(self):
        self.assertIsNone(self.store.get("INV001"))

    def test_save_then_get_roundtrip(self):
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.store.save("INV001", "workshop_1", issued_at)
        self.assertEqual(self.store.get("INV001"), ("workshop_1", issued_at))

    def test_delete_removes_entry(self):
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.store.save("INV001", "workshop_1", issued_at)
        self.store.delete("INV001")
        self.assertIsNone(self.store.get("INV001"))

    def test_items_lists_all_entries(self):
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        self.store.save("INV001", "workshop_1", issued_at)
        self.store.save("INV002", "workshop_2", issued_at)
        self.assertEqual(
            sorted(self.store.items()),
            sorted(
                [
                    ("INV001", "workshop_1", issued_at),
                    ("INV002", "workshop_2", issued_at),
                ]
            ),
        )

    def test_two_stores_do_not_share_state_even_with_same_code(self):
        """design.md 1節: pending_links・pending_workshop_invitesは名前空間が分離された
        別コレクションであることを確認する(同じcodeを使っても互いに影響しない)。"""
        issued_at = datetime(2026, 10, 20, 3, 0, tzinfo=timezone.utc)
        link_client = _FakeFirestoreClient("pending_links")
        link_store = FirestorePendingLinkStore(link_client)
        link_store.save("SAME01", "U_user1", issued_at)

        self.store.save("SAME01", "workshop_1", issued_at)

        self.assertEqual(link_store.get("SAME01"), ("U_user1", issued_at))
        self.assertEqual(self.store.get("SAME01"), ("workshop_1", issued_at))


if __name__ == "__main__":
    unittest.main()
