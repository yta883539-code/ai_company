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

フェーズ続き340: usage_counter_workshop.py側のUserProfileStoreProtocolへ追加された
`unlink(user_id)`(downgrade-excess-member-handling-design.md「4. 未検証・残課題」で
確定した、縮小除外メンバーのworkshop_id null化)に対応するFirestore実装を追加した。

フェーズ続き341: `unlink(user_id, unlinked_at=...)`・`get_unlinked_at`・
`all_unlinked_user_ids`を追加した(member-user-profile-deletion-candidate-design.md
参照)。`all_unlinked_user_ids`はfirestore_workshop_adapter.pyの`all_workshop_ids`
(`.stream()`による全件スキャン)と同じ方針で、`user_profile`コレクション全件を
読み取ってクライアント側で`unlinked_at`の有無を判定する(deletion-candidate-query-
consolidation-decision.md同様、実運用規模が大きくなった場合は複合インデックスを使う
単一クエリへの統合が将来の最適化候補として残る)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional


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
        # フェーズ続き341: InMemoryUserProfileStore.linkと同じ「再リンク時はunlinked_at
        # をクリアする」方針をFirestore側にも反映する。
        self._doc_ref(user_id).set(
            {"workshop_id": workshop_id, "unlinked_at": None}, merge=True
        )

    def unlink(self, user_id: str, unlinked_at: Optional[datetime] = None) -> None:
        """フェーズ続き340: workshop_idをNoneへ戻す(ドキュメント自体は削除しない。
        is_following等の他フィールドをmerge=Trueのまま維持するため)。

        フェーズ続き341: `unlinked_at`を渡した場合は`unlinked_at`フィールドにも
        記録する(省略時は既存の値を変更しない)。"""
        data: dict = {"workshop_id": None}
        if unlinked_at is not None:
            data["unlinked_at"] = unlinked_at
        self._doc_ref(user_id).set(data, merge=True)

    def get_unlinked_at(self, user_id: str) -> Optional[datetime]:
        return self._get_doc(user_id).get("unlinked_at")

    def all_unlinked_user_ids(self) -> Iterable[str]:
        return [
            doc.id
            for doc in self._client.collection("user_profile").stream()
            if (doc.to_dict() or {}).get("unlinked_at") is not None
        ]

    def get_is_following(self, user_id: str) -> bool:
        doc = self._get_doc(user_id)
        if "is_following" not in doc:
            # InMemoryUserProfileStoreと同じ既定値: プロフィール未作成・
            # is_following未設定のuser_idはTrue(未フォロー状態は存在しない)。
            return True
        return bool(doc["is_following"])

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        self._doc_ref(user_id).set({"is_following": is_following}, merge=True)
