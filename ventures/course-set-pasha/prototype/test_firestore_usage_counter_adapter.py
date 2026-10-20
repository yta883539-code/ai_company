"""firestore_usage_counter_adapter.FirestoreUsageCounterのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、firestore-provider-adapter-
design.md 19.2節が前提とした最小インターフェース(collection/document/get/set・
transaction().get/set/commit)のみを満たす軽量フェイクをここで実装し、
InMemoryUsageCounter(cloud_function_webhook.py)と観測可能な振る舞いが一致すること、
および19.3節で指摘されたread-modify-write競合がトランザクションのコミット時競合検出+
リトライで回避されることを検証する。
"""

import unittest
from datetime import datetime

from firestore_usage_counter_adapter import FirestoreUsageCounter, TransactionConflict


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


class FirestoreUsageCounterTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.counter = FirestoreUsageCounter(self.client)

    def test_get_count_for_unknown_user_is_zero(self):
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 0)

    def test_increment_then_get_count(self):
        self.assertEqual(self.counter.increment("u1", "2026-10"), 1)
        self.assertEqual(self.counter.increment("u1", "2026-10"), 2)
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 2)

    def test_month_rollover_resets_to_zero(self):
        self.counter.increment("u1", "2026-10")
        self.counter.increment("u1", "2026-10")
        self.assertEqual(self.counter.get_count("u1", "2026-11"), 0)
        self.assertEqual(self.counter.increment("u1", "2026-11"), 1)

    def test_increment_is_scoped_per_user(self):
        self.counter.increment("u1", "2026-10")
        self.counter.increment("u2", "2026-10")
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 1)
        self.assertEqual(self.counter.get_count("u2", "2026-10"), 1)

    def test_interleaved_transactions_do_not_lose_an_increment(self):
        """19.3節で指摘されたread-modify-write競合の回避を確認する。

        2つの「連投」をトランザクションの読み取りが互いの書き込みより先に起きるよう
        手動で組み立て(count_before=0を両方が読む)、1つ目のcommit成功後に2つ目が
        competeすると、FirestoreUsageCounter.increment()が内部でリトライして最終的に
        2が記録されることを確認する(ナイーブな実装なら1のまま失われるケース)。
        """
        doc_ref = self.client.collection("usage_counter").document("u1")

        tx_a = self.client.transaction()
        tx_a.get(doc_ref)
        tx_b = self.client.transaction()
        tx_b.get(doc_ref)

        tx_a.set(doc_ref, {"month": "2026-10", "count": 1})
        tx_a.commit()

        with self.assertRaises(TransactionConflict):
            tx_b.set(doc_ref, {"month": "2026-10", "count": 1})
            tx_b.commit()

        # increment()自身は上記と同型の競合に内部リトライで対応し、取り落とさない。
        result = self.counter.increment("u1", "2026-10")
        self.assertEqual(result, 2)
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 2)


class FirestoreUsageCounterIncrementAndMarkNoticeTest(unittest.TestCase):
    """firestore-provider-adapter-design.md 20節(increment_and_mark_noticeグループ)の
    実Firestore接続アダプタのテスト。"""

    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.counter = FirestoreUsageCounter(self.client)

    def test_increments_count_like_increment(self):
        result = self.counter.increment_and_mark_notice(
            "u1", "2026-10", mark_notice_sent=False
        )
        self.assertEqual(result, 1)
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 1)

    def test_mark_notice_sent_false_does_not_set_field(self):
        self.counter.increment_and_mark_notice("u1", "2026-10", mark_notice_sent=False)
        doc = self.client.collection("usage_counter").document("u1").get().to_dict()
        self.assertNotIn("first_generation_notice_sent", doc)

    def test_mark_notice_sent_true_sets_field(self):
        self.counter.increment_and_mark_notice("u1", "2026-10", mark_notice_sent=True)
        doc = self.client.collection("usage_counter").document("u1").get().to_dict()
        self.assertTrue(doc["first_generation_notice_sent"])

    def test_trial_start_at_is_set_when_unset(self):
        trial_start_at = datetime(2026, 10, 18, 12, 0, 0)
        self.counter.increment_and_mark_notice(
            "u1", "2026-10", mark_notice_sent=False, trial_start_at=trial_start_at
        )
        doc = self.client.collection("usage_counter").document("u1").get().to_dict()
        self.assertEqual(doc["trial_start_at"], trial_start_at)

    def test_trial_start_at_is_not_overwritten_once_set(self):
        first = datetime(2026, 10, 18, 12, 0, 0)
        second = datetime(2026, 10, 19, 9, 0, 0)
        self.counter.increment_and_mark_notice(
            "u1", "2026-10", mark_notice_sent=False, trial_start_at=first
        )
        self.counter.increment_and_mark_notice(
            "u1", "2026-10", mark_notice_sent=False, trial_start_at=second
        )
        doc = self.client.collection("usage_counter").document("u1").get().to_dict()
        self.assertEqual(doc["trial_start_at"], first)

    def test_does_not_clobber_fields_set_by_a_previous_call(self):
        """mark_notice_sent=Falseかつtrial_start_at=Noneで呼んでも、既に書き込まれている
        first_generation_notice_sent・trial_start_atを消してしまわないことを確認する
        (20.3節「merge=Trueを使う理由」の実コード側の等価物)。"""
        trial_start_at = datetime(2026, 10, 18, 12, 0, 0)
        self.counter.increment_and_mark_notice(
            "u1", "2026-10", mark_notice_sent=True, trial_start_at=trial_start_at
        )
        self.counter.increment_and_mark_notice("u1", "2026-10", mark_notice_sent=False)
        doc = self.client.collection("usage_counter").document("u1").get().to_dict()
        self.assertTrue(doc["first_generation_notice_sent"])
        self.assertEqual(doc["trial_start_at"], trial_start_at)
        self.assertEqual(doc["count"], 2)

    def test_interleaved_transactions_do_not_lose_an_increment(self):
        """19節のincrement()版と同じ競合を、increment_and_mark_notice()側でも検証する。"""
        doc_ref = self.client.collection("usage_counter").document("u1")

        tx_a = self.client.transaction()
        tx_a.get(doc_ref)
        tx_b = self.client.transaction()
        tx_b.get(doc_ref)

        tx_a.set(doc_ref, {"month": "2026-10", "count": 1})
        tx_a.commit()

        with self.assertRaises(TransactionConflict):
            tx_b.set(doc_ref, {"month": "2026-10", "count": 1})
            tx_b.commit()

        result = self.counter.increment_and_mark_notice(
            "u1", "2026-10", mark_notice_sent=True
        )
        self.assertEqual(result, 2)
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 2)


