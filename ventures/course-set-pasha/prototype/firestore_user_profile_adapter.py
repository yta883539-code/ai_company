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

from typing import Optional


class FirestoreUserProfileStore:
    """UserProfileStoreProtocolの実Firestore接続実装(基盤2フィールド:
    gym_area_pairs・emailグループのみ。残りのグループ〈Stripe顧客IDグループ・
    is_following+all_user_ids・blocked_but_billing_owner_notified_at系・plan・
    checkout_session_completed_event_time〉は次回候補、設計5節末尾参照)。
    user_profile/{user_id}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("user_profile")

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
