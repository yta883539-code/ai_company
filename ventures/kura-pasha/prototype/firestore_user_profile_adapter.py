"""firestore-provider-adapter-design.md 2節の設計を実コードに落としたもの。
firestore_workshop_adapter.py・firestore_usage_counter_adapter.py・
firestore_linking_code_adapter.pyと同型の方針を踏襲し、google-cloud-firestore SDKを
直接importしない(`firestore_client`に`collection(name).document(id)`で取得した
ドキュメント参照が`get()`(`.exists`・`.to_dict()`を持つSnapshotを返す)・
`set(data, merge=True)`を持つ、という最小インターフェースを満たせば実SDKでもテスト用
フェイクでも差し替え可能)。

本venture4Protocol(WorkshopStoreProtocol・UsageCounterStoreProtocol・
LinkingCodeStoreProtocol・UserProfileStoreProtocol)のうち、本モジュールが最後に
残っていたUserProfileStoreProtocol(get_workshop_id・link・get_is_following・
set_is_following の4メソッド、対象ドキュメントはuser_profile/{user_id}単一)の
実コード化にあたる。
"""

from __future__ import annotations

from typing import Optional


class FirestoreUserProfileProvider:
    """UserProfileStoreProtocolの実Firestore接続実装。
    user_profile/{user_id}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client

    def _doc_ref(self, user_id: str):
        return self._client.collection("user_profile").document(user_id)

    def _get_doc(self, user_id: str) -> dict:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # design.md 3節の方針: ネットワークエラー・権限エラー等はProtocol契約通りの
            # 安全側フォールバック(get_workshop_id→None、get_is_following→True)に
            # 合流させ、呼び出し元に例外を伝播させない。
            return {}
        if not snapshot.exists:
            return {}
        return snapshot.to_dict() or {}

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        return self._get_doc(user_id).get("workshop_id")

    def link(self, user_id: str, workshop_id: str) -> None:
        self._doc_ref(user_id).set({"workshop_id": workshop_id}, merge=True)

    def get_is_following(self, user_id: str) -> bool:
        doc = self._get_doc(user_id)
        if "is_following" not in doc:
            # InMemoryUserProfileStoreと同じ既定値: プロフィール未作成・
            # is_following未設定のuser_idはTrue(未フォロー状態は存在しない)。
            return True
        return bool(doc["is_following"])

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        self._doc_ref(user_id).set({"is_following": is_following}, merge=True)
