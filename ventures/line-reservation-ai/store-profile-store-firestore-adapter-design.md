# StoreProfileStoreProtocol の実Firestore接続アダプタ設計(Stripe顧客IDグループ)

## 1. 背景・範囲

`prototype/store_profile_store.py`の`StoreProfileStoreProtocol`は`stores/{storeId}`
ドキュメントを読み書きする包括的Protocol(get/set合計18メソッド超)だが、実Firestore
接続アダプタはまだ存在しない。本ventureでは`firestore-provider-adapter-design.md`
(フェーズ続き296〜)が`StoreNameProviderProtocol`/`RegionNameProviderProtocol`
(`stores/{storeId}`の`businessName`・`regionName`読み取りのみ)を先に設計済みだが、
`StoreProfileStoreProtocol`自体は未着手だった。

aircon-pasha(フェーズ295〜)・kura-pasha(フェーズ209〜)が広い`UserProfileStoreProtocol`
に対して採用した「最小の関連グループから段階的に着手する」方針を踏襲し、本フェーズは
以下のグループに限定する。

- **Stripeグループ(3メソッド)**: `set_stripe_customer_id`/`get_stripe_customer_id`/
  `get_store_id_by_stripe_customer_id`。`stripe_customer_id`の順引き・逆引きという
  単一の関心に閉じており、`checkout-session-plan-selection-design.md`・
  `portal-session-provider-design.md`の両方から参照される独立度の高いグループ。

他のグループ(owner_user_id・owner_is_following・suspension_reason・owner_email・
blocked_but_billing_owner_notified_at・plan・checkout_session_completed_event_time・
menu_durations・store_faq_info・onboarding_completion_message・all_store_ids)は次回候補
とする(4節)。

## 2. 設計

`stores/{storeId}`は`store_id`(= LINEの`user_id`)をドキュメントIDとする1ドキュメント
1エントリ構造。aircon-pashaの`FirestoreUserProfileStore`(5節)と同じく、逆引きは
専用コレクション`stripe_customer_index/{stripe_customer_id}`への同時書き込みで対応し、
`WriteBatch`で原子性を確保する。

aircon-pashaの設計は「旧customer_idからの付け替え時に旧インデックスを削除する処理は
次回候補」として見送ったが、本venture(line-reservation-ai)の
`InMemoryStoreProfileStore.set_stripe_customer_id()`(store_profile_store.py 223-239行目)
は既に付け替え時の旧インデックス削除を実装済みのため、実Firestoreアダプタも同じ契約
(付け替え時に旧`stripe_customer_index`ドキュメントを削除する)を満たす設計とする
(InMemory実装と実装の間で契約が食い違うことを避ける)。

```python
class FirestoreStoreProfileStore:
    """StoreProfileStoreProtocolの実Firestore接続実装(Stripeグループのみ。
    他グループは次回候補、4節)。
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
            # InMemoryStoreProfileStoreの付け替え時挙動(228-237行目)と契約を合わせる。
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
```

## 3. 検討事項

- **付け替え時の読み取り1回追加**: `set_stripe_customer_id`は旧IDを判定するため
  `get_stripe_customer_id`を内部で1回呼ぶ(書き込み前の読み取り1回+バッチ書き込み)。
  Stripe Webhook経由の呼び出し頻度(`customer.subscription.*`イベント)は
  `firestore-traffic-cost-estimate.md`の想定トラフィックの範囲内であり、追加コストは
  無視できると判断した。
- **`merge=True`固定**: `stores/{storeId}`ドキュメントは他の多数のフィールド
  (businessName・regionName・menuDurations等)を同じドキュメントに持つため、
  フィールド単位の部分更新(`merge=True`)を全グループで統一する方針とする
  (aircon-pashaの`save()`のみ`merge`無し、という例外は本ventureの`StoreProfileStoreProtocol`
  には`save()`相当の一括新規作成メソッドが無いため該当しない)。
- **例外方針**: `firestore-provider-adapter-design.md`3節と同じ安全側フォールバック
  (接続エラー・権限エラーはProtocol契約上の「未設定」側に合流)を踏襲。
- **依存ライブラリ**: `google-cloud-firestore`を想定し、`firestore_client`を
  コンストラクタ注入する(既存設計と同じくクライアントの具体型には依存しない)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はオーナー承認待ち(pending-approval.md
  参照)のため、本設計のコードは承認後の結合実装フェーズまでコミットしない。
- 残りのグループ(owner_user_id・owner_is_following・suspension_reason・owner_email・
  blocked_but_billing_owner_notified_at・plan・checkout_session_completed_event_time・
  menu_durations・store_faq_info・onboarding_completion_message・all_store_ids)は
  引き続き次回候補として段階的に設計する。次に着手しやすいのは
  `is_onboarding_completion_message_sent`/`mark_onboarding_completion_message_sent`
  (booleanフラグ1件のみで依存関係が薄い)と判断する。
- 承認後は、`portal_session.py`・`checkout_session.py`等の呼び出し側で
  `StoreProfileStoreProtocol`実装注入箇所に本クラスのインスタンスを渡すだけで
  差し替えが完了する設計になっていることを、結合実装時に確認する。
