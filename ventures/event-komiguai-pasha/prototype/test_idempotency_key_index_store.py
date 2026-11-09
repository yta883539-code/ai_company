"""idempotency_key_index_store.InMemoryIdempotencyKeyIndexStoreのテスト。"""

import unittest
from datetime import datetime, timedelta, timezone

from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore


class InMemoryIdempotencyKeyIndexStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryIdempotencyKeyIndexStore()
        self.now = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)

    def test_first_call_reserves_and_returns_same_document_id(self):
        result = self.store.reserve_or_get(
            "idem-1",
            collection="one_time_draft",
            document_id="draft-aaaa",
            created_at=self.now,
        )
        self.assertEqual(result, "draft-aaaa")

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
            created_at=self.now + timedelta(seconds=1),
        )
        self.assertEqual(result, "draft-aaaa")

    def test_distinct_keys_are_independent(self):
        first = self.store.reserve_or_get(
            "idem-1",
            collection="one_time_draft",
            document_id="draft-aaaa",
            created_at=self.now,
        )
        second = self.store.reserve_or_get(
            "idem-2",
            collection="one_time_draft",
            document_id="draft-bbbb",
            created_at=self.now,
        )
        self.assertEqual(first, "draft-aaaa")
        self.assertEqual(second, "draft-bbbb")

    def test_inquiry_collection_without_expire_at_is_stored(self):
        self.store.reserve_or_get(
            "idem-3",
            collection="inquiry",
            document_id="inquiry-cccc",
            created_at=self.now,
        )
        entry = self.store._entries["idem-3"]
        self.assertEqual(entry.collection, "inquiry")
        self.assertIsNone(entry.expire_at)

    def test_one_time_draft_collection_with_expire_at_is_stored(self):
        expire_at = self.now + timedelta(hours=24)
        self.store.reserve_or_get(
            "idem-4",
            collection="one_time_draft",
            document_id="draft-dddd",
            created_at=self.now,
            expire_at=expire_at,
        )
        entry = self.store._entries["idem-4"]
        self.assertEqual(entry.expire_at, expire_at)


if __name__ == "__main__":
    unittest.main()
