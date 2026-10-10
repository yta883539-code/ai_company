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

> **訂正(フェーズ続き311監査、2026-10-10 17:00 UTC)**: 上記コード例のフィールド名
> `onboardingCompletionMessageSent`(boolean)は、`firestore-data-model.md`(1節、
> フェーズ続き155・本節より前に確定済み)が定義する正本フィールド
> `onboardingCompletionMessageSentAt`(Timestamp | null)と一致しない。本グループの
> 正式なFirestoreアダプタ設計は、正本フィールドに準拠し`SERVER_TIMESTAMP`・安全側
> フォールバック(接続エラーを未送信側に合流)を採用した
> `store-profile-store-firestore-adapter-design-onboarding-flag.md`(2026-10-08作成)
> を正とする。本節のコード例は結合実装時には参照せず、検討過程の記録としてのみ残す。
> 詳細は21節参照。ただし、直後の「例外方針の不統一を明文化」で述べる
> 「副作用の可逆性で例外方針を分ける」という一般原則そのものは7節以降で継続的に
> 参照される設計基準として引き続き有効であり、本訂正の対象外。

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

## 10. (旧)次回候補

- 11節で`owner_email`グループに着手した。

## 11. owner_emailグループ(2メソッド)

`get_owner_email`/`set_owner_email`(`store_profile_store.py` 153-157行目・286-294行目)を
追加設計する。InMemory実装は`_owner_emails: dict[str, str]`への単純な読み書きで、未設定時は
`None`をデフォルト値として返す(286-287行目のdict.get挙動)。`set_owner_email`は空文字列を
拒否する(`ValueError`、293行目)が、これはあくまで「設定する値」自体の検証であり、
「未設定(そもそも一度も呼ばれていない)」状態とは別である。

```python
    def get_owner_email(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # InMemory実装の未設定時デフォルト(None)と揃える安全側フォールバック。
            # 本フィールドはblocked_but_billing_owner_email_notification.pyの
            # select_new_blocked_but_billing_candidates_for_email_notification()から
            # `and store.get_owner_email(store_id)`という真偽値判定のみに使われ、
            # Noneを返すとその店舗は単に今回の送信対象候補から外れるだけである。
            # 本バッチはblocked_but_billing_owner_notified_atが未設定の間は毎回
            # 再評価される(9節の基準における「可逆」判定)ため、接続エラーの回だけ
            # 通知が1サイクル遅れる(=未設定の店舗と同じ扱いになる)のは安全側であり、
            # 誤って送信してしまう・誤って停止させてしまうよりはるかに望ましい。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("ownerEmail")

    def set_owner_email(self, store_id: str, owner_email: str) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        if not owner_email:
            raise ValueError("owner_email must be a non-empty string")
        self._doc_ref(store_id).set({"ownerEmail": owner_email}, merge=True)
```

- **「未設定」と「設定済みだが接続エラー」を区別しない設計判断**: `set_owner_email`は
  空文字列を拒否するため、一度正しく設定された店舗の`ownerEmail`が後から空になることは
  正常系では起こらない。しかし接続エラー時に例外を伝播させず`None`に合流させる設計上、
  呼び出し側(`select_new_blocked_but_billing_candidates_for_email_notification`)からは
  「本当にオーナーメールが未登録」なのか「登録済みだが今回の接続が失敗した」のかを
  区別できなくなる。本グループは9節(suspension_reason)と異なり新規予約のブロック可否のような
  即時の顧客影響はなく、最悪ケースでも「通知が1回遅れる」程度の影響に留まるため、
  区別をつけない単純なフォールバックで十分と判断した。将来、通知の遅延自体を監視したい
  要件が生じた場合は、例外発生時のみログに記録する(戻り値は変えない)方式を追加検討する。
- `set_owner_email`は2節(Stripeグループ)のような逆引きインデックスを持たない単純フィールド
  更新であり、付け替え時の旧インデックス削除は不要(9節のsuspension_reasonと同型)。

## 12. (旧)次回候補

