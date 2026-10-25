"""store-profile-store-firestore-adapter-design.md 2節(Stripeグループ)・
7節(owner_is_followingグループ)・19節(owner_user_idグループ)の設計を実コードに
落としたもの。
firestore_store_document_provider.py(フェーズ続き340)・kura-pasha/course-set-pasha/
aircon-pashaの各Firestoreアダプタと同型の方針を踏襲し、google-cloud-firestore SDKを
直接importしない(`firestore_client`が`collection(name).document(id)`・`batch()`
(`.set()`/`.delete()`/`.commit()`を持つWriteBatch)を提供すれば、実SDKでもテスト用
フェイクでも差し替え可能)。

StoreProfileStoreProtocol全体(store_profile_store.py)のうち本ファイルが実装するのは
上記3グループ・9節(suspension_reasonグループ)・11節(owner_emailグループ)の
計5グループ(11メソッド)のみ。
他グループ(blocked_but_billing_owner_notified_at・plan・
checkout_session_completed_event_time・menu_durations・store_faq_info・
onboarding_completion_message・all_store_ids・store_deletion_confirmation関連)は
設計(design.md各節)は完了済みだが実コード化は次回候補のまま残る。
"""

from __future__ import annotations

from typing import Optional


class FirestoreStoreProfileStore:
    """StoreProfileStoreProtocolの実Firestore接続実装(Stripeグループ・
    owner_is_followingグループのみ)。
    stores/{storeId}ドキュメントおよびstripe_customer_index/{stripeCustomerId}
    逆引きドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._stores = firestore_client.collection("stores")
        self._stripe_index = firestore_client.collection("stripe_customer_index")

    def _doc_ref(self, store_id: str):
        return self._stores.document(store_id)

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # get_business_name等と同じ安全側方針(firestore-provider-adapter-design.md
            # 3節): 接続エラーも「未設定」(None)に合流させる。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("stripeCustomerId")

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        if not stripe_customer_id:
            raise ValueError("stripe_customer_id must be a non-empty string")
        previous_stripe_customer_id = self.get_stripe_customer_id(user_id)

        batch = self._client.batch()
        batch.set(
            self._doc_ref(user_id),
            {"stripeCustomerId": stripe_customer_id},
            merge=True,
        )
        batch.set(
            self._stripe_index.document(stripe_customer_id),
            {"storeId": user_id},
        )
        if (
            previous_stripe_customer_id is not None
            and previous_stripe_customer_id != stripe_customer_id
        ):
            # InMemoryStoreProfileStoreの付け替え時挙動と契約を合わせる。
            batch.delete(self._stripe_index.document(previous_stripe_customer_id))
        batch.commit()

    def get_store_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        try:
            snapshot = self._stripe_index.document(stripe_customer_id).get()
        except Exception:
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("storeId")

    def get_owner_is_following(self, store_id: str) -> bool:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # InMemory実装の未設定時デフォルト(True)と揃える安全側フォールバック
            # (design.md 7節: 本フィールドの参照は候補抽出条件の一部であり、
            # 次回バッチで再評価されるため可逆)。
            return True
        if not snapshot.exists:
            return True
        return bool((snapshot.to_dict() or {}).get("ownerIsFollowing", True))

    def set_owner_is_following(self, store_id: str, is_following: bool) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        self._doc_ref(store_id).set(
            {"ownerIsFollowing": bool(is_following)}, merge=True
        )

    def get_owner_user_id(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # get_stripe_customer_id等と同じ安全側方針(firestore-provider-adapter-
            # design.md 3節): 接続エラーも「未設定」(None)に合流させる。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("ownerUserId")

    def set_owner_user_id(self, store_id: str, owner_user_id: str) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        if not owner_user_id:
            raise ValueError("owner_user_id must be a non-empty string")
        self._doc_ref(store_id).set({"ownerUserId": owner_user_id}, merge=True)

    def get_suspension_reason(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # InMemory実装の未設定時デフォルト(None=未停止)と揃える安全側フォールバック
            # (design.md 9節: 本フィールドはcloud_function_process_event.pyの新規予約
            # 受付判定に直接使われるが、予約リクエストごとに再評価される可逆な判定の
            # ため、7節・19節と同じ方針を適用する)。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("suspensionReason")

    def set_suspension_reason(
        self, store_id: str, suspension_reason: Optional[str]
    ) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        self._doc_ref(store_id).set(
            {"suspensionReason": suspension_reason}, merge=True
        )

    def get_owner_email(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # design.md 11節: 未設定/接続エラーを区別せずNoneに合流させる安全側方針。
            # 呼び出し側(blocked_but_billing_owner_email_notification.py)は真偽値
            # 判定のみに使うため、接続エラーの回は通知対象から外れるだけで済む。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("ownerEmail")

    def set_owner_email(self, store_id: str, owner_email: str) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        if not owner_email:
            raise ValueError("owner_email must be a non-empty string")
        self._doc_ref(store_id).set({"ownerEmail": owner_email}, merge=True
        )
