"""firestore-provider-adapter-design.md 5節(基盤3メソッド+Stripe顧客IDグループ)・
7節(trial系グループ)・19節(`_profile_to_dict`/`_profile_from_dict`ヘルパー)の設計を
実コードに落としたもの。kura-pashaのfirestore_workshop_adapter.py・course-set-pashaの
firestore_usage_counter_adapter.pyと同型の方針を踏襲し、google-cloud-firestore SDKを
直接importしない(`firestore_client`に`collection(name).document(id)`で取得した
ドキュメント参照が`get()`(`.exists`・`.to_dict()`を持つSnapshotを返す)・
`set(data, merge=...)`を持ち、`firestore_client.batch()`が`set(doc_ref, data, merge=...)`・
`commit()`を持つ、という最小インターフェースを満たせば実SDKでもテスト用フェイクでも
差し替え可能)。

`UserProfileStoreProtocol`は design.md が5・7・9・11・13・15・17節の7グループに分けて
設計した本venture最大のProtocolであり、実コード化もグループ単位で段階的に行う。本モジュールは
design.md 5節の**基盤3メソッド(save/get/exists)+Stripe顧客IDグループ**・7節の
**trial系グループ**(`set_trial_start_at`/`set_trial_end_notified_at`/`set_upgraded_at`/
`increment_trial_generation_count`/`increment_trial_unit_count`/`get_trial_unit_count`)・
9節の**payment_failure系グループ**(`payment_failure_detected_at`・`payment_suspended_at`・
`payment_failure_reminder_sent_at`・`payment_failure_detection_notified_at`の
get/set計8メソッド)・11節の**owner_notified_at系グループ**
(`blocked_but_billing_owner_notified_at`・`payment_suspension_owner_notified_at`の
get/set計4メソッド)・13節の**current_plan_idグループ**(1フィールド・get/set計2メソッド)
を対象とする(残り2グループ〈is_following+all_user_ids・event_time系4種〉は次回候補)。

design.md 7.2節のコード例は実SDKの`google.cloud.firestore.Increment`を前提にしているが、
本モジュールは実SDK非依存方針を維持するため、同じ「サーバー側フィールド変換として加算する」
意味論のみを表す本モジュール独自の`Increment`センチネルを定義し、フェイク・実SDKアダプタの
いずれからも同じインターフェース(`set({"field": Increment(n)}, merge=True)`)で扱える
ようにしている(実SDK接続時はこの`Increment`を`google.cloud.firestore.Increment`に
読み替えるだけで済む)。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Optional

from user_id_linking import UserProfile


class Increment:
    """design.md 7.2節の`firestore.Increment`相当の最小センチネル。実SDKを直接
    importしない本モジュールの方針を保つため、「現在値への加算」という意味論だけを
    運ぶ軽量な値オブジェクトとして定義する(実際の加算処理はFirestoreクライアント側
    〈実SDKまたはテスト用フェイク〉がこのセンチネルを見て行う)。
    """

    def __init__(self, value: int) -> None:
        self.value = value


def _profile_to_dict(profile: UserProfile) -> dict:
    # design.md 19.2節: UserProfileはフラットなdataclass(ネストしたdataclass・
    # list/dict型フィールドを持たない)であるため、dataclasses.asdict()のディープコピー
    # オーバーヘッドを避け、dataclasses.fields()+getattrで直接値を取り出す。
    return {
        field.name: getattr(profile, field.name)
        for field in dataclasses.fields(profile)
    }


def _profile_from_dict(data: dict) -> UserProfile:
    # design.md 19.3節: UserProfile(**data)はキーワード引数に存在しないフィールドを
    # dataclass自身の既定値で埋めるため、フィールド追加前に連携した既存ドキュメントの
    # キー欠落に対しても特別なマイグレーション処理なしに後方互換性が成立する。
    return UserProfile(**data)


class FirestoreUserProfileStore:
    """UserProfileStoreProtocolの実Firestore接続実装(基盤3メソッド+Stripe顧客ID
    グループ・trial系グループ・payment_failure系グループ。design.md 11・13・15・17節の
    残りグループは次回候補)。
    user_profile/{user_id}ドキュメントおよびstripe_customer_index/{stripe_customer_id}
    逆引きドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._profiles = firestore_client.collection("user_profile")
        self._stripe_index = firestore_client.collection("stripe_customer_index")

    def _doc_ref(self, user_id: str):
        return self._profiles.document(user_id)

    def save(self, user_id: str, profile: UserProfile) -> None:
        # design.md 5.3節: 連携成立時の新規作成のみを想定するためset()(merge無し)。
        # 既存フィールドの部分更新は個別グループのset_*メソッド(merge=True)で行う。
        self._doc_ref(user_id).set(_profile_to_dict(profile))

    def get(self, user_id: str) -> Optional[UserProfile]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # design.md 5.3節: LinkingCodeStoreProtocol.get()と同じ安全側方針。
            # 一時的な接続エラーも「未発見」(None)に合流させる。
            return None
        if not snapshot.exists:
            return None
        return _profile_from_dict(snapshot.to_dict() or {})

    def exists(self, user_id: str) -> bool:
        try:
            return self._doc_ref(user_id).get().exists
        except Exception:
            return False

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        batch = self._client.batch()
        batch.set(
            self._doc_ref(user_id),
            {"stripe_customer_id": stripe_customer_id},
            merge=True,
        )
        batch.set(
            self._stripe_index.document(stripe_customer_id),
            {"user_id": user_id},
        )
        batch.commit()

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        try:
            snapshot = self._stripe_index.document(stripe_customer_id).get()
        except Exception:
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("user_id")

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        profile = self.get(user_id)
        if profile is None:
            return None
        return profile.stripe_customer_id

    def set_trial_start_at(self, user_id: str, at: datetime) -> None:
        self._doc_ref(user_id).set({"trial_start_at": at}, merge=True)

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        self._doc_ref(user_id).set({"trial_end_notified_at": notified_at}, merge=True)

    def set_upgraded_at(self, user_id: str, at: datetime) -> None:
        self._doc_ref(user_id).set({"upgraded_at": at}, merge=True)

    def increment_trial_generation_count(self, user_id: str) -> int:
        doc_ref = self._doc_ref(user_id)
        doc_ref.set({"trial_generation_count": Increment(1)}, merge=True)
        return (doc_ref.get().to_dict() or {}).get("trial_generation_count", 0)

    def increment_trial_unit_count(self, user_id: str, unit_count: int) -> int:
        doc_ref = self._doc_ref(user_id)
        doc_ref.set({"trial_unit_count": Increment(unit_count)}, merge=True)
        return (doc_ref.get().to_dict() or {}).get("trial_unit_count", 0)

    def get_trial_unit_count(self, user_id: str) -> int:
        profile = self.get(user_id)
        return profile.trial_unit_count if profile is not None else 0

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.payment_failure_detected_at if profile is not None else None

    def set_payment_failure_detected_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_failure_detected_at": value}, merge=True
        )

    def get_payment_suspended_at(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.payment_suspended_at if profile is not None else None

    def set_payment_suspended_at(self, user_id: str, value: Optional[datetime]) -> None:
        self._doc_ref(user_id).set({"payment_suspended_at": value}, merge=True)

    def get_payment_failure_reminder_sent_at(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.payment_failure_reminder_sent_at if profile is not None else None

    def set_payment_failure_reminder_sent_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_failure_reminder_sent_at": value}, merge=True
        )

    def get_payment_failure_detection_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        profile = self.get(user_id)
        return (
            profile.payment_failure_detection_notified_at
            if profile is not None
            else None
        )

    def set_payment_failure_detection_notified_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_failure_detection_notified_at": value}, merge=True
        )

    def get_current_plan_id(self, user_id: str) -> Optional[str]:
        profile = self.get(user_id)
        return profile.current_plan_id if profile is not None else None

    def set_current_plan_id(self, user_id: str, plan_id: Optional[str]) -> None:
        self._doc_ref(user_id).set({"current_plan_id": plan_id}, merge=True)

    def get_blocked_but_billing_owner_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        profile = self.get(user_id)
        return (
            profile.blocked_but_billing_owner_notified_at
            if profile is not None
            else None
        )

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"blocked_but_billing_owner_notified_at": notified_at}, merge=True
        )

    def get_payment_suspension_owner_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        profile = self.get(user_id)
        return (
            profile.payment_suspension_owner_notified_at
            if profile is not None
            else None
        )

    def set_payment_suspension_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_suspension_owner_notified_at": notified_at}, merge=True
        )
