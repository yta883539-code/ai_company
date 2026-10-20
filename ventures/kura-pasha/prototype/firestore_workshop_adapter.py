"""workshop-store-firestore-adapter-design.md 2節(基盤グループ)の設計を実コードに落としたもの。
firestore_usage_counter_adapter.py(フェーズ248)・firestore_linking_code_adapter.py
(フェーズ250)と同型の方針を踏襲し、google-cloud-firestore SDKを直接importしない
(`firestore_client`に`collection(name).document(id)`で取得したドキュメント参照が
`get()`(`.exists`・`.to_dict()`を持つSnapshotを返す)・`set(data, merge=...)`・
`update(data)`を持ち、`collection(name).stream()`がSnapshot列を返す、という最小
インターフェースを満たせば実SDKでもテスト用フェイクでも差し替え可能)。

`WorkshopStoreProtocol`は30件超のメソッドを持つ本venture最大のProtocolであり、
design.mdが8グループ(基盤・メンバー削減系・契約者引き継ぎ系・trial系・
stripe_customer_id順引き逆引き系・subscription_status+event_time系・payment_failure系・
owner_notified_at系・deletion系)に分けて設計したのと同じ方針で、実コード化も
グループ単位で段階的に行う。本モジュールは design.md 2節の**基盤グループ**
(workshop新規作成時に書き込まれるフィールド+付随フィールド)のみを対象とする
(残りのグループは次回候補)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional


class ArrayUnion:
    """firestore.ArrayUnion相当の最小実装(design.md 2節`add_member_user_id`)。
    実SDKを直接importしないため、本モジュール内で同じ役割を果たす軽量な値オブジェクトを
    定義する。テスト用フェイク側がこの型を認識し、`update()`呼び出し時に重複排除
    (サーバー側のArrayUnionと同じ契約)を行う前提とする。
    """

    def __init__(self, values: list) -> None:
        self.values = list(values)


class FirestoreWorkshopStore:
    """WorkshopStoreProtocolの実Firestore接続実装(基盤グループのみ。design.md 5・7・9・
    11・13・15・17・29節の残りグループは次回候補)。craftsman_workshop/{workshop_id}
    ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._workshops = firestore_client.collection("craftsman_workshop")

    def _doc_ref(self, workshop_id: str):
        return self._workshops.document(workshop_id)

    def set_members(
        self,
        workshop_id: str,
        contractor_user_id: str,
        member_user_ids: list[str],
        display_names: Optional[dict[str, str]] = None,
    ) -> None:
        all_ids = [contractor_user_id] + [
            uid for uid in member_user_ids if uid != contractor_user_id
        ]
        self._doc_ref(workshop_id).set(
            {
                "contractor_user_id": contractor_user_id,
                "member_user_ids": all_ids,
                "member_display_names": dict(display_names or {}),
            },
            merge=True,
        )

    def get_contractor_user_id(self, workshop_id: str) -> str:
        # design.md 23.3節: 認可判定(契約者本人確認)に直接使われるため、接続エラーを
        # 安全側デフォルトに合流させず例外を伝播させる(fail-closed)。未作成workshop_idに
        # 対する挙動もInMemory実装と同じKeyError相当(ここではdict直接アクセスに相当する
        # 欠損キー参照で例外を送出する)。
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {})["contractor_user_id"]

    def set_contractor_user_id(self, workshop_id: str, user_id: str) -> None:
        self._doc_ref(workshop_id).set({"contractor_user_id": user_id}, merge=True)

    def get_member_user_ids(self, workshop_id: str) -> list[str]:
        # 23節の統一方針: 一時的な接続エラーは「メンバーなし」側([])に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return []
        return list((snapshot.to_dict() or {}).get("member_user_ids", []))

    def add_member_user_id(self, workshop_id: str, user_id: str) -> None:
        # 本来はFirestoreのArrayUnion(サーバー側で重複排除される原子的操作)を使うが、
        # 本モジュールは実SDKを直接importしないため、このモジュール内のArrayUnion値
        # オブジェクトを渡す(テスト用フェイクが同じ重複排除契約を再現する)。
        self._doc_ref(workshop_id).update(
            {"member_user_ids": ArrayUnion([user_id])}
        )

    def get_member_display_name(self, workshop_id: str, user_id: str) -> Optional[str]:
        # 23節の統一方針: 一時的な接続エラーは「表示名未設定」側(None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("member_display_names", {}).get(user_id)

    def get_plan_id(self, workshop_id: str) -> str:
        # design.md 23.3節: 利用上限プラン判定に直接使われるため、get_contractor_user_id
        # と同じ理由で例外を伝播させる(fail-closed)。
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {})["plan_id"]

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        self._doc_ref(workshop_id).set({"plan_id": plan_id}, merge=True)

    def get_workshop_name(self, workshop_id: str) -> Optional[str]:
        # 23節の統一方針: 一時的な接続エラーは「未設定」側(None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("workshop_name")

    def set_workshop_name(self, workshop_id: str, workshop_name: str) -> None:
        self._doc_ref(workshop_id).set({"workshop_name": workshop_name}, merge=True)

    def get_first_generation_notice_sent(self, workshop_id: str) -> bool:
        # 23節の統一方針: 一時的な接続エラーは「未送信」側(False)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return False
        return (snapshot.to_dict() or {}).get("first_generation_notice_sent", False)

    def set_first_generation_notice_sent(self, workshop_id: str) -> None:
        self._doc_ref(workshop_id).set(
            {"first_generation_notice_sent": True}, merge=True
        )

    def all_workshop_ids(self) -> Iterable[str]:
        return [doc.id for doc in self._workshops.stream()]
