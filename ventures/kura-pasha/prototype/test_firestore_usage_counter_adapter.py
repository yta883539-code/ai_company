"""firestore_usage_counter_adapter.FirestoreUsageCounterProviderのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、firestore-usage-counter-
provider-adapter-design.md 2節が前提とした最小インターフェース(collection/document/
get/set・transaction().get/set/commit)のみを満たす軽量フェイクをここで実装し、
InMemoryUsageCounterStore(usage_counter_workshop.py)と観測可能な振る舞いが一致すること、
design.md 3節で指摘されたread-modify-write競合がトランザクションのコミット時競合検出+
リトライで回避されること、design.md 5節で確定したfail-open方針(最大試行回数超過時は
1を返す)を検証する。
"""

import unittest

from firestore_usage_counter_adapter import (
    FirestoreUsageCounterProvider,
    TransactionConflict,
)


class _FakeSnapshot:
    def __init__(self, exists: bool, data: dict | None):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return self._data


class _FakeDocumentRef:
    def __init__(self, store: dict, versions: dict, key):
        self._store = store
        self._versions = versions
        self._key = key

    def get(self):
        data = self._store.get(self._key)
        return _FakeSnapshot(exists=data is not None, data=dict(data) if data else None)

    def set(self, data: dict) -> None:
        self._store[self._key] = dict(data)
        self._versions[self._key] = self._versions.get(self._key, 0) + 1


class _FakeCollection:
    def __init__(self, store: dict, versions: dict):
        self._store = store
        self._versions = versions

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, self._versions, doc_id)


class _FakeTransaction:
    """読み取り時点のバージョンをコミット時にチェックし、他のトランザクションが先に
    書き込んでいた場合はTransactionConflictを送出する、楽観的並行性制御のフェイク
    (実Firestoreのトランザクション競合検出の簡易モデル)。
    """

    def __init__(self, store: dict, versions: dict):
        self._store = store
        self._versions = versions
        self._read_versions: dict = {}
        self._pending_writes: list[tuple[str, dict]] = []

    def get(self, doc_ref: _FakeDocumentRef) -> _FakeSnapshot:
        key = doc_ref._key
        self._read_versions[key] = self._versions.get(key, 0)
        return doc_ref.get()

    def set(self, doc_ref: _FakeDocumentRef, data: dict) -> None:
        self._pending_writes.append((doc_ref._key, dict(data)))

    def commit(self) -> None:
        for key, seen_version in self._read_versions.items():
            if self._versions.get(key, 0) != seen_version:
                raise TransactionConflict(f"document {key!r} changed since read")
        for key, data in self._pending_writes:
            self._store[key] = data
            self._versions[key] = self._versions.get(key, 0) + 1


class _FakeFirestoreClient:
    def __init__(self):
        self._store: dict = {}
        self._versions: dict = {}

    def collection(self, name: str) -> _FakeCollection:
        assert name == "usage_counter"
        return _FakeCollection(self._store, self._versions)

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self._store, self._versions)


class FirestoreUsageCounterProviderTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.provider = FirestoreUsageCounterProvider(self.client)

    def test_get_for_unknown_workshop_is_none(self):
        self.assertIsNone(self.provider.get("w1"))

    def test_set_then_get_roundtrip(self):
        self.provider.set("w1", "2026-10", 3)
        self.assertEqual(self.provider.get("w1"), ("2026-10", 3))

    def test_increment_or_reset_accumulates_within_same_month(self):
        self.assertEqual(self.provider.increment_or_reset("w1", "2026-10"), 1)
        self.assertEqual(self.provider.increment_or_reset("w1", "2026-10"), 2)
        self.assertEqual(self.provider.get("w1"), ("2026-10", 2))

    def test_increment_or_reset_resets_on_month_change(self):
        self.provider.increment_or_reset("w1", "2026-10")
        self.provider.increment_or_reset("w1", "2026-10")
        self.assertEqual(self.provider.increment_or_reset("w1", "2026-11"), 1)
        self.assertEqual(self.provider.get("w1"), ("2026-11", 1))

    def test_increment_or_reset_is_scoped_per_workshop(self):
        self.provider.increment_or_reset("w1", "2026-10")
        self.provider.increment_or_reset("w2", "2026-10")
        self.assertEqual(self.provider.get("w1"), ("2026-10", 1))
        self.assertEqual(self.provider.get("w2"), ("2026-10", 1))

    def test_interleaved_transactions_do_not_lose_an_increment(self):
        """design.md 3節で指摘されたread-modify-write競合の回避を確認する。

        2つの「連投」をトランザクションの読み取りが互いの書き込みより先に起きるよう
        手動で組み立て(count_before=0を両方が読む)、1つ目のcommit成功後に2つ目が
        競合すると、increment_or_reset()が内部でリトライして最終的に2が記録される
        ことを確認する(ナイーブな実装なら1のまま失われるケース)。
        """
        doc_ref = self.client.collection("usage_counter").document("w1")

        tx_a = self.client.transaction()
        tx_a.get(doc_ref)
        tx_b = self.client.transaction()
        tx_b.get(doc_ref)

        tx_a.set(doc_ref, {"month": "2026-10", "count": 1})
        tx_a.commit()

        with self.assertRaises(TransactionConflict):
            tx_b.set(doc_ref, {"month": "2026-10", "count": 1})
            tx_b.commit()

        result = self.provider.increment_or_reset("w1", "2026-10")
        self.assertEqual(result, 2)
        self.assertEqual(self.provider.get("w1"), ("2026-10", 2))

    def test_increment_or_reset_fails_open_when_commit_always_conflicts(self):
        """design.md 5節(フェーズ226)で確定したfail-open方針: 最大試行回数を超えて
        コミットできない場合は例外を伝播させず、当月初回利用として1を返す。
        """

        class _AlwaysConflictingTransaction(_FakeTransaction):
            def commit(self) -> None:
                raise TransactionConflict("simulated persistent conflict")

        class _AlwaysConflictingClient(_FakeFirestoreClient):
            def transaction(self) -> _FakeTransaction:
                return _AlwaysConflictingTransaction(self._store, self._versions)

        provider = FirestoreUsageCounterProvider(_AlwaysConflictingClient())
        self.assertEqual(provider.increment_or_reset("w1", "2026-10"), 1)


if __name__ == "__main__":
    unittest.main()
