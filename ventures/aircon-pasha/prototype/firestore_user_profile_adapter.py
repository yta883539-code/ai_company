"""firestore-provider-adapter-design.md 5節(基盤3メソッド+Stripe顧客IDグループ)・
19節(`_profile_to_dict`/`_profile_from_dict`ヘルパー)の設計を実コードに落としたもの。
kura-pashaのfirestore_workshop_adapter.py・course-set-pashaのfirestore_usage_counter_
adapter.pyと同型の方針を踏襲し、google-cloud-firestore SDKを直接importしない
(`firestore_client`に`collection(name).document(id)`で取得したドキュメント参照が
`get()`(`.exists`・`.to_dict()`を持つSnapshotを返す)・`set(data, merge=...)`を持ち、
`firestore_client.batch()`が`set(doc_ref, data, merge=...)`・`commit()`を持つ、という
最小インターフェースを満たせば実SDKでもテスト用フェイクでも差し替え可能)。

`UserProfileStoreProtocol`は design.md が5・7・9・11・13・15・17節の7グループに分けて
設計した本venture最大のProtocolであり、実コード化もグループ単位で段階的に行う。本モジュールは
design.md 5節の**基盤3メソッド(save/get/exists)+Stripe顧客IDグループ**のみを対象とする
(残り6グループ〈trial系・payment_failure系・current_plan_id・is_following+all_user_ids・
owner_notified_at系・event_time系4種〉は次回候補)。
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from user_id_linking import UserProfile


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
    グループのみ。design.md 7・9・11・13・15・17節の残りグループは次回候補、6節)。
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
