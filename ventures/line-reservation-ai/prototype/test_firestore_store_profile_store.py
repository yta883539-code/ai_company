"""firestore_store_profile_store.FirestoreStoreProfileStoreのテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、store-profile-store-
firestore-adapter-design.md 2節・7節が前提とした最小インターフェース
(collection/document/get/set/batch)のみを満たす軽量フェイクをここで実装し、
InMemoryStoreProfileStore(store_profile_store.py)と観測可能な振る舞いが
一致することを検証する。
"""

import unittest

from firestore_store_profile_store import FirestoreStoreProfileStore
from store_profile_store import PLAN_MONTHLY_BOOKING_LIMITS


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

    def delete(self) -> None:
        self._store.pop(self._doc_id, None)


class _FakeDocumentSnapshot:
    def __init__(self, doc_id: str, data: dict):
        self.id = doc_id
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)

    def stream(self):
        # 26節: 実Firestoreのstream()はドキュメントID順を保証しないため、
        # フェイクでもテストで列挙順に依存しないことを確認しやすいよう
        # dict挿入順のまま返す(昇順ソート等はしない)。
        for doc_id, data in self._store.items():
            yield _FakeDocumentSnapshot(doc_id, data)


class _FakeBatch:
    def __init__(self):
        self._ops = []

    def set(self, doc_ref: _FakeDocumentRef, data: dict, merge: bool = False) -> None:
        self._ops.append(("set", doc_ref, data, merge))

    def delete(self, doc_ref: _FakeDocumentRef) -> None:
        self._ops.append(("delete", doc_ref))

    def commit(self) -> None:
        for op in self._ops:
            if op[0] == "set":
                _, doc_ref, data, merge = op
                doc_ref.set(data, merge=merge)
            else:
                _, doc_ref = op
                doc_ref.delete()
        self._ops = []


class _FakeFirestoreClient:
    def __init__(self):
        self._collections: dict[str, dict] = {}

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections.setdefault(name, {}))

    def batch(self) -> _FakeBatch:
        return _FakeBatch()

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

    def batch(self):
        raise AssertionError("batch() should not be called when reads fail")


