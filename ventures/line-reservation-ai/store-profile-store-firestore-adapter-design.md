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
  menu_durations・store_faq_info・all_store_ids)は引き続き次回候補として段階的に設計する。

## 5. onboarding_completion_messageグループ(2メソッド)

`is_onboarding_completion_message_sent`/`mark_onboarding_completion_message_sent`
(`store_profile_store.py` 129-133行目・246-252行目)を追加設計する。InMemory実装
(208行目・246-252行目)は`_onboarding_completion_message_sent: set[str]`への
membership判定・追加のみで、送信日時は保持しない(`is_X`はbool、`mark_X`は戻り値なし)。

```python
    def is_onboarding_completion_message_sent(self, user_id: str) -> bool:
        # Stripeグループ(2節)の get_stripe_customer_id 等とは異なり、接続エラーを
        # Noneに合流させる「安全側フォールバック」(3節)をここでは踏襲しない。
        # この判定は「初回設定完了メッセージを送ってよいか」の一回送信ゲートであり、
        # 呼び出し元 onboarding-settings-and-self-check-design.md の
        # maybe_send_onboarding_completion_message() 相当の処理は
        # is_X が False → 送信 → mark_X という一方向の流れしか持たない。
        # 接続エラーをFalse(未送信)に合流させると、一時的な接続障害のたびに
        # 既送信店舗へ再送してしまう(二重送信)。安全側は「送信をスキップしても
        # 事業上の損害は小さい」側であり、ここでは例外を呼び出し元に伝播させ、
        # 送信判定自体を保留させる。
        snapshot = self._doc_ref(user_id).get()
        if not snapshot.exists:
            return False
        return bool(
            (snapshot.to_dict() or {}).get("onboardingCompletionMessageSent", False)
        )

    def mark_onboarding_completion_message_sent(self, user_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        self._doc_ref(user_id).set(
            {"onboardingCompletionMessageSent": True}, merge=True
        )
```

- **例外方針の不統一を明文化**: 2節(Stripeグループ)・`firestore-provider-adapter-design.md`
  3節はいずれも「接続エラーは未設定側に安全に合流させる」方針だが、これは参照系
  (名前・IDの取得)や「無ければfalse扱いで問題ない」判定に限った方針であり、
  本グループのように「false→副作用(送信)→true固定」という一方向ゲートに同じ方針を
  適用すると二重送信リスクを生むことを本フェーズで発見した。例外を安全側に握り込む
  かどうかは、判定結果が生む副作用の可逆性(送信は不可逆、参照系は可逆)で分けるべき
  という基準を次回以降の設計にも適用する。
- `mark_onboarding_completion_message_sent`は`merge=True`の単純フィールド更新で、
  Stripeグループのような逆引きインデックス更新は不要(1節の方針どおり)。

## 6. (旧)次回候補

- 7節で`owner_is_following`グループに着手した。

## 7. owner_is_followingグループ(2メソッド)

`get_owner_is_following`/`set_owner_is_following`(`store_profile_store.py` 141-145行目・
265-274行目)を追加設計する。InMemory実装は`_owner_is_following: dict[str, bool]`への
単純な読み書きで、未設定時は`True`(フォロー中)をデフォルト値として返す
(265-269行目のコメント「安全側で『フォロー中』として扱う」)。

```python
    def get_owner_is_following(self, store_id: str) -> bool:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # InMemory実装の未設定時デフォルト(True)と揃える安全側フォールバック。
            # 本フィールドはblocked_but_billing_candidates.pyの候補抽出条件
            # 「owner_is_followingがFalse」の判定に使われるため、接続エラーをTrueに
            # 合流させることで、一時的な接続障害時に誤ってブロック候補として
            # 扱われること(=未読状態のオーナーへの通知処理が走ること)を避ける。
            # 5節で明文化した基準(副作用の可逆性で例外方針を分ける)に沿って判断すると、
            # 本フィールドの参照は「候補抽出条件の一部」であり、候補から漏れても
            # 次回バッチで再評価されるため可逆(5節のonboarding_completion_messageとは
            # 逆に、安全側=未設定側に合流させてよいケース)。
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
```

