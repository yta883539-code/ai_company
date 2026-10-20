"""linking-code-store-firestore-adapter-design.md(フェーズ213)・invite-code-store-
firestore-adapter-design.md(フェーズ214)の設計を実コードに落としたもの。
firestore_usage_counter_adapter.py(フェーズ248)と同型の方針を踏襲し、
google-cloud-firestore SDKを直接importしない(`firestore_client`に
`collection(name).document(id)`で取得したドキュメント参照が`get()`
(`.exists`・`.to_dict()`を持つSnapshotを返す)・`set(data)`・`delete()`を持ち、
`collection(name).stream()`がSnapshot列を返す、という最小インターフェースを満たせば
実SDKでもテスト用フェイクでも差し替え可能)。

`LinkingCodeStoreProtocol`という同名の型を2つの異なるコレクション
(`pending_links`・`pending_workshop_invites`)に使う設計(両design.md参照)のため、
コンストラクタで異なる`firestore_client.collection(...)`を参照するだけの別クラスとして
2つとも本モジュールに定義する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional, Tuple


class FirestorePendingLinkStore:
    """LinkingCodeStoreProtocol(pending_links/{code}向け)の実Firestore接続実装。

    follow時の新規workshop作成用連携コード(`user_id`を保存)を扱う
    (linking-code-store-firestore-adapter-design.md 2節)。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("pending_links")

    def save(self, code: str, user_id: str, issued_at: datetime) -> None:
        self._collection.document(code).set({"user_id": user_id, "issued_at": issued_at})

    def get(self, code: str) -> Optional[Tuple[str, datetime]]:
        try:
            snapshot = self._collection.document(code).get()
        except Exception:
            # ネットワークエラー・権限エラー等は「未発見」(None)に倒す(design.md 3節)。
            return None
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        user_id = data.get("user_id")
        issued_at = data.get("issued_at")
        if user_id is None or issued_at is None:
            return None
        return (user_id, issued_at)

    def delete(self, code: str) -> None:
        self._collection.document(code).delete()

    def items(self) -> Iterable[Tuple[str, str, datetime]]:
        for snapshot in self._collection.stream():
            data = snapshot.to_dict() or {}
            user_id = data.get("user_id")
            issued_at = data.get("issued_at")
            if user_id is None or issued_at is None:
                continue
            yield (snapshot.id, user_id, issued_at)


class FirestoreWorkshopInviteStore:
    """LinkingCodeStoreProtocol(pending_workshop_invites/{code}向け)の実Firestore接続実装。

    既存workshopへのメンバー追加用招待コード(`workshop_id`を保存)を扱う。フィールド名
    (`user_id`ではなく`workshop_id`)以外はFirestorePendingLinkStoreと設計方針が
    完全に一致する(invite-code-store-firestore-adapter-design.md 2節)。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("pending_workshop_invites")

    def save(self, code: str, workshop_id: str, issued_at: datetime) -> None:
        self._collection.document(code).set(
            {"workshop_id": workshop_id, "issued_at": issued_at}
        )

    def get(self, code: str) -> Optional[Tuple[str, datetime]]:
        try:
            snapshot = self._collection.document(code).get()
        except Exception:
            return None
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        workshop_id = data.get("workshop_id")
        issued_at = data.get("issued_at")
        if workshop_id is None or issued_at is None:
            return None
        return (workshop_id, issued_at)

    def delete(self, code: str) -> None:
        self._collection.document(code).delete()

    def items(self) -> Iterable[Tuple[str, str, datetime]]:
        for snapshot in self._collection.stream():
            data = snapshot.to_dict() or {}
            workshop_id = data.get("workshop_id")
            issued_at = data.get("issued_at")
            if workshop_id is None or issued_at is None:
                continue
            yield (snapshot.id, workshop_id, issued_at)