- 13節で`blocked_but_billing_owner_notified_at`グループに着手した。

## 13. blocked_but_billing_owner_notified_atグループ(2メソッド)

`get_blocked_but_billing_owner_notified_at`/`set_blocked_but_billing_owner_notified_at`
(`store_profile_store.py` 159-165行目・297-306行目)を追加設計する。本フィールドは
`blocked_but_billing_owner_email_notification.py`の
`select_new_blocked_but_billing_candidates_for_email_notification()`(91行目)が
「まだ通知していない」かを判定する冪等性フラグであり、同ファイルの
`clear_blocked_but_billing_owner_notified_at()`(143行目)は専用の`clear_*`メソッドを
持たず`set_blocked_but_billing_owner_notified_at(store_id, None)`で表現する
(aircon-pasha 11節と同じ設計、course-set-pasha 9節は専用`clear_*`を持つ点が差分)。
InMemory実装は`_blocked_but_billing_owner_notified_at: dict[str, Optional[str]]`への
単純な読み書きで、値は`datetime`ではなく`Optional[str]`(呼び出し元
`send_blocked_but_billing_owner_email_notifications()`が`notified_at: str`引数で
受け取った文字列をそのまま書き込む、148-157行目)である点が、同種のaircon-pasha・
course-set-pashaの`notified_at`系フィールド(いずれも`datetime`型)との差分になる。

```python
    def get_blocked_but_billing_owner_notified_at(
        self, store_id: str
    ) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # 9節(suspension_reason)・11節(owner_email)と同じく接続エラーを
            # Protocol契約上の「未設定」側(None)に合流させる安全側フォールバック。
            # ただし本フィールドは「未通知」判定にそのまま使われるため、9節・11節とは
            # 逆方向のリスク(通知の見送りではなく、二重送信)を受け入れる判断になる
            # (13節の検討事項参照)。
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
```

- **`None`書き込みによる`clear_*`表現の整合性**: InMemory版の`set_*`は未設定時の
  キー不在と`None`明示設定を区別しないdict代入であり、`get_*`も`dict.get(store_id)`
  (デフォルト`None`)のため、両状態の観測結果は一致する。Firestore側も`merge=True`の
  `None`書き込みでフィールドが`null`として残るのみで削除されないが、`get_*`は`null`も
  未設定もいずれも`None`として返すため、InMemory版の挙動と一致する
  (11節・course-set-pasha 9.3節と同じ結論)。
- **例外時に`None`を返すことで二重送信リスクを受け入れる判断**: `select_new_
  blocked_but_billing_candidates_for_email_notification()`は「本フィールドが`None`」を
  「未通知」として候補抽出条件に使う(91行目)ため、接続エラー時に`None`へフォールバック
  すると、既に通知済みの店舗が誤って再度候補に含まれ、メールが二重送信される可能性がある。
  これは9節(suspension_reason、新規予約ブロック可否という即時の顧客影響がある不可逆な
  誤判定を避ける目的)・11節(owner_email、通知を誤って遅らせる方向の安全側)とは逆方向の
  安全側判断だが、course-set-pasha 9.3節・aircon-pashaが同種の`notified_at`系フィールドで
  既に確立した「通知を誤って止める(二度と送られなくなる)より、まれに再送される方が実害が
  小さい」という横展開一貫した方針であり、本venture固有の事情で判断を変える理由はないため
  同じ結論を採用する。なお実際の二重送信は、`email_sender.send()`成功後にのみ本フィールドを
  書き込む`send_blocked_but_billing_owner_email_notifications()`側の設計(164-166行目)により、
  接続エラーが起きた回の実行でメール送信自体が複数回成功しない限り発生しない(本フィールドの
  読み取りエラーと書き込み側のメール送信は独立した操作のため、読み取りエラーの発生頻度が
  即座に二重送信頻度に直結するわけではない)。
- `set_blocked_but_billing_owner_notified_at`は2節(Stripeグループ)のような逆引き
  インデックスを持たない単純フィールド更新であり、付け替え時の旧インデックス削除は不要
  (9節・11節と同型)。

