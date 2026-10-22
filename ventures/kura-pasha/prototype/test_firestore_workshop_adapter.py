"""firestore_workshop_adapter.FirestoreWorkshopStore(基盤グループ)のテスト。

本物のgoogle-cloud-firestore SDKへは接続しない(pending-approval.md記載の通り実
Firestoreプロジェクト自体がオーナー承認待ち)。代わりに、workshop-store-firestore-
adapter-design.md 2節が前提とした最小インターフェース(collection/document/get/
set/update・collection.stream())のみを満たす軽量フェイクをここで実装し、
InMemoryWorkshopStore(usage_counter_workshop.py)の基盤グループと観測可能な
振る舞いが一致することを検証する。
"""

import unittest
from datetime import datetime, timezone

from firestore_workshop_adapter import ArrayUnion, FirestoreWorkshopStore
from usage_counter_workshop import InvalidSubscriptionStatusError, PendingContractorTransfer


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

    def set(self, data: dict, merge: bool = False) -> None:
        if merge and self._doc_id in self._store:
            self._store[self._doc_id].update(data)
        else:
            self._store[self._doc_id] = dict(data)

    def update(self, data: dict) -> None:
        # design.md 2節`add_member_user_id`相当: ArrayUnionセンチネルを認識して
        # 重複排除しながらマージする(実Firestoreサーバー側の挙動を模す)。
        existing = self._store.setdefault(self._doc_id, {})
        for key, value in data.items():
            if isinstance(value, ArrayUnion):
                current = list(existing.get(key, []))
                for item in value.values:
                    if item not in current:
                        current.append(item)
                existing[key] = current
            else:
                existing[key] = value

    def delete(self) -> None:
        self._store.pop(self._doc_id, None)


class _FakeCollection:
    def __init__(self, store: dict):
        self._store = store

    def document(self, doc_id: str) -> _FakeDocumentRef:
        return _FakeDocumentRef(self._store, doc_id)

    def stream(self):
        return [
            _FakeSnapshot(doc_id, exists=True, data=dict(data))
            for doc_id, data in self._store.items()
        ]


class _FakeBatch:
    """design.md 11節`set_stripe_customer_id`のWriteBatch呼び出しを模す最小実装
    (aircon-pasha test_firestore_user_profile_adapter.py `_FakeBatch`と同型、
    `delete`呼び出し〈design.md 11.1節・25節の旧インデックス削除〉への対応を追加)。
    """

    def __init__(self):
        self._writes: list[tuple] = []

    def set(self, doc_ref: _FakeDocumentRef, data: dict, merge: bool = False) -> None:
        self._writes.append(("set", doc_ref, data, merge))

    def delete(self, doc_ref: _FakeDocumentRef) -> None:
        self._writes.append(("delete", doc_ref, None, None))

    def commit(self) -> None:
        for kind, doc_ref, data, merge in self._writes:
            if kind == "set":
                doc_ref.set(data, merge=merge)
            else:
                doc_ref.delete()
        self._writes = []


class _FakeFirestoreClient:
    def __init__(self):
        self._collections: dict[str, dict] = {
            "craftsman_workshop": {},
            "stripe_customer_index": {},
        }

    def collection(self, name: str) -> _FakeCollection:
        return _FakeCollection(self._collections[name])

    def batch(self) -> _FakeBatch:
        return _FakeBatch()


