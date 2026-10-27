"""store-profile-store-firestore-adapter-design.md 2節(Stripeグループ)・
7節(owner_is_followingグループ)・19節(owner_user_idグループ)の設計を実コードに
落としたもの。
firestore_store_document_provider.py(フェーズ続き340)・kura-pasha/course-set-pasha/
aircon-pashaの各Firestoreアダプタと同型の方針を踏襲し、google-cloud-firestore SDKを
直接importしない(`firestore_client`が`collection(name).document(id)`・`batch()`
(`.set()`/`.delete()`/`.commit()`を持つWriteBatch)を提供すれば、実SDKでもテスト用
フェイクでも差し替え可能)。

StoreProfileStoreProtocol全体(store_profile_store.py)のうち本ファイルが実装するのは
上記3グループ・9節(suspension_reasonグループ)・11節(owner_emailグループ)・
13節(blocked_but_billing_owner_notified_atグループ)・15節(planグループ)・
26節(all_store_idsグループ)・22節(menu_durationsグループ)の計9グループ
(18メソッド)。他グループ(checkout_session_completed_event_time・store_faq_info・
onboarding_completion_message・store_deletion_confirmation関連)は設計
(design.md各節)は完了済みだが実コード化は次回候補のまま残る。
"""

from __future__ import annotations

from typing import Iterable, Optional

from store_profile_store import PLAN_MONTHLY_BOOKING_LIMITS


class FirestoreStoreProfileStore:
    """StoreProfileStoreProtocolの実Firestore接続実装(モジュールdocstring記載の
    8グループのみ)。
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

    def get_blocked_but_billing_owner_notified_at(
        self, store_id: str
    ) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # design.md 13節: 9節(suspension_reason)・11節(owner_email)と同じく
            # 接続エラーをProtocol契約上の「未設定」側(None)に合流させる安全側
            # フォールバック。ただし本フィールドは「未通知」判定にそのまま使われるため、
            # 9節・11節とは逆方向のリスク(通知の見送りではなく、二重送信)を受け入れる
            # 判断になる(13節の検討事項参照)。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("blockedButBillingOwnerNotifiedAt")

    def set_blocked_but_billing_owner_notified_at(
        self, store_id: str, value: Optional[str]
    ) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        self._doc_ref(store_id).set(
            {"blockedButBillingOwnerNotifiedAt": value}, merge=True
        )

    def get_plan(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # design.md 15節: InMemory実装の未設定時デフォルト(None=プラン未購入)と
            # 揃える安全側フォールバック。接続エラーの回だけ月間予約件数上限チェックが
            # 一時的に効かなくなる(トライアル中と同じ扱い)側に合流させる方が、誤って
            # 上限0相当の挙動になり有料プラン契約中の店舗の新規予約を全てブロックして
            # しまう事態より明らかに安全であり、9節・11節・13節と同じ基準に合致する。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("plan")

    def set_plan(self, store_id: str, plan: str) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        if plan not in PLAN_MONTHLY_BOOKING_LIMITS:
            raise ValueError(f"unknown plan: {plan!r}")
        self._doc_ref(store_id).set({"plan": plan}, merge=True)

    def all_store_ids(self) -> Iterable[str]:
        # design.md 26節: 唯一の呼び出し元list_blocked_but_billing_candidates()が
        # 結果を絞り込んだ上で自前でsorted()するため、stream()の返却順序
        # (ドキュメントID順保証なし)に依存しない。
        for snapshot in self._stores.stream():
            yield snapshot.id

    def get_menu_durations(self, store_id: str) -> dict:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # design.md 22節: 接続エラー時はInMemory実装の未設定時デフォルト(空dict)
            # と揃える。resolve_menu_duration()は空dict渡しでも未知メニュー時と同じ
            # Noneを返し、呼び出し元はNone判定を既存の「未登録メニュー」と同じ経路
            # (オーナー転送)に合流させるため、9節・15節と同じ「空へ合流=処理を止めて
            # 人手に回す」基準に合致する。
            return {}
        if not snapshot.exists:
            return {}
        return dict((snapshot.to_dict() or {}).get("menuDurations", {}))

    def set_menu_durations(self, store_id: str, menu_durations: dict) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        # design.md 22節: InMemory実装は呼び出しごとに辞書全体を置き換える契約の
        # ため、"menuDurations"フィールドを丸ごと置き換える(個別キーの差分マージは
        # 行わない)。
        self._doc_ref(store_id).set({"menuDurations": dict(menu_durations)}, merge=True)
