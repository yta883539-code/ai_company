"""workshop-store-firestore-adapter-design.md 2節(基盤グループ)・5節(メンバー削減系
グループ)の設計を実コードに落としたもの。firestore_usage_counter_adapter.py
(フェーズ248)・firestore_linking_code_adapter.py(フェーズ250)と同型の方針を踏襲し、
google-cloud-firestore SDKを直接importしない(`firestore_client`に
`collection(name).document(id)`で取得したドキュメント参照が`get()`(`.exists`・
`.to_dict()`を持つSnapshotを返す)・`set(data, merge=...)`・`update(data)`を持ち、
`collection(name).stream()`がSnapshot列を返す、という最小インターフェースを満たせば
実SDKでもテスト用フェイクでも差し替え可能)。

`WorkshopStoreProtocol`は30件超のメソッドを持つ本venture最大のProtocolであり、
design.mdが8グループ(基盤・メンバー削減系・契約者引き継ぎ系・trial系・
stripe_customer_id順引き逆引き系・subscription_status+event_time系・payment_failure系・
owner_notified_at系・deletion系)に分けて設計したのと同じ方針で、実コード化も
グループ単位で段階的に行う。本モジュールは design.md 2節の**基盤グループ**
(workshop新規作成時に書き込まれるフィールド+付随フィールド)・5節の
**メンバー削減系グループ**(`apply_member_reduction`等5メソッド)・7節の
**契約者引き継ぎ系グループ**(`pending_contractor_transfer`map型フィールドの3メソッド)
・9節の**trial系グループ**(`trial_start_at`・`trial_generation_used`の2フィールド
4メソッド)・11節の**stripe_customer_id順引き逆引き系グループ**(`get_stripe_customer_id`・
`set_stripe_customer_id`・`get_workshop_id_by_stripe_customer_id`の3メソッド)・
13節の**subscription_status+各種event_time系グループ**(`subscription_status`・
`subscription_status_event_time`・`checkout_session_completed_event_time`・
`subscription_updated_event_time`・`current_period_end`の5フィールド10メソッド)を対象とする
(残り2グループ〈payment_failure系・owner_notified_at系・deletion系〉は次回候補)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from usage_counter_workshop import (
    SUBSCRIPTION_STATUSES,
    InvalidSubscriptionStatusError,
    PendingContractorTransfer,
)


class ArrayUnion:
    """firestore.ArrayUnion相当の最小実装(design.md 2節`add_member_user_id`)。
    実SDKを直接importしないため、本モジュール内で同じ役割を果たす軽量な値オブジェクトを
    定義する。テスト用フェイク側がこの型を認識し、`update()`呼び出し時に重複排除
    (サーバー側のArrayUnionと同じ契約)を行う前提とする。
    """

    def __init__(self, values: list) -> None:
        self.values = list(values)


class FirestoreWorkshopStore:
    """WorkshopStoreProtocolの実Firestore接続実装(基盤グループ+メンバー削減系グループ+
    契約者引き継ぎ系グループ+trial系グループ+stripe_customer_id順引き逆引き系グループ+
    subscription_status+各種event_time系グループ。design.md 15・17・29節の残りグループは
    次回候補)。
    craftsman_workshop/{workshop_id}ドキュメントを読み書きする
    (stripe_customer_id逆引きはstripe_customer_index/{stripe_customer_id}
    ドキュメントを併用する、design.md 11節)。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._workshops = firestore_client.collection("craftsman_workshop")
        self._stripe_index = firestore_client.collection("stripe_customer_index")

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

    def set_pending_reduction_effective_at(
        self, workshop_id: str, effective_at: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"pending_member_reduction_effective_at": effective_at}, merge=True
        )

    def get_pending_reduction_effective_at(self, workshop_id: str) -> Optional[datetime]:
        # 23節の統一方針: 一時的な接続エラーは「未設定」側(None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("pending_member_reduction_effective_at")

    def set_specified_retention_member_name(self, workshop_id: str, name: str) -> None:
        self._doc_ref(workshop_id).set(
            {"specified_retention_member_name": name}, merge=True
        )

    def get_specified_retention_member_name(self, workshop_id: str) -> Optional[str]:
        # 23節の統一方針: 一時的な接続エラーは「未設定」側(None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("specified_retention_member_name")

    def apply_member_reduction(self, workshop_id: str, retained_user_ids: list[str]) -> None:
        # フェーズ223(design.md 19節)の確定仕様: member_user_idsの置き換えに加え、
        # pending_member_reduction_effective_at・specified_retention_member_nameの
        # 両方をクリアする(サイクル1回限りの入力のため)。InMemory実装(usage_counter_
        # workshop.py 821〜824行目)が2フィールドのpop(キー削除)を行うのに対し、
        # Firestore側はNone書き込みで揃える(get側が常に.get(key)でNoneフォールバック
        # する限り観測可能な挙動は一致する、5.1節で確立済みの根拠)。
        self._doc_ref(workshop_id).set(
            {
                "member_user_ids": list(retained_user_ids),
                "pending_member_reduction_effective_at": None,
                "specified_retention_member_name": None,
            },
            merge=True,
        )

    def get_pending_contractor_transfer(
        self, workshop_id: str
    ) -> Optional[PendingContractorTransfer]:
        # design.md 7節・23節の統一方針: 一時的な接続エラーは「未設定」側(None)に
        # 安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        data = (snapshot.to_dict() or {}).get("pending_contractor_transfer")
        if data is None:
            return None
        return PendingContractorTransfer(
            candidate_user_id=data["candidate_user_id"],
            candidate_member_name=data["candidate_member_name"],
            requested_at=data["requested_at"],
            expires_at=data["expires_at"],
        )

    def set_pending_contractor_transfer(
        self, workshop_id: str, pending: PendingContractorTransfer
    ) -> None:
        # design.md 7節の検討事項: mapフィールド全体を常に丸ごと書き込む(部分更新は
        # 呼び出し元usage_counter_workshop.start_pending_contractor_transfer()が
        # 常に新しいPendingContractorTransferインスタンス全体を渡すため想定しない)。
        self._doc_ref(workshop_id).set(
            {
                "pending_contractor_transfer": {
                    "candidate_user_id": pending.candidate_user_id,
                    "candidate_member_name": pending.candidate_member_name,
                    "requested_at": pending.requested_at,
                    "expires_at": pending.expires_at,
                }
            },
            merge=True,
        )

    def clear_pending_contractor_transfer(self, workshop_id: str) -> None:
        # design.md 7節: apply_member_reductionと同じNone書き込み方式(5.1節で確立済みの
        # 「InMemoryのpop()とFirestoreの明示的None書き込みは、get側が常に欠損をNone扱い
        # する限り観測可能な挙動が一致する」という根拠がここでも成立する)。
        self._doc_ref(workshop_id).set(
            {"pending_contractor_transfer": None}, merge=True
        )

    def get_trial_start_at(self, workshop_id: str) -> Optional[datetime]:
        # design.md 9節・23節の統一方針: 一時的な接続エラーは「未設定」側(None)に
        # 安全側合流させる(is_trial_period_over()がNoneを「トライアル未終了」扱いに
        # 倒す既存の安全側分岐と整合する)。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("trial_start_at")

    def set_trial_start_at(self, workshop_id: str, trial_start_at: datetime) -> None:
        self._doc_ref(workshop_id).set(
            {"trial_start_at": trial_start_at}, merge=True
        )

    def get_trial_generation_used(self, workshop_id: str) -> bool:
        # design.md 9節・23節の統一方針: 一時的な接続エラーは「未設定」側(False)に
        # 安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return False
        return (snapshot.to_dict() or {}).get("trial_generation_used", False)

    def set_trial_generation_used(self, workshop_id: str, used: bool = True) -> None:
        self._doc_ref(workshop_id).set(
            {"trial_generation_used": used}, merge=True
        )

    # --- design.md 11節: stripe_customer_id順引き逆引き系グループ ---

    def get_stripe_customer_id(self, workshop_id: str) -> Optional[str]:
        # design.md 11.1節・23節の統一方針: 一時的な接続エラーは「未設定」側(None)に
        # 安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("stripe_customer_id")

    def set_stripe_customer_id(self, workshop_id: str, stripe_customer_id: str) -> None:
        previous_stripe_customer_id = self.get_stripe_customer_id(workshop_id)

        batch = self._client.batch()
        batch.set(
            self._doc_ref(workshop_id),
            {"stripe_customer_id": stripe_customer_id},
            merge=True,
        )
        batch.set(
            self._stripe_index.document(stripe_customer_id),
            {"workshop_id": workshop_id},
        )
        if (
            previous_stripe_customer_id is not None
            and previous_stripe_customer_id != stripe_customer_id
        ):
            # InMemoryWorkshopStoreの付け替え時挙動(design.md 21節)と契約を合わせる。
            batch.delete(self._stripe_index.document(previous_stripe_customer_id))
        batch.commit()

    def get_workshop_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        # design.md 11.1節・23節の統一方針: 一時的な接続エラーは「未発見」側(None)に
        # 安全側合流させる。
        try:
            snapshot = self._stripe_index.document(stripe_customer_id).get()
        except Exception:
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("workshop_id")

    # --- design.md 13節: subscription_status+各種event_time系グループ ---

    def get_subscription_status(self, workshop_id: str) -> str:
        # design.md 13.3節・23節の統一方針: 一時的な接続エラーは「未契約」側
        # ("trialing")に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return "trialing"
        return (snapshot.to_dict() or {}).get("subscription_status", "trialing")

    def set_subscription_status(self, workshop_id: str, status: str) -> None:
        if status not in SUBSCRIPTION_STATUSES:
            raise InvalidSubscriptionStatusError(
                f"unknown subscription_status: {status!r} "
                f"(expected one of {SUBSCRIPTION_STATUSES})"
            )
        self._doc_ref(workshop_id).set({"subscription_status": status}, merge=True)

    def get_subscription_status_event_time(self, workshop_id: str) -> Optional[datetime]:
        # design.md 13節・23節の統一方針: 一時的な接続エラーは配信順序ガード無効化側
        # (None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("subscription_status_event_time")

    def set_subscription_status_event_time(
        self, workshop_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"subscription_status_event_time": event_time}, merge=True
        )

    def get_checkout_session_completed_event_time(
        self, workshop_id: str
    ) -> Optional[datetime]:
        # design.md 13節・23節の統一方針: 一時的な接続エラーは配信順序ガード無効化側
        # (None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("checkout_session_completed_event_time")

    def set_checkout_session_completed_event_time(
        self, workshop_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"checkout_session_completed_event_time": event_time}, merge=True
        )

    def get_subscription_updated_event_time(self, workshop_id: str) -> Optional[datetime]:
        # design.md 13節・23節の統一方針: 一時的な接続エラーは配信順序ガード無効化側
        # (None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("subscription_updated_event_time")

    def set_subscription_updated_event_time(
        self, workshop_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"subscription_updated_event_time": event_time}, merge=True
        )

    def get_current_period_end(self, workshop_id: str) -> Optional[datetime]:
        # design.md 13節・23節の統一方針: 一時的な接続エラーは配信順序ガード無効化側
        # (None)に安全側合流させる。
        try:
            snapshot = self._doc_ref(workshop_id).get()
        except Exception:
            return None
        return (snapshot.to_dict() or {}).get("current_period_end")

    def set_current_period_end(self, workshop_id: str, current_period_end: datetime) -> None:
        self._doc_ref(workshop_id).set(
            {"current_period_end": current_period_end}, merge=True
        )
