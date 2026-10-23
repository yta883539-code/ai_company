"""firestore_user_profile_adapter.FirestoreUserProfileProviderのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、firestore-provider-adapter-
design.md 2節が前提とした最小インターフェース(collection/document/get/set)のみを
満たす軽量フェイクをここで実装し、InMemoryUserProfileStore(usage_counter_workshop.py)
と観測可能な振る舞いが一致することを検証する。
"""

import unittest

from firestore_user_profile_adapter import FirestoreUserProfileProvider


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


class _FakeFirestoreClient:
    def __init__(self) -> None:
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections.setdefault(name, {}))


class _RaisingDocumentRef:
    def get(self):
        raise RuntimeError("simulated connection error")

    def set(self, data: dict, merge: bool = False) -> None:
        raise RuntimeError("simulated connection error")


class _RaisingFirestoreClient:
    def collection(self, name: str):
        class _Collection:
            def document(self, doc_id: str):
                return _RaisingDocumentRef()

        return _Collection()


class FirestoreUserProfileProviderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = _FakeFirestoreClient()
        self.provider = FirestoreUserProfileProvider(self.client)

    def test_get_workshop_id_unknown_user_returns_none(self) -> None:
        self.assertIsNone(self.provider.get_workshop_id("user-1"))

    def test_link_then_get_workshop_id_round_trip(self) -> None:
        self.provider.link("user-1", "workshop-1")
        self.assertEqual(self.provider.get_workshop_id("user-1"), "workshop-1")

    def test_get_is_following_default_true_when_unset(self) -> None:
        self.assertTrue(self.provider.get_is_following("user-1"))

    def test_get_is_following_default_true_when_profile_missing(self) -> None:
        # ドキュメント自体が存在しない(linkもset_is_followingも未呼び出し)場合も
        # InMemoryUserProfileStoreと同じくTrue(未フォロー状態は存在しない)。
        self.assertTrue(self.provider.get_is_following("unknown-user"))

    def test_set_is_following_then_get_round_trip(self) -> None:
        self.provider.set_is_following("user-1", False)
        self.assertFalse(self.provider.get_is_following("user-1"))
        self.provider.set_is_following("user-1", True)
        self.assertTrue(self.provider.get_is_following("user-1"))

    def test_link_does_not_clobber_is_following(self) -> None:
        self.provider.set_is_following("user-1", False)
        self.provider.link("user-1", "workshop-1")
        self.assertFalse(self.provider.get_is_following("user-1"))
        self.assertEqual(self.provider.get_workshop_id("user-1"), "workshop-1")

    def test_set_is_following_does_not_clobber_workshop_id(self) -> None:
        self.provider.link("user-1", "workshop-1")
        self.provider.set_is_following("user-1", False)
        self.assertEqual(self.provider.get_workshop_id("user-1"), "workshop-1")

    def test_users_are_independent(self) -> None:
        self.provider.link("user-1", "workshop-1")
        self.provider.set_is_following("user-2", False)
        self.assertIsNone(self.provider.get_workshop_id("user-2"))
        self.assertTrue(self.provider.get_is_following("user-1"))

    def test_get_workshop_id_fails_open_to_none_on_connection_error(self) -> None:
        provider = FirestoreUserProfileProvider(_RaisingFirestoreClient())
        self.assertIsNone(provider.get_workshop_id("user-1"))

    def test_get_is_following_fails_open_to_true_on_connection_error(self) -> None:
        provider = FirestoreUserProfileProvider(_RaisingFirestoreClient())
        self.assertTrue(provider.get_is_following("user-1"))


if __name__ == "__main__":
    unittest.main()