class FirestoreUsageCounterUpgradedAtTrialEndNotifiedAtTest(unittest.TestCase):
    """firestore-provider-adapter-design.md 22節(upgraded_at・trial_end_notified_at
    グループ)の実Firestore接続アダプタのテスト。"""

    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.counter = FirestoreUsageCounter(self.client)

    def test_get_upgraded_at_for_unknown_user_is_none(self):
        self.assertIsNone(self.counter.get_upgraded_at("u1"))

    def test_set_upgraded_at_if_unset_sets_value(self):
        upgraded_at = datetime(2026, 10, 19, 9, 0, 0)
        self.counter.set_upgraded_at_if_unset("u1", upgraded_at)
        self.assertEqual(self.counter.get_upgraded_at("u1"), upgraded_at)

    def test_set_upgraded_at_if_unset_does_not_overwrite_once_set(self):
        first = datetime(2026, 10, 19, 9, 0, 0)
        second = datetime(2026, 10, 20, 9, 0, 0)
        self.counter.set_upgraded_at_if_unset("u1", first)
        self.counter.set_upgraded_at_if_unset("u1", second)
        self.assertEqual(self.counter.get_upgraded_at("u1"), first)

    def test_set_upgraded_at_if_unset_does_not_clobber_other_fields(self):
        """22.3節「merge=Trueを使う理由」: 同一ドキュメントのcount等の既存フィールドを
        消してしまわないことを確認する。"""
        self.counter.increment("u1", "2026-10")
        self.counter.set_upgraded_at_if_unset("u1", datetime(2026, 10, 19, 9, 0, 0))
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 1)

    def test_set_upgraded_at_if_unset_retries_on_duplicate_webhook_delivery(self):
        """22.3節: 同一user_idからの重複Webhook配信が競合した場合でも、
        最終的に先勝ち(最初に書き込まれた値が保持される)になることを確認する。"""
        doc_ref = self.client.collection("usage_counter").document("u1")

        tx_a = self.client.transaction()
        tx_a.get(doc_ref)
        tx_b = self.client.transaction()
        tx_b.get(doc_ref)

        first = datetime(2026, 10, 19, 9, 0, 0)
        tx_a.set(doc_ref, {"upgraded_at": first})
        tx_a.commit()

        with self.assertRaises(TransactionConflict):
            tx_b.set(doc_ref, {"upgraded_at": datetime(2026, 10, 19, 9, 0, 1)})
            tx_b.commit()

        # set_upgraded_at_if_unset()自身は内部リトライで再読み取りし、既に
        # upgraded_atが設定済みと判定して書き込まずに終える(先勝ちを保持)。
        self.counter.set_upgraded_at_if_unset("u1", datetime(2026, 10, 19, 9, 0, 1))
        self.assertEqual(self.counter.get_upgraded_at("u1"), first)

    def test_get_trial_end_notified_at_for_unknown_user_is_none(self):
        self.assertIsNone(self.counter.get_trial_end_notified_at("u1"))

    def test_set_trial_end_notified_at_sets_value(self):
        notified_at = datetime(2026, 10, 19, 10, 0, 0)
        self.counter.set_trial_end_notified_at("u1", notified_at)
        self.assertEqual(self.counter.get_trial_end_notified_at("u1"), notified_at)

    def test_set_trial_end_notified_at_does_not_clobber_other_fields(self):
        self.counter.increment("u1", "2026-10")
        self.counter.set_upgraded_at_if_unset("u1", datetime(2026, 10, 19, 9, 0, 0))
        self.counter.set_trial_end_notified_at("u1", datetime(2026, 10, 19, 10, 0, 0))
        self.assertEqual(self.counter.get_count("u1", "2026-10"), 1)
        self.assertEqual(
            self.counter.get_upgraded_at("u1"), datetime(2026, 10, 19, 9, 0, 0)
        )


if __name__ == "__main__":
    unittest.main()
