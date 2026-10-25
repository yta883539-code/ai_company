"""firestore-provider-adapter-design.md 5節(UserProfileStoreProtocolの基盤2フィールド:
gym_area_pairs・emailグループ)の設計を実コードに落としたもの。

実Firestoreプロジェクトへの接続自体はpending-approval.md記載の通りオーナー承認待ちのため、
本モジュールはgoogle-cloud-firestore SDKを直接importしない。firestore_usage_counter_
adapter.pyと同じ最小インターフェース(collection(name).document(id)が
get()/set(data)を持つドキュメント参照を返す)を前提にする。

5.2節の設計コード例は`set({...}, merge=True)`一発を想定していたが、19節以降の各
フェーズ(24節等)で確立した理由(フェイクの`document.set(data)`がmerge引数を取らない)
により、本実装も既存パターンと揃えて「読んでから全フィールドをベースに書き戻す」方式で
同じ契約(user_profile/{user_id}を共有する他グループのフィールドを消さない)を満たす。
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional


class FirestoreUserProfileStore:
    """UserProfileStoreProtocolの実Firestore接続実装(基盤2フィールド:
    gym_area_pairs・emailグループ、Stripe顧客IDグループ〈フェーズ323、設計6節〉、
    is_following+all_user_idsグループ〈フェーズ324、設計7節〉、および
    blocked_but_billing_owner_notified_atグループ〈フェーズ325、設計9節〉、
    planグループ〈フェーズ327、設計11節〉、および
    checkout_session_completed_event_timeグループ〈フェーズ328、設計13節〉。
    これで`UserProfileStoreProtocol`の全グループの実Firestore接続アダプタ実装が完了する)。
    加えて`GymAreaConfigStoreProtocol.is_configured()`〈フェーズ330、設計15節〉も
    get_gym_area_pairs()への委譲として同一クラスで満たす。
    user_profile/{user_id}ドキュメント、およびstripe_customer_id逆引き用の
    stripe_customer_index/{stripe_customer_id}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("user_profile")
        self._stripe_index = firestore_client.collection("stripe_customer_index")

    def set_gym_area_pairs(self, user_id: str, raw_value: str) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["gym_area_pairs"] = raw_value
        doc_ref.set(data)

    def get_gym_area_pairs(self, user_id: str) -> str:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return ""
        return (snapshot.to_dict() or {}).get("gym_area_pairs", "")

    def is_configured(self, user_id: str) -> bool:
        # 設計15.2節: 専用のドキュメント読み取りを別途行わず、get_gym_area_pairs()の
        # 非空判定に委譲する(GymAreaConfigStoreProtocol互換)。
        return bool(self.get_gym_area_pairs(user_id))

    def set_email(self, user_id: str, email: str) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["email"] = email
        doc_ref.set(data)

    def get_email(self, user_id: str) -> Optional[str]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("email")

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        # フェーズ286(aircon-pashaフェーズ294の方式を横展開、設計6.3節)と同じ
        # 再紐付け検出: 書き込み前に旧stripe_customer_idを読み出し、変化があれば
        # stripe_customer_index側の旧エントリを削除してから新エントリを書き込む。
        previous_stripe_customer_id = self.get_stripe_customer_id(user_id)
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["stripe_customer_id"] = stripe_customer_id
        doc_ref.set(data)
        if (
            previous_stripe_customer_id is not None
            and previous_stripe_customer_id != stripe_customer_id
        ):
            self._stripe_index.document(previous_stripe_customer_id).delete()
        self._stripe_index.document(stripe_customer_id).set({"user_id": user_id})

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("stripe_customer_id")

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        snapshot = self._stripe_index.document(stripe_customer_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("user_id")

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["is_following"] = is_following
        doc_ref.set(data)

    def get_is_following(self, user_id: str) -> bool:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return True
        return (snapshot.to_dict() or {}).get("is_following", True)

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: datetime
    ) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["blocked_but_billing_owner_notified_at"] = notified_at
        doc_ref.set(data)

    def get_blocked_but_billing_owner_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(
            "blocked_but_billing_owner_notified_at"
        )

    def clear_blocked_but_billing_owner_notified_at(self, user_id: str) -> None:
        # 設計9.3節: InMemory版はキー自体をpopするが、get側はキー不在・null値いずれも
        # Noneとして返すため、nullとして書き込んでも観測可能な挙動は一致する。
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["blocked_but_billing_owner_notified_at"] = None
        doc_ref.set(data)

    def set_plan(self, user_id: str, plan: str) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["plan"] = plan
        doc_ref.set(data)

    def get_plan(self, user_id: str) -> Optional[str]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("plan")

    def set_checkout_session_completed_event_time(
        self, user_id: str, event_time: datetime
    ) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["checkout_session_completed_event_time"] = event_time
        doc_ref.set(data)

    def get_checkout_session_completed_event_time(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(
            "checkout_session_completed_event_time"
        )

    def all_user_ids(self) -> Iterable[str]:
        # 設計7.2節・7.3節: user_profileコレクション全件のドキュメントID集合は、
        # InMemoryUserProfileStore.all_user_ids()が5辞書から取る和集合と常に一致する
        # (blocked_but_billing_owner_notified_at・checkout_session_completed_event_timeは
        # 必ず本グループ以降に書き込まれるため、和集合から除外しても欠落しない)。
        for snapshot in self._collection.stream():
            yield snapshot.id
