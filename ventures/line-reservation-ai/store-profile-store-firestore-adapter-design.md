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