class FirestoreWorkshopStoreTest(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()
        self.store = FirestoreWorkshopStore(self.client)

    def test_set_members_then_get_contractor_and_member_ids(self):
        self.store.set_members("w1", "U_owner", ["U_member1"], {"U_owner": "親方太郎"})
        self.assertEqual(self.store.get_contractor_user_id("w1"), "U_owner")
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])
        self.assertEqual(self.store.get_member_display_name("w1", "U_owner"), "親方太郎")

    def test_set_members_deduplicates_contractor_from_member_list(self):
        # 契約者自身がmember_user_idsにも含まれていても1件のみ(InMemory実装と同じ挙動)。
        self.store.set_members("w1", "U_owner", ["U_owner", "U_member1"])
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])

    def test_set_contractor_user_id_overwrites(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_contractor_user_id("w1", "U_new_owner")
        self.assertEqual(self.store.get_contractor_user_id("w1"), "U_new_owner")

    def test_get_contractor_user_id_for_unknown_workshop_raises(self):
        # design.md 23.3節: fail-closed(安全側デフォルトに合流させず例外を伝播させる)。
        with self.assertRaises(KeyError):
            self.store.get_contractor_user_id("unknown")

    def test_get_plan_id_for_unknown_workshop_raises(self):
        with self.assertRaises(KeyError):
            self.store.get_plan_id("unknown")

    def test_get_member_user_ids_for_unknown_workshop_is_empty(self):
        self.assertEqual(self.store.get_member_user_ids("unknown"), [])

    def test_add_member_user_id_appends_new_member(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.add_member_user_id("w1", "U_member2")
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member2"])

    def test_add_member_user_id_is_idempotent(self):
        # ArrayUnionと同じ重複排除契約(design.md 2節・3節の検討事項)。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.add_member_user_id("w1", "U_member1")
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])

    def test_get_member_display_name_for_unknown_user_is_none(self):
        self.store.set_members("w1", "U_owner", [], {"U_owner": "親方太郎"})
        self.assertIsNone(self.store.get_member_display_name("w1", "U_unknown"))

    def test_set_plan_then_get_plan_id(self):
        self.store.set_plan("w1", "standard")
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    def test_workshop_name_roundtrip_and_default_none(self):
        self.assertIsNone(self.store.get_workshop_name("w1"))
        self.store.set_workshop_name("w1", "鍛治屋 寅吉")
        self.assertEqual(self.store.get_workshop_name("w1"), "鍛治屋 寅吉")

    def test_first_generation_notice_sent_roundtrip_and_default_false(self):
        self.assertFalse(self.store.get_first_generation_notice_sent("w1"))
        self.store.set_first_generation_notice_sent("w1")
        self.assertTrue(self.store.get_first_generation_notice_sent("w1"))

    def test_all_workshop_ids_lists_created_workshops(self):
        self.store.set_members("w1", "U_owner1", [])
        self.store.set_members("w2", "U_owner2", [])
        self.assertEqual(sorted(self.store.all_workshop_ids()), ["w1", "w2"])

    def test_fields_do_not_clobber_each_other_via_merge(self):
        # merge=Trueによる部分更新方針(design.md 2節・27節)の確認: 異なるタイミングで
        # 書き込まれる複数フィールドが、互いの値を消さずに共存できること。
        self.store.set_members("w1", "U_owner", ["U_member1"], {"U_owner": "親方太郎"})
        self.store.set_plan("w1", "light")
        self.store.set_workshop_name("w1", "鍛治屋 寅吉")
        self.store.set_first_generation_notice_sent("w1")

        self.assertEqual(self.store.get_contractor_user_id("w1"), "U_owner")
        self.assertEqual(self.store.get_plan_id("w1"), "light")
        self.assertEqual(self.store.get_workshop_name("w1"), "鍛治屋 寅吉")
        self.assertTrue(self.store.get_first_generation_notice_sent("w1"))
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner", "U_member1"])

    def test_pending_reduction_effective_at_roundtrip_and_default_none(self):
        self.assertIsNone(self.store.get_pending_reduction_effective_at("w1"))
        effective_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
        self.store.set_pending_reduction_effective_at("w1", effective_at)
        self.assertEqual(self.store.get_pending_reduction_effective_at("w1"), effective_at)

    def test_specified_retention_member_name_roundtrip_and_default_none(self):
        self.assertIsNone(self.store.get_specified_retention_member_name("w1"))
        self.store.set_specified_retention_member_name("w1", "U_member1")
        self.assertEqual(self.store.get_specified_retention_member_name("w1"), "U_member1")

    def test_apply_member_reduction_replaces_member_ids(self):
        self.store.set_members("w1", "U_owner", ["U_member1", "U_member2"])
        self.store.apply_member_reduction("w1", ["U_owner"])
        self.assertEqual(self.store.get_member_user_ids("w1"), ["U_owner"])

    def test_apply_member_reduction_clears_pending_effective_at_and_retention_name(self):
        # フェーズ223(design.md 19節)の確定仕様: サイクル1回限りの入力として両方クリアする。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_pending_reduction_effective_at(
            "w1", datetime(2026, 11, 1, tzinfo=timezone.utc)
        )
        self.store.set_specified_retention_member_name("w1", "U_member1")

        self.store.apply_member_reduction("w1", ["U_owner"])

        self.assertIsNone(self.store.get_pending_reduction_effective_at("w1"))
        self.assertIsNone(self.store.get_specified_retention_member_name("w1"))

    def test_apply_member_reduction_does_not_clobber_unrelated_fields(self):
        # merge=True方針(design.md 2節・27節)の確認: plan_id等の無関係フィールドは消えない。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_plan("w1", "standard")
        self.store.apply_member_reduction("w1", ["U_owner"])
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    # --- design.md 7節: 契約者引き継ぎ系グループ(pending_contractor_transfer) ---

    def test_pending_contractor_transfer_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_pending_contractor_transfer("w1"))

    def test_pending_contractor_transfer_roundtrip(self):
        self.store.set_members("w1", "U_owner", ["U_member1"])
        pending = PendingContractorTransfer(
            candidate_user_id="U_member1",
            candidate_member_name="弟子次郎",
            requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
            expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
        )
        self.store.set_pending_contractor_transfer("w1", pending)

        result = self.store.get_pending_contractor_transfer("w1")
        self.assertEqual(result, pending)

    def test_clear_pending_contractor_transfer_resets_to_none(self):
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_pending_contractor_transfer(
            "w1",
            PendingContractorTransfer(
                candidate_user_id="U_member1",
                candidate_member_name="弟子次郎",
                requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
            ),
        )
        self.store.clear_pending_contractor_transfer("w1")
        self.assertIsNone(self.store.get_pending_contractor_transfer("w1"))

    def test_set_pending_contractor_transfer_does_not_clobber_unrelated_fields(self):
        # merge=True方針(design.md 2節・27節)の確認: plan_id等の無関係フィールドは消えない。
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_plan("w1", "standard")
        self.store.set_pending_contractor_transfer(
            "w1",
            PendingContractorTransfer(
                candidate_user_id="U_member1",
                candidate_member_name="弟子次郎",
                requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
            ),
        )
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    def test_clear_pending_contractor_transfer_does_not_clobber_unrelated_fields(self):
        self.store.set_members("w1", "U_owner", ["U_member1"])
        self.store.set_plan("w1", "standard")
        self.store.set_pending_contractor_transfer(
            "w1",
            PendingContractorTransfer(
                candidate_user_id="U_member1",
                candidate_member_name="弟子次郎",
                requested_at=datetime(2026, 10, 20, 21, 0, tzinfo=timezone.utc),
                expires_at=datetime(2026, 10, 27, 21, 0, tzinfo=timezone.utc),
            ),
        )
        self.store.clear_pending_contractor_transfer("w1")
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    # --- design.md 9節: trial系グループ(trial_start_at・trial_generation_used) ---

    def test_get_trial_start_at_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_trial_start_at("w1"))

    def test_trial_start_at_roundtrip(self):
        self.store.set_members("w1", "U_owner", [])
        trial_start_at = datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc)
        self.store.set_trial_start_at("w1", trial_start_at)
        self.assertEqual(self.store.get_trial_start_at("w1"), trial_start_at)

    def test_get_trial_generation_used_default_false(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertFalse(self.store.get_trial_generation_used("w1"))

    def test_trial_generation_used_roundtrip(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_trial_generation_used("w1")
        self.assertTrue(self.store.get_trial_generation_used("w1"))

    def test_set_trial_generation_used_explicit_value(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_trial_generation_used("w1", used=True)
        self.assertTrue(self.store.get_trial_generation_used("w1"))

    def test_trial_fields_do_not_clobber_unrelated_fields(self):
        # merge=True方針(design.md 2節・27節)の確認: plan_id等の無関係フィールドは消えない。
        self.store.set_members("w1", "U_owner", [])
        self.store.set_plan("w1", "standard")
        self.store.set_trial_start_at("w1", datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc))
        self.store.set_trial_generation_used("w1")
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    def test_trial_start_at_and_generation_used_are_independent(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_trial_start_at("w1", datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc))
        self.assertFalse(self.store.get_trial_generation_used("w1"))
        self.store.set_trial_generation_used("w1")
        self.assertEqual(
            self.store.get_trial_start_at("w1"),
            datetime(2026, 10, 21, 3, 0, tzinfo=timezone.utc),
        )

    # --- design.md 11節: stripe_customer_id順引き逆引き系グループ ---

    def test_get_stripe_customer_id_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_stripe_customer_id("w1"))

    def test_set_stripe_customer_id_roundtrip(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_stripe_customer_id("w1", "cus_abc")
        self.assertEqual(self.store.get_stripe_customer_id("w1"), "cus_abc")

    def test_set_stripe_customer_id_enables_reverse_lookup(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_stripe_customer_id("w1", "cus_abc")
        self.assertEqual(
            self.store.get_workshop_id_by_stripe_customer_id("cus_abc"), "w1"
        )

    def test_get_workshop_id_by_stripe_customer_id_unknown_is_none(self):
        self.assertIsNone(self.store.get_workshop_id_by_stripe_customer_id("cus_unknown"))

    def test_set_stripe_customer_id_does_not_clobber_unrelated_fields(self):
        # merge=True方針(design.md 2節・27節)の確認: plan_id等の無関係フィールドは消えない。
        self.store.set_members("w1", "U_owner", [])
        self.store.set_plan("w1", "standard")
        self.store.set_stripe_customer_id("w1", "cus_abc")
        self.assertEqual(self.store.get_plan_id("w1"), "standard")

    def test_set_stripe_customer_id_reassignment_removes_old_reverse_index(self):
        # design.md 11.1節(21節・25節追記): 付け替え時はInMemoryWorkshopStoreの挙動
        # (design.md 21節)と対称に、旧stripe_customer_idの逆引きエントリを削除する。
        self.store.set_members("w1", "U_owner", [])
        self.store.set_stripe_customer_id("w1", "cus_old")
        self.store.set_stripe_customer_id("w1", "cus_new")

        self.assertIsNone(self.store.get_workshop_id_by_stripe_customer_id("cus_old"))
        self.assertEqual(
            self.store.get_workshop_id_by_stripe_customer_id("cus_new"), "w1"
        )
        self.assertEqual(self.store.get_stripe_customer_id("w1"), "cus_new")

    def test_set_stripe_customer_id_same_value_again_keeps_reverse_index(self):
        # 同一値での再設定(冪等呼び出し)では旧エントリ削除分岐に入らないことを確認する。
        self.store.set_members("w1", "U_owner", [])
        self.store.set_stripe_customer_id("w1", "cus_abc")
        self.store.set_stripe_customer_id("w1", "cus_abc")

        self.assertEqual(
            self.store.get_workshop_id_by_stripe_customer_id("cus_abc"), "w1"
        )

    # --- design.md 13節: subscription_status+各種event_time系グループ ---

    def test_get_subscription_status_default_trialing(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertEqual(self.store.get_subscription_status("w1"), "trialing")

    def test_get_subscription_status_for_unknown_workshop_is_trialing(self):
        self.assertEqual(self.store.get_subscription_status("unknown"), "trialing")

    def test_set_subscription_status_roundtrip(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_subscription_status("w1", "active")
        self.assertEqual(self.store.get_subscription_status("w1"), "active")

    def test_set_subscription_status_rejects_unknown_status(self):
        self.store.set_members("w1", "U_owner", [])
        with self.assertRaises(InvalidSubscriptionStatusError):
            self.store.set_subscription_status("w1", "not_a_real_status")
        # バリデーション失敗時はFirestoreへの書き込み自体が行われず、既定値のまま。
        self.assertEqual(self.store.get_subscription_status("w1"), "trialing")

    def test_subscription_status_event_time_roundtrip_and_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_subscription_status_event_time("w1"))
        event_time = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
        self.store.set_subscription_status_event_time("w1", event_time)
        self.assertEqual(self.store.get_subscription_status_event_time("w1"), event_time)

    def test_checkout_session_completed_event_time_roundtrip_and_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_checkout_session_completed_event_time("w1"))
        event_time = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
        self.store.set_checkout_session_completed_event_time("w1", event_time)
        self.assertEqual(
            self.store.get_checkout_session_completed_event_time("w1"), event_time
        )

    def test_subscription_updated_event_time_roundtrip_and_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_subscription_updated_event_time("w1"))
        event_time = datetime(2026, 10, 21, 13, 0, tzinfo=timezone.utc)
        self.store.set_subscription_updated_event_time("w1", event_time)
        self.assertEqual(self.store.get_subscription_updated_event_time("w1"), event_time)

    def test_current_period_end_roundtrip_and_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_current_period_end("w1"))
        current_period_end = datetime(2026, 11, 21, 13, 0, tzinfo=timezone.utc)
        self.store.set_current_period_end("w1", current_period_end)
        self.assertEqual(self.store.get_current_period_end("w1"), current_period_end)

    def test_subscription_status_group_fields_are_independent_and_do_not_clobber(self):
        # merge=True方針(design.md 2節・27節)の確認: 5フィールドが互いの値を消さず
        # 共存し、plan_id等の無関係フィールドも消えないこと。
        self.store.set_members("w1", "U_owner", [])
        self.store.set_plan("w1", "standard")
        self.store.set_subscription_status("w1", "past_due")
        self.store.set_subscription_status_event_time(
            "w1", datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc)
        )
        self.store.set_checkout_session_completed_event_time(
            "w1", datetime(2026, 10, 21, 11, 0, tzinfo=timezone.utc)
        )
        self.store.set_subscription_updated_event_time(
            "w1", datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
        )
        self.store.set_current_period_end(
            "w1", datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc)
        )

        self.assertEqual(self.store.get_plan_id("w1"), "standard")
        self.assertEqual(self.store.get_subscription_status("w1"), "past_due")
        self.assertEqual(
            self.store.get_subscription_status_event_time("w1"),
            datetime(2026, 10, 21, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            self.store.get_checkout_session_completed_event_time("w1"),
            datetime(2026, 10, 21, 11, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            self.store.get_subscription_updated_event_time("w1"),
            datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            self.store.get_current_period_end("w1"),
            datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc),
        )

    def test_payment_failure_detected_at_roundtrip_and_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_payment_failure_detected_at("w1"))
        detected_at = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        self.store.set_payment_failure_detected_at("w1", detected_at)
        self.assertEqual(self.store.get_payment_failure_detected_at("w1"), detected_at)

    def test_payment_failure_detected_at_for_unknown_workshop_is_none(self):
        self.assertIsNone(self.store.get_payment_failure_detected_at("unknown"))

    def test_payment_failure_reminder_sent_at_roundtrip_and_default_none(self):
        self.store.set_members("w1", "U_owner", [])
        self.assertIsNone(self.store.get_payment_failure_reminder_sent_at("w1"))
        sent_at = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)
        self.store.set_payment_failure_reminder_sent_at("w1", sent_at)
        self.assertEqual(self.store.get_payment_failure_reminder_sent_at("w1"), sent_at)

    def test_clear_payment_failure_detected_at_clears_three_fields(self):
        # design.md 15.1節・15.2節: InMemory実装と同じ契約で、payment_failure_detected_at
        # だけでなくpayment_failure_reminder_sent_at・payment_suspension_owner_notified_at
        # も同時にクリアする。
        self.store.set_members("w1", "U_owner", [])
        self.store.set_payment_failure_detected_at(
            "w1", datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        )
        self.store.set_payment_failure_reminder_sent_at(
            "w1", datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)
        )
        self.store._doc_ref("w1").set(
            {
                "payment_suspension_owner_notified_at": datetime(
                    2026, 10, 24, 9, 0, tzinfo=timezone.utc
                )
            },
            merge=True,
        )

        self.store.clear_payment_failure_detected_at("w1")

        self.assertIsNone(self.store.get_payment_failure_detected_at("w1"))
        self.assertIsNone(self.store.get_payment_failure_reminder_sent_at("w1"))
        snapshot = self.store._doc_ref("w1").get()
        self.assertIsNone(
            (snapshot.to_dict() or {}).get("payment_suspension_owner_notified_at")
        )

    def test_clear_payment_failure_detected_at_does_not_clobber_other_fields(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_plan("w1", "standard")
        self.store.set_subscription_status("w1", "past_due")
        self.store.set_payment_failure_detected_at(
            "w1", datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        )

        self.store.clear_payment_failure_detected_at("w1")

        self.assertEqual(self.store.get_plan_id("w1"), "standard")
        self.assertEqual(self.store.get_subscription_status("w1"), "past_due")

    def test_payment_failure_fields_are_independent_per_workshop(self):
        self.store.set_members("w1", "U_owner", [])
        self.store.set_members("w2", "U_owner2", [])
        self.store.set_payment_failure_detected_at(
            "w1", datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)
        )
        self.assertIsNone(self.store.get_payment_failure_detected_at("w2"))


if __name__ == "__main__":
    unittest.main()
