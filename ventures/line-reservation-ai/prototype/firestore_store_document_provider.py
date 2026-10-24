"""firestore-provider-adapter-design.md 2節の設計を実コードに落としたもの。
kura-pasha firestore_workshop_adapter.py・course-set-pasha/aircon-pasha
firestore_user_profile_adapter.py等と同型の方針を踏襲し、google-cloud-firestore
SDKを直接importしない(`firestore_client`に`collection(name).document(id)`で
取得したドキュメント参照が`get()`(`.exists`・`.to_dict()`を持つSnapshotを返す)を
持てば、実SDKでもテスト用フェイクでも差し替え可能)。

StoreNameProviderProtocol・RegionNameProviderProtocol(cloud_function_process_event.py)
の両方を、design.md 2節の方針通り1クラスで実装する(stores/{storeId}を1回読むだけで
両フィールドを返す)。
"""

from __future__ import annotations


class FirestoreStoreDocumentProvider:
    """StoreNameProviderProtocol・RegionNameProviderProtocolの実Firestore接続実装。
    stores/{storeId}ドキュメントを読み、businessName・regionNameを取得する。
    両Protocolの契約(未設定・取得失敗時は空文字列)を維持する。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client

    def _get_store_doc(self, store_id: str) -> dict:
        try:
            snapshot = self._client.collection("stores").document(store_id).get()
        except Exception:
            # ネットワークエラー・権限エラー等はProtocol契約通り空文字列側の
            # フォールバックに合流させる(呼び出し元に例外を伝播させない)。
            return {}
        if not snapshot.exists:
            return {}
        return snapshot.to_dict() or {}

    def get_business_name(self, store_id: str) -> str:
        return self._get_store_doc(store_id).get("businessName") or ""

    def get_region_name(self, store_id: str) -> str:
        return self._get_store_doc(store_id).get("regionName") or ""