class FirestoreStoreProfileStoreStripeGroupTest(unittest.TestCase):
    def test_get_stripe_customer_id_returns_none_when_document_missing(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        self.assertIsNone(store.get_stripe_customer_id("store-1"))

    def test_set_then_get_stripe_customer_id_round_trips(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        store.set_stripe_customer_id("store-1", "cus_abc")

        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_abc")

    def test_set_stripe_customer_id_writes_reverse_index(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        store.set_stripe_customer_id("store-1", "cus_abc")

        self.assertEqual(store.get_store_id_by_stripe_customer_id("cus_abc"), "store-1")

    def test_set_stripe_customer_id_replacement_deletes_old_reverse_index(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        store.set_stripe_customer_id("store-1", "cus_old")

        store.set_stripe_customer_id("store-1", "cus_new")

        self.assertIsNone(store.get_store_id_by_stripe_customer_id("cus_old"))
        self.assertEqual(store.get_store_id_by_stripe_customer_id("cus_new"), "store-1")

    def test_set_stripe_customer_id_same_value_keeps_reverse_index(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        store.set_stripe_customer_id("store-1", "cus_abc")

        store.set_stripe_customer_id("store-1", "cus_abc")

        self.assertEqual(store.get_store_id_by_stripe_customer_id("cus_abc"), "store-1")

    def test_set_stripe_customer_id_rejects_empty_user_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_stripe_customer_id("", "cus_abc")

    def test_set_stripe_customer_id_rejects_empty_stripe_customer_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_stripe_customer_id("store-1", "")

    def test_get_stripe_customer_id_falls_back_to_none_on_client_exception(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertIsNone(store.get_stripe_customer_id("store-1"))

    def test_get_store_id_by_stripe_customer_id_falls_back_to_none_on_exception(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertIsNone(store.get_store_id_by_stripe_customer_id("cus_abc"))


class FirestoreStoreProfileStoreOwnerIsFollowingGroupTest(unittest.TestCase):
    def test_get_owner_is_following_defaults_to_true_when_document_missing(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        self.assertTrue(store.get_owner_is_following("store-1"))

    def test_get_owner_is_following_defaults_to_true_when_field_unset(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"stripeCustomerId": "cus_abc"})
        store = FirestoreStoreProfileStore(client)

        self.assertTrue(store.get_owner_is_following("store-1"))

    def test_set_then_get_owner_is_following_round_trips_false(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        store.set_owner_is_following("store-1", False)

        self.assertFalse(store.get_owner_is_following("store-1"))

    def test_set_then_get_owner_is_following_round_trips_true(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        store.set_owner_is_following("store-1", False)

        store.set_owner_is_following("store-1", True)

        self.assertTrue(store.get_owner_is_following("store-1"))

    def test_set_owner_is_following_preserves_other_fields(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"stripeCustomerId": "cus_abc"})
        store = FirestoreStoreProfileStore(client)

        store.set_owner_is_following("store-1", False)

        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_abc")

    def test_set_owner_is_following_rejects_empty_store_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_owner_is_following("", True)

    def test_get_owner_is_following_falls_back_to_true_on_client_exception(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertTrue(store.get_owner_is_following("store-1"))


class FirestoreStoreProfileStoreOwnerUserIdGroupTest(unittest.TestCase):
    def test_get_owner_user_id_returns_none_when_document_missing(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        self.assertIsNone(store.get_owner_user_id("store-1"))

    def test_set_then_get_owner_user_id_round_trips(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        store.set_owner_user_id("store-1", "U_owner_abc")

        self.assertEqual(store.get_owner_user_id("store-1"), "U_owner_abc")

    def test_set_owner_user_id_preserves_other_fields(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"stripeCustomerId": "cus_abc"})
        store = FirestoreStoreProfileStore(client)

        store.set_owner_user_id("store-1", "U_owner_abc")

        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_abc")

    def test_set_owner_user_id_rejects_empty_store_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_owner_user_id("", "U_owner_abc")

    def test_set_owner_user_id_rejects_empty_owner_user_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_owner_user_id("store-1", "")

    def test_get_owner_user_id_falls_back_to_none_on_client_exception(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertIsNone(store.get_owner_user_id("store-1"))


class FirestoreStoreProfileStoreSuspensionReasonGroupTest(unittest.TestCase):
    def test_get_suspension_reason_returns_none_when_document_missing(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        self.assertIsNone(store.get_suspension_reason("store-1"))

    def test_set_then_get_suspension_reason_round_trips(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        store.set_suspension_reason("store-1", "payment_failed")

        self.assertEqual(store.get_suspension_reason("store-1"), "payment_failed")

    def test_set_suspension_reason_can_clear_back_to_none(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        store.set_suspension_reason("store-1", "payment_failed")

        store.set_suspension_reason("store-1", None)

        self.assertIsNone(store.get_suspension_reason("store-1"))

    def test_set_suspension_reason_preserves_other_fields(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"stripeCustomerId": "cus_abc"})
        store = FirestoreStoreProfileStore(client)

        store.set_suspension_reason("store-1", "payment_failed")

        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_abc")

    def test_set_suspension_reason_rejects_empty_store_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_suspension_reason("", "payment_failed")

    def test_get_suspension_reason_falls_back_to_none_on_client_exception(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertIsNone(store.get_suspension_reason("store-1"))


class FirestoreStoreProfileStoreOwnerEmailGroupTest(unittest.TestCase):
    def test_get_owner_email_returns_none_when_document_missing(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        self.assertIsNone(store.get_owner_email("store-1"))

    def test_set_then_get_owner_email_round_trips(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        store.set_owner_email("store-1", "owner@example.com")

        self.assertEqual(store.get_owner_email("store-1"), "owner@example.com")

    def test_set_owner_email_preserves_other_fields(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"stripeCustomerId": "cus_abc"})
        store = FirestoreStoreProfileStore(client)

        store.set_owner_email("store-1", "owner@example.com")

        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_abc")

    def test_set_owner_email_rejects_empty_store_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_owner_email("", "owner@example.com")

    def test_set_owner_email_rejects_empty_owner_email(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_owner_email("store-1", "")

    def test_get_owner_email_falls_back_to_none_on_client_exception(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertIsNone(store.get_owner_email("store-1"))


class FirestoreStoreProfileStoreBlockedButBillingOwnerNotifiedAtGroupTest(
    unittest.TestCase
):
    def test_get_blocked_but_billing_owner_notified_at_returns_none_when_document_missing(
        self,
    ):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        self.assertIsNone(
            store.get_blocked_but_billing_owner_notified_at("store-1")
        )

    def test_set_then_get_blocked_but_billing_owner_notified_at_round_trips(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)

        store.set_blocked_but_billing_owner_notified_at(
            "store-1", "2026-10-25T10:00:00Z"
        )

        self.assertEqual(
            store.get_blocked_but_billing_owner_notified_at("store-1"),
            "2026-10-25T10:00:00Z",
        )

    def test_set_blocked_but_billing_owner_notified_at_can_clear_back_to_none(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        store.set_blocked_but_billing_owner_notified_at(
            "store-1", "2026-10-25T10:00:00Z"
        )

        store.set_blocked_but_billing_owner_notified_at("store-1", None)

        self.assertIsNone(
            store.get_blocked_but_billing_owner_notified_at("store-1")
        )

    def test_set_blocked_but_billing_owner_notified_at_preserves_other_fields(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"stripeCustomerId": "cus_abc"})
        store = FirestoreStoreProfileStore(client)

        store.set_blocked_but_billing_owner_notified_at(
            "store-1", "2026-10-25T10:00:00Z"
        )

        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_abc")

    def test_set_blocked_but_billing_owner_notified_at_rejects_empty_store_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_blocked_but_billing_owner_notified_at(
                "", "2026-10-25T10:00:00Z"
            )

    def test_get_blocked_but_billing_owner_notified_at_falls_back_to_none_on_client_exception(
        self,
    ):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertIsNone(
            store.get_blocked_but_billing_owner_notified_at("store-1")
        )


class FirestoreStoreProfileStorePlanGroupTest(unittest.TestCase):
    def test_get_plan_returns_none_when_document_missing(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        self.assertIsNone(store.get_plan("store-1"))

    def test_set_then_get_plan_round_trips(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        plan = next(iter(PLAN_MONTHLY_BOOKING_LIMITS))

        store.set_plan("store-1", plan)

        self.assertEqual(store.get_plan("store-1"), plan)

    def test_set_plan_preserves_other_fields(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"stripeCustomerId": "cus_abc"})
        store = FirestoreStoreProfileStore(client)
        plan = next(iter(PLAN_MONTHLY_BOOKING_LIMITS))

        store.set_plan("store-1", plan)

        self.assertEqual(store.get_stripe_customer_id("store-1"), "cus_abc")

    def test_set_plan_rejects_empty_store_id(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())
        plan = next(iter(PLAN_MONTHLY_BOOKING_LIMITS))

        with self.assertRaises(ValueError):
            store.set_plan("", plan)

    def test_set_plan_rejects_unknown_plan_name(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_plan("store-1", "存在しないプラン")

    def test_set_plan_rejects_unknown_plan_without_touching_client(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        with self.assertRaises(ValueError):
            store.set_plan("store-1", "存在しないプラン")

    def test_get_plan_falls_back_to_none_on_client_exception(self):
        store = FirestoreStoreProfileStore(_RaisingFirestoreClient())

        self.assertIsNone(store.get_plan("store-1"))


class FirestoreStoreProfileStoreAllStoreIdsGroupTest(unittest.TestCase):
    def test_all_store_ids_returns_empty_when_no_stores(self):
        store = FirestoreStoreProfileStore(_FakeFirestoreClient())

        self.assertEqual(list(store.all_store_ids()), [])

    def test_all_store_ids_returns_every_seeded_store_id(self):
        client = _FakeFirestoreClient()
        client.seed_store("store-1", {"plan": "standard"})
        client.seed_store("store-2", {"plan": "basic"})
        store = FirestoreStoreProfileStore(client)

        self.assertEqual(set(store.all_store_ids()), {"store-1", "store-2"})

    def test_all_store_ids_reflects_stores_created_via_setters(self):
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        store.set_owner_is_following("store-3", True)

        self.assertEqual(list(store.all_store_ids()), ["store-3"])

    def test_all_store_ids_does_not_include_stripe_customer_index_entries(self):
        # stripe_customer_index/{stripeCustomerId}は逆引き専用の別コレクションであり、
        # 「stores」コレクションのみを走査するall_store_ids()には含まれない。
        client = _FakeFirestoreClient()
        store = FirestoreStoreProfileStore(client)
        store.set_stripe_customer_id("store-1", "cus_abc")

        self.assertEqual(list(store.all_store_ids()), ["store-1"])


if __name__ == "__main__":
    unittest.main()