## 14. 次回候補

- 残りのグループ(owner_user_id・plan・checkout_session_completed_event_time・
  menu_durations・store_faq_info・onboarding_completion_message・all_store_ids)のうち、
  次に着手しやすいのは`plan`(`get_plan`/`set_plan`、`checkout.session.completed`受信時に
  購入プランを記録する単純フィールドで、9節・11節・13節と同じ`_doc_ref(store_id)`の上に
  素直に実装できる見込み)と判断する。
- 承認後は、`portal_session.py`・`checkout_session.py`・
  `onboarding-settings-and-self-check-design.md`の呼び出し側で`StoreProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。

## 15. planグループ(2メソッド)

`get_plan`/`set_plan`(`store_profile_store.py` 167-171行目・308-317行目)を追加設計する。
InMemory実装は`_plans: dict[str, str]`への単純な読み書きで、未設定時は`None`(トライアル中・
プラン未購入)をデフォルト値として返す(308-309行目のdict.get挙動)。`set_plan`は
`PLAN_MONTHLY_BOOKING_LIMITS`にないプラン名を拒否する(`ValueError`、314-315行目)ため、
`get_plan`が返す値は常に`None`かこの辞書の既知キーのいずれかであるという`resolve_
monthly_booking_limit()`(388-417行目)側の前提は、Firestore版でも値の出し入れを
そのまま委譲するだけで自動的に保たれる。

```python
    def get_plan(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # InMemory実装の未設定時デフォルト(None=プラン未購入)と揃える安全側
            # フォールバック。本フィールドはresolve_monthly_booking_limit()経由で
            # ConversationFlowStateMachine構築時の月間予約件数上限に使われ、Noneは
            # 「上限機能を無効にする」側に解釈される(store_profile_store.py
            # 396-399行目のdocstring)。接続エラーの回だけ上限チェックが一時的に
            # 効かなくなる(=トライアル中と同じ扱いになる)のは、誤って上限0相当の
            # 挙動になり有料プラン契約中の店舗の新規予約を全てブロックしてしまう
            # 事態より明らかに安全であり、9節(suspension_reason)・13節
            # (blocked_but_billing_owner_notified_at)のいずれとも異なる具体的な
            # 誤り方だが、同じ「顧客体験を損なう側より実害の小さい側に合流させる」
            # 基準には合致する。本判定はイベント受信ごとに`build_conversation_flow_
            # state_machine_for_store()`から毎回再構築される(102行目、
            # conversation_event_processor_assembly.py)ため、5節の基準における
            # 「可逆」判定にも当たる。
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
```

- **`set_plan`の検証は接続前に完結する**: `plan not in PLAN_MONTHLY_BOOKING_LIMITS`の
  チェックはFirestoreへの書き込み呼び出し自体より前に行われるため、InMemory版・
  Firestore版のいずれも不正なプラン名を一度も永続化層へ渡さずに`ValueError`を送出する
  (`subscription_plan_sync.py`115行目の`store.get_plan(store_id) != plan`比較が、
  書き込み済みの`plan`が必ず既知キーである前提に依存できる)。
- `set_plan`は2節のStripeグループのような逆引きインデックスを持たない単純フィールド更新
  であり、付け替え時の旧インデックス削除は不要(9節・11節・13節と同型)。
- フィールド名は`checkout_session.py`の`metadata={"plan": plan}`(88・112行目)・
  `prototype/test_store_profile_store.py`の既存テストケースと同じ`"plan"`をそのまま
  Firestoreのキー名に採用し、camelCase変換は行わない(元が単一の英単語のため9節
  〈suspensionReason〉等のような複合語キャメルケース化は不要)。

## 16. (旧)次回候補

- 残りのグループ(owner_user_id・checkout_session_completed_event_time・
  menu_durations・store_faq_info・onboarding_completion_message・all_store_ids)のうち、
  次に着手しやすいのは`checkout_session_completed_event_time`
  (`get_checkout_session_completed_event_time`/`set_checkout_session_completed_event_time`、
  aircon-pashaの同名グループ〈フェーズ296〉で既に確立済みのイベント配信順序ガード設計を
  横展開できる見込み)と判断する。
- 承認後は、`portal_session.py`・`checkout_session.py`・
  `onboarding-settings-and-self-check-design.md`の呼び出し側で`StoreProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。

## 17. checkout_session_completed_event_timeグループ(2メソッド)

`get_checkout_session_completed_event_time`/`set_checkout_session_completed_event_time`
(`store_profile_store.py` 173-181行目・319-329行目)を追加設計する。InMemory実装は
`_checkout_session_completed_event_time: dict[str, datetime]`への単純な読み書きで、
未設定時は`None`を返す。Protocol上の引数名は他グループと異なり`user_id`だが、2節で
確認した通り本venture(line-reservation-ai)では`store_id`と同一の識別子(LINEの
`user_id`がそのまま`stores/{storeId}`のドキュメントID)であり、`_doc_ref()`の扱いは
15節までと変わらない。

```python
    def get_checkout_session_completed_event_time(
        self, user_id: str
    ) -> Optional[datetime]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # handle_checkout_session_completed()(checkout-session-completed-event-
            # order-guard-design.md)は本フィールドが未設定(None)の場合、配信順序
            # ガードを行わず無条件にcheckout.session.completedイベントを適用する
            # (後方互換パス)。接続エラーをNoneへ合流させると、まれに古いイベントの
            # 再送が新しいstripe_customer_id・planを誤って上書きする可能性があるが、
            # 逆に「ガードが効いてイベントを一切適用できなくなる」(=Checkout完了後も
            # 永久にstripe_customer_idが紐付かない)方が顧客体験への実害が大きいため、
            # 9節(suspension_reason)・15節(plan)と同じ「処理を止めない方向」の
            # 安全側フォールバックを適用する。aircon-pasha 17節が同種の`event_time`系
            # 4フィールドで確立した「ガード自体は無条件適用側が安全側」という結論とも
            # 一致する。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("checkoutSessionCompletedEventTime")

    def set_checkout_session_completed_event_time(
        self, user_id: str, event_time: datetime
    ) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        self._doc_ref(user_id).set(
            {"checkoutSessionCompletedEventTime": event_time}, merge=True
        )
```

- **フィールド名はcamelCase化する**: 9節(`suspensionReason`)・11節(`ownerEmail`)と同じ
  方針で、複合語である`checkout_session_completed_event_time`は`checkoutSessionCompleted
  EventTime`に変換する。1節の既存グループが`stores/{storeId}`の既存フィールド
  (`stripeCustomerId`等)に合わせてcamelCaseを使っている一貫性を保つ。
- **read-modify-write競合はない**: `handle_checkout_session_completed()`
  (store_profile_store.py 481行目以降)は1回のイベント処理内で
  `get_checkout_session_completed_event_time`→(ガード判定)→
  `set_stripe_customer_id`/`set_plan`→`set_checkout_session_completed_event_time`の順に
  呼ぶが、各呼び出しは独立したAPI呼び出しであり、本グループ自体がaircon-pasha 17節の
  event_time系4フィールドと同型の「他フィールドとの比較・計算を伴わない単純な値の
  読み書き」であるため、13節・15節までと同じ理由で単一フィールドの競合リスク対象外と
  判断する(stale判定自体の精度は呼び出し元のStripe Webhook配信順序に依存するが、
  これは本アダプタの設計範囲外)。
- `set_checkout_session_completed_event_time`は`set_plan`(15節)と同じく逆引き
  インデックスを持たない単純フィールド更新であり、付け替え時の旧インデックス削除は
  不要(9節・11節・13節・15節と同型)。

## 18. (旧)次回候補

- 残りのグループ(owner_user_id・menu_durations・store_faq_info・
  onboarding_completion_message・all_store_ids)のうち、次に着手しやすいのは
  `owner_user_id`(`get_owner_user_id`/`set_owner_user_id`、9節〈suspension_reason〉・
  11節〈owner_email〉と同じ`stores/{storeId}`上の単純フィールドで、新規パターンの
  検討が不要な見込み)と判断する。
- 承認後は、`portal_session.py`・`checkout_session.py`・
  `onboarding-settings-and-self-check-design.md`の呼び出し側で`StoreProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。

## 19. owner_user_idグループ(2メソッド)

`get_owner_user_id`/`set_owner_user_id`(`store_profile_store.py` 135-138行目・254-262行目)を
追加設計する。InMemory実装は`_owner_user_ids: dict[str, str]`への単純な読み書きで、未設定時は
`None`(オーナー未登録)をデフォルト値として返す(254-255行目のdict.get挙動)。

```python
    def get_owner_user_id(self, store_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # InMemory実装の未設定時デフォルト(None=オーナー未登録)と揃えるが、本
            # グループは9節(suspension_reason)・15節(plan)・17節
            # (checkout_session_completed_event_time)とは安全側の方向が逆になる点が
            # 特徴的である。verify_checkout_authorization()(checkout_session.py
            # 186-199行目)は`get_owner_user_id`がNoneの場合、認可チェック自体を
            # `AUTHORIZATION_DENIED_OWNER_NOT_SET`で拒否する(=Checkout Session作成を
            # 続行させない)設計になっており、接続エラーをNoneへ合流させることは
            # 「認可不明の場合は決済を止める」というfail-closedの挙動に自然に一致する。
            # 9節等では「Noneへ合流=処理を止めない」が安全側だったのに対し、本グループは
            # 「Noneへ合流=処理を止める」側が安全側になる、店舗プロフィールストア内で
            # 唯一決済の認可判定に直結するフィールドであることが理由である。したがって
            # 新たな方針判断は不要で、InMemory実装の既定動作をそのまま委譲するだけで
            # verify_checkout_authorization()が意図する安全側の挙動が保たれる。
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
```

- **fail-closedが自然に成り立つ理由**: `verify_checkout_authorization()`は
  `owner_user_id is None`と「`owner_user_id`が`requester_user_id`と不一致」のいずれも
  同じ`authorized=False`として扱う(200-204行目)。接続エラー時に例外を伝播させず
  `None`へ合流させても、この2つの拒否理由(`AUTHORIZATION_DENIED_OWNER_NOT_SET`)に
  吸収されるだけで、誤って決済を許可してしまう経路は生じない。
- **`_known_store_ids`への追加はこのグループの設計対象外**: InMemory実装の
  `set_owner_user_id`は`self._known_store_ids.add(store_id)`も行う(263行目)が、これは
  `all_store_ids()`(195・354-360行目)がFirestoreでは別実装(コレクション自体を走査する
  想定)になる見込みの前提に基づくInMemory固有の付随処理であり、本グループの
  Firestoreアダプタ設計では扱わない(残課題として「all_store_ids」グループに持ち越す)。
- フィールド名は9節(`suspensionReason`)・11節(`ownerEmail`)・17節
  (`checkoutSessionCompletedEventTime`)と同じ方針でcamelCase化し`ownerUserId`とした。
- `set_owner_user_id`は逆引きインデックスを持たない単純フィールド更新であり、2節の
  Stripeグループのような付け替え時の旧インデックス削除は不要(9節・11節・13節・15節・
  17節と同型)。

## 20. 次回候補(2026-10-10フェーズ続き311時点で誤り訂正済み。21節参照)

- ~~残りのグループ(menu_durations・store_faq_info・onboarding_completion_message・
  all_store_ids)のうち、次に着手しやすいのは`onboarding_completion_message`~~
  → 誤り。`onboarding_completion_message`グループは本ファイル5節で既に設計済みであり、
  かつ正本設計は`store-profile-store-firestore-adapter-design-onboarding-flag.md`
  (2026-10-08作成)として独立に存在する。本節のこの記載は、5節の存在を見落としたまま
  書かれたものであり、フェーズ続き306〜309のREADME進捗ログでも同じ誤りがそのまま
  繰り返されていた(21節参照)。残りグループは実際には
  **menu_durations・store_faq_info・all_store_ids の3件**。
- `all_store_ids`はInMemory実装の`_known_store_ids`集合を使わず、Firestoreの
  `stores`コレクション自体をクエリする設計になる見込みで、他グループとは異なる検討
  (ページネーション・インデックス戦略等)が必要になるため、残りグループの中では最後に
  着手する。次に着手しやすいのは`menu_durations`または`store_faq_info`と見込む
  (いずれも未着手のため、着手時に単純なget/set型か複合構造かを個別に確認する)。
- 承認後は、`portal_session.py`・`checkout_session.py`・
  `onboarding-settings-and-self-check-design.md`の呼び出し側で`StoreProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。

## 21. 次回候補の誤り発見・是正(フェーズ続き311監査、2026-10-10 17:00 UTC)

- **発見した問題**: 本ファイル20節の「次回候補」が`onboarding_completion_message`
  グループを繰り返し未着手として挙げていたが、実際には
  - 本ファイル5節で`is_onboarding_completion_message_sent`/
    `mark_onboarding_completion_message_sent`の設計が既に完了していた(Stripeグループに
    続く2番目のグループとして早い段階で設計済み)、
  - さらに独立したファイル`store-profile-store-firestore-adapter-design-onboarding-flag.md`
    (2026-10-08作成)でも同じ2メソッドの設計が重複して行われていた。
  この2つの設計は**互いに矛盾**しており、
  - 5節: フィールド名`onboardingCompletionMessageSent`(boolean)・例外を握り潰さず
    呼び出し元に伝播させる方針。
  - 独立ファイル: フィールド名`onboardingCompletionMessageSentAt`(Timestamp、
    `SERVER_TIMESTAMP`使用)・接続エラーを「未送信」に安全側で合流させる方針。
  いずれも`firestore-data-model.md`(1節)の定義(`onboardingCompletionMessageSentAt`、
  フェーズ続き155で確定)と照合すると、独立ファイルの設計のみがフィールド名・型とも
  一致する。
- **是正**: 独立ファイル(`store-profile-store-firestore-adapter-design-onboarding-flag.md`)
  を本グループの正本設計として確定し、5節には訂正注記を追加した(5節末尾参照)。
  コード(`prototype/store_profile_store.py`のInMemory実装)自体はどちらの設計とも
  独立した簡略実装(真偽値のみの`set[str]`)であり、今回の訂正はFirestore接続アダプタの
  設計文書間の矛盾の整理に限定されるため、コード変更は発生しない。
- **根本原因の推測**: README.mdのフェーズ続き306〜309の「次回候補」記述が、
  フェーズ続き305の時点で一度生成された文言をほぼそのまま複製・継承し続け、
  各フェーズの着手時に候補の妥当性(既に別の形で対応済みでないか)を再検証しないまま
  引き継がれていたことが原因と考えられる。本ventureの他の「次回候補」記述についても
  同種の陳腐化が起きていないか、次回以降のフェーズで順次点検する価値がある。
- **回帰確認**: ドキュメントのみの変更のためコード・テストへの影響はないが、念のため
  `python3 -m unittest discover -s prototype -p "test_*.py"`(906件)・
  `python3 schema/validate_test_cases.py`(28件)を再実行し、いずれもパスすることを
  確認した(件数に変更なし)。
- **次回候補**: (1)承認待ち事項(顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)
  がオーナーから承認された場合はその着手を最優先、(2)残りグループ
  `menu_durations`・`store_faq_info`のいずれかの実Firestore接続アダプタ設計、
  (3)他venture・アイデア領域の前進、(4)他venture(course-set-pasha・aircon-pasha・
  kura-pasha・forklift-pasha)の「次回候補」記述にも同種の陳腐化(既に対応済みの項目を
  未着手として繰り返し記載)がないかの点検。
