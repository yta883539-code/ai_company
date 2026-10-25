"""store-profile-store-firestore-adapter-design.md 2節(Stripeグループ)・
7節(owner_is_followingグループ)の設計を実コードに落としたもの。
firestore_store_document_provider.py(フェーズ続き340)・kura-pasha/course-set-pasha/
aircon-pashaの各Firestoreアダプタと同型の方針を踏襲し、google-cloud-firestore SDKを
直接importしない(`firestore_client`が`collection(name).document(id)`・`batch()`
(`.set()`/`.delete()`/`.commit()`を持つWriteBatch)を提供すれば、実SDKでもテスト用
フェイクでも差し替え可能)。

StoreProfileStoreProtocol全体(store_profile_store.py)のうち本ファイルが実装するのは
上記2グループ(5メソッド)のみ。他グループ(owner_user_id・suspension_reason・
owner_email・blocked_but_billing_owner_notified_at・plan・
checkout_session_completed_event_time・menu_durations・store_faq_info・
onboarding_completion_message・all_store_ids)は設計(design.md各節)は完了済みだが
実コード化は次回候補のまま残る。
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
