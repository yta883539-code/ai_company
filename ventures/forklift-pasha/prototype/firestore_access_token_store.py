"""access-token-store-firestore-adapter-design.md(フェーズ159)の設計を実コードに
落としたもの。firestore_fleet_operator_adapter.FirestoreFleetOperatorStoreと同型の方針
(google-cloud-firestore SDKを直接importしない、`collection(name).document(id)`で取得した
ドキュメント参照が`get()`・`set(data, merge=...)`を持てば実SDKでもテスト用フェイクでも
差し替え可能)を踏襲する。

design.md 1節の判断により、本クラスはFirestoreFleetOperatorStoreとは独立したクラスの
ままとする(両クラスとも同一の`fleet_operator/{internal_id}`ドキュメントを読み書きするが、
Protocol単体のテスト・差し替えのしやすさを優先し、ドキュメント取得1回への統合は時期尚早な
最適化として見送る)。
"""

from __future__ import annotations

from datetime import datetime


class FirestoreAccessTokenStore:
    """AccessTokenStoreProtocol(prototype/access_token_store.py)の実Firestore接続実装。
    fleet_operator/{internal_id}ドキュメントの`accessToken`・`lastAccessedAt`フィールドを
    読み書きする(firestore-data-model.md「1. fleet_operator/{internal_id}」)。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._operators = firestore_client.collection("fleet_operator")

    def _doc_ref(self, internal_id: str):
        return self._operators.document(internal_id)

    def _get_field(self, internal_id: str, field: str):
        try:
            snapshot = self._doc_ref(internal_id).get()
        except Exception:
            # design.md「2.3節」が前提とする安全側方針(firestore_fleet_operator_adapter.
            # _get_fieldと同じ)。一時的な接続エラーも「未設定」(None)に合流させる。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(field)

    def get_access_token(self, internal_id: str) -> "str | None":
        return self._get_field(internal_id, "accessToken")

    def set_access_token(self, internal_id: str, value: str) -> None:
        # design.md 2.1節: InMemory版が持つ旧トークンの逆引きインデックス削除処理は
        # 不要(2.3節のライブクエリにより自動的に失効する)。
        self._doc_ref(internal_id).set({"accessToken": value}, merge=True)

    def get_internal_id_by_access_token(self, access_token: str) -> "str | None":
        # design.md 2.3節: accessTokenフィールドへの単一フィールドクエリ。
        query = self._operators.where("accessToken", "==", access_token).limit(1)
        docs = list(query.stream())
        return docs[0].id if docs else None

    def get_last_accessed_at(self, internal_id: str) -> "datetime | None":
        return self._get_field(internal_id, "lastAccessedAt")

    def set_last_accessed_at(self, internal_id: str, value: datetime) -> None:
        self._doc_ref(internal_id).set({"lastAccessedAt": value}, merge=True)