- **例外方針はStripeグループ(2節)側に合流**: 5節で発見した「副作用の可逆性で例外方針を
  分ける」基準に沿って判定すると、本グループは参照結果が候補抽出の入力にしかならず
  (`blocked_but_billing_candidates.py`は定期バッチで再評価されるため、1回の誤判定が
  恒久的な副作用を生まない)、2節(Stripeグループ)・`firestore-provider-adapter-design.md`
  3節と同じ「接続エラーは未設定側に安全に合流させる」方針を踏襲してよいと判断した。
- `set_owner_is_following`は逆引きインデックスを持たない単純フィールド更新で、
  2節のStripeグループのような付け替え時の旧インデックス削除は不要。

## 8. (旧)次回候補

- 9節で`suspension_reason`グループに着手した。

## 9. suspension_reasonグループ(2メソッド)

`get_suspension_reason`/`set_suspension_reason`(`store_profile_store.py` 147-153行目・
277-283行目)を追加設計する。InMemory実装は`_suspension_reasons: dict[str, Optional[str]]`
への単純な読み書きで、未設定時は`None`(未停止)をデフォルト値として返す(277-278行目の
dict.get挙動)。

```python
    def get_suspension_reason(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # InMemory実装の未設定時デフォルト(None=未停止)と揃える安全側フォールバック。
            # 本フィールドはcloud_function_process_event.pyの新規予約受付判定
            # (suspension_reasonがNone以外なら`new_booking_blocked_suspended`で
            # ブロック)に直接使われる。接続エラーをNoneに合流させなかった場合、
            # 一時的な接続障害のたびに正常稼働中(未停止)の全店舗の新規予約が
            # 誤ってブロックされてしまい、本来停止中でない店舗の顧客体験を損なう。
            # 本判定は予約リクエストごとに毎回再評価される(5節の一方向ゲートとは
            # 異なり可逆)ため、5節で明文化した基準(副作用の可逆性で例外方針を分ける)
            # に沿い、7節(owner_is_following)・2節(Stripeグループ)と同じ
            # 「接続エラーは未設定側に安全に合流させる」方針を適用してよいと判断した。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("suspensionReason")

    def set_suspension_reason(self, store_id: str, suspension_reason: Optional[str]) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        self._doc_ref(store_id).set(
            {"suspensionReason": suspension_reason}, merge=True
        )
```

- **owner_is_followingグループとの違い**: 7節は「候補抽出条件の一部」という間接的な
  参照だったが、本グループは`cloud_function_process_event.py`の予約受付可否を直接
  左右する判定である。それでも判定自体が予約リクエストごとに再評価される(一度きりの
  不可逆な送信ゲートではない)ため、5節の基準では「可逆」側に分類され、安全側
  フォールバックの適用対象であることを確認した。
- `set_suspension_reason`は逆引きインデックスを持たない単純フィールド更新で、2節の
  Stripeグループのような付け替え時の旧インデックス削除は不要。

## 10. 次回候補

- 残りのグループ(owner_user_id・owner_email・blocked_but_billing_owner_notified_at・
  plan・checkout_session_completed_event_time・menu_durations・store_faq_info・
  all_store_ids)のうち、次に着手しやすいのは`owner_email`
  (blocked-but-billing-owner-email-notification-design.mdのオーナー通知送信先フィールドで、
  送信自体はオーナー承認待ちの範囲外、フィールド読み書き設計のみ机上で進められる見込み)
  と判断する。
- 承認後は、`portal_session.py`・`checkout_session.py`・
  `onboarding-settings-and-self-check-design.md`の呼び出し側で`StoreProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する。
