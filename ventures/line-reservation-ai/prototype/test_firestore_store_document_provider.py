"""firestore_store_document_provider.FirestoreStoreDocumentProviderのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、firestore-provider-adapter-
design.md 2節が前提とした最小インターフェース(collection/document/get)のみを満たす
軽量フェイクをここで実装し、InMemoryStoreNameProvider・InMemoryRegionNameProvider
(cloud_function_process_event.py)と観測可能な振る舞いが一致することを検証する。
"""

import unittest

from firestore_store_document_provider import FirestoreStoreDocumentProvider


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


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)


class _FakeFirestoreClient:
    def __init__(self):
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections.setdefault(name, {}))

    def seed_store(self, store_id: str, data: dict) -> None:
        self._collections.setdefault("stores", {})[store_id] = dict(data)


class _RaisingDocumentRef:
    def get(self):
        raise RuntimeError("firestore permission denied")


class _RaisingCollection:
    def document(self, doc_id: str) -> _RaisingDocumentRef:
        return _RaisingDocumentRef()


class _RaisingFirestoreClient:
    def collection(self, name: str) -> _RaisingCollection:
        return _RaisingCollection()


class FirestoreStoreDocumentProviderTest(unittest.TestCase):
    def test_get_business_name_returns_field_when_document_exists(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"businessName": "美容室サンプル", "regionName": "渋谷区"})
        provider = FirestoreStoreDocumentProvider(client)

        self.assertEqual(provider.get_business_name("store-1"), "美容室サンプル")

    def test_get_region_name_returns_field_when_document_exists(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"businessName": "美容室サンプル", "regionName": "渋谷区"})
        provider = FirestoreStoreDocumentProvider(client)

        self.assertEqual(provider.get_region_name("store-1"), "渋谷区")

    def test_get_business_name_returns_empty_string_when_document_missing(self):
        client = _FakeFirestoreClient()
        provider = FirestoreStoreDocumentProvider(client)

        self.assertEqual(provider.get_business_name("unknown-store"), "")

    def test_get_region_name_returns_empty_string_when_document_missing(self):
        client = _FakeFirestoreClient()
        provider = FirestoreStoreDocumentProvider(client)

        self.assertEqual(provider.get_region_name("unknown-store"), "")

    def test_get_business_name_returns_empty_string_when_field_unset(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"regionName": "渋谷区"})
        provider = FirestoreStoreDocumentProvider(client)

        self.assertEqual(provider.get_business_name("store-1"), "")

    def test_get_region_name_returns_empty_string_when_field_unset(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"businessName": "美容室サンプル"})
        provider = FirestoreStoreDocumentProvider(client)

        self.assertEqual(provider.get_region_name("store-1"), "")

    def test_get_business_name_falls_back_to_empty_string_on_client_exception(self):
        provider = FirestoreStoreDocumentProvider(_RaisingFirestoreClient())

        self.assertEqual(provider.get_business_name("store-1"), "")

    def test_get_region_name_falls_back_to_empty_string_on_client_exception(self):
        provider = FirestoreStoreDocumentProvider(_RaisingFirestoreClient())

        self.assertEqual(provider.get_region_name("store-1"), "")


if __name__ == "__main__":
    unittest.main()
