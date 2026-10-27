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

## 4. 残課題・次回候補(2026-10-25 03:00 UTCフェーズ続き342で訂正)

- 〔訂正〕本節は元々「本設計のコードは承認後の結合実装フェーズまでコミットしない」と
  記載していたが、本venture自身のfirestore-provider-adapter-design.md(フェーズ続き340、
  `FirestoreStoreDocumentProvider`)や、kura-pasha・course-set-pasha・aircon-pasha・
  forklift-pashaの各Firestoreアダプタが、実GCP接続なしの最小インターフェース(duck
  typing)実装として既にコード化済みであることを踏まえると、本クラスも同じ方針で
  コード化してよい(実Firestoreプロジェクト・GCPアカウントの開設待ちは、実クライアント
  を注入する結合実装の段階でのみ関係し、Protocol準拠コード自体の作成を妨げない)。
  この訂正に基づき、フェーズ続き342でStripeグループ(本節、3メソッド)・
  owner_is_followingグループ(7節、2メソッド)を`prototype/firestore_store_profile_store.py`
  として実コード化した(テスト16件追加、`test_firestore_store_profile_store.py`)。
  続いてフェーズ続き343で、19節が既に設計していた`get_owner_user_id`/
  `set_owner_user_id`(owner_user_idグループ、2メソッド)を同ファイルへ追加実コード化
  した(19節のコード例をそのまま転記、テスト6件追加)。フェーズ続き344で9節
  (suspension_reasonグループ、2メソッド)を追加実コード化した(テスト6件追加)。
  フェーズ続き345で11節(owner_emailグループ、2メソッド)を追加実コード化した
  (11節のコード例をそのまま転記、テスト6件追加、992→998件)。
  フェーズ続き346で13節(blocked_but_billing_owner_notified_atグループ、2メソッド)を
  追加実コード化した(13節のコード例をそのまま転記、テスト6件追加、998→1004件)。
  フェーズ続き351で15節(planグループ、2メソッド)を追加実コード化した(15節のコード
  例をそのまま転記、テスト7件追加、1004→1011件)。
  フェーズ続き352で26節(all_store_idsグループ、1メソッド)を追加実コード化した
  (26.2節のコード例をそのまま転記、テスト4件追加、1011→1015件)。
- 残りのグループ(checkout_session_completed_event_time・menu_durations・
  store_faq_info・onboarding_completion_message)は
  設計(各節)は完了済みだが実コード化は次回候補として残る。いずれも本節が訂正した
  通り、実Firestoreプロジェクト・GCPアカウントの開設(オーナー承認待ち)を待たずに
  実コード化できる(承認待ちは実クライアントを注入する結合実装の段階でのみ関係する)。

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
- **次回候補(2026-10-11フェーズ続き312時点で(2)着手済み。22節参照)**: (1)承認待ち事項
  (顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)がオーナーから承認された場合は
  その着手を最優先、(2)~~残りグループ`menu_durations`・`store_faq_info`のいずれかの実
  Firestore接続アダプタ設計~~ → 22節で`menu_durations`グループを設計済み、
  (3)他venture・アイデア領域の前進、(4)他venture(course-set-pasha・aircon-pasha・
  kura-pasha・forklift-pasha)の「次回候補」記述にも同種の陳腐化(既に対応済みの項目を
  未着手として繰り返し記載)がないかの点検。

## 22. menu_durationsグループ(2メソッド)(フェーズ続き312、2026-10-11 00:00 UTC)

`get_menu_durations`/`set_menu_durations`(`store_profile_store.py` 331-341行目)を追加設計
する。これまでの9・11・13・15・17・19節のグループはいずれも単一スカラー値(文字列・真偽値・
日時)の読み書きだったが、本グループは唯一「`{メニュー名: 所要時間(分)}`のフラットな辞書」を
値とする最初の複合構造グループである(20節で店舗FAQグループと並べて残課題とされていたうちの
片方)。InMemory実装は呼び出しごとに辞書全体を置き換える契約で、未設定時は空dictを返す
(331-335行目のdict.get既定値、`conversation-event-processor-assembly-design.md`準拠で
`ConversationEventProcessor.__init__`の`menu_durations`引数が`None`非許容のため)。

```python
    def get_menu_durations(self, store_id: str) -> dict:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # 接続エラー時はInMemory実装の未設定時デフォルト(空dict)と揃える。
            # resolve_menu_duration()(cloud_function_process_event.py 425-438行目)は
            # 空dict渡しでも未知メニュー時と同じNoneを返し、呼び出し元
            # (_handle_new_booking_menu_resolution相当、1035-1040行目)はNone判定を
            # 既存の「未登録メニュー」と同じ経路(_notify_owner()によるオーナー転送)に
            # 合流させる。接続エラーの回だけ誤った所要時間で候補検索を進めてしまう
            # (顧客に誤った予約時間枠を提示する)よりも、人手のオーナー対応に切り替わる
            # 側が明らかに安全であり、9節・15節と同じ「Noneまたは空へ合流=処理を止めて
            # 人手に回す」基準に合致するため、新たな分岐の追加は不要である。
            return {}
        if not snapshot.exists:
            return {}
        return dict((snapshot.to_dict() or {}).get("menuDurations", {}))

    def set_menu_durations(self, store_id: str, menu_durations: dict) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        # InMemory実装(337-340行目)は呼び出しごとに辞書全体を置き換える(個別キーの
        # 差分マージではない)契約のため、Firestore側もset(merge=True)がトップレベル
        # フィールド単位でのみ浅いマージを行う(ネストしたmapフィールドの値自体は丸ごと
        # 置き換わる)標準挙動のまま、"menuDurations"フィールドを丸ごと置き換える形で
        # 契約を一致させる。個別メニューキーのみを更新したい場合でも、呼び出し側が
        # 事前に`get_menu_durations()`で現在値を読み出してから更新後の全体dictを渡す
        # 運用とする(本メソッドの中では差分マージを行わない)。
        self._doc_ref(store_id).set({"menuDurations": dict(menu_durations)}, merge=True)
```

- **フラット辞書のまま1フィールドに格納する**: メニュー数は店舗ごとに数件〜数十件程度
  (`conversation-event-processor-assembly-design.md`の想定顧客規模)であり、サブ
  コレクション化(`stores/{storeId}/menus/{menuName}`のような1メニュー1ドキュメント
  構造)によるクエリ・ページネーションの必要性は無いと判断し、9・11・13・15・17・19節と
  同じ単一ドキュメント内のフィールドとして設計する。
- **フィールド名**は9節(`suspensionReason`)等と同じ方針でcamelCase化し`menuDurations`
  とした。メニュー名自体(dictのキー)は日本語文字列のままFirestoreのmapキーとして
  格納し、変換は行わない(Firestoreのmapキーはドット・チルダ等一部記号を除けば任意の
  文字列を許容するため、カット・カラー等の日本語メニュー名はそのまま使える)。
- **`store_faq_info`グループは対象外**: 20節の想定どおり着手時に構造を確認した結果、
  `store_faq_info`は`parking`/`address`/`payment_methods`/`hours`/`menu`等キーごとに
  型が異なる(文字列・ネストしたdict等)不均一な構造(`cloud_function_process_event.py`
  1254-1276行目)であり、`menu_durations`のような単純なフラット辞書とは異なる個別の
  設計検討(キーごとに異なる既定値・省略時の挙動の整理)が必要なため、本フェーズでは
  着手せず次回候補として残す。

## 23. 次回候補(フェーズ続き312時点)

- (1)承認待ち事項(顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)がオーナーから
  承認された場合はその着手を最優先。
- (2)残りグループ`store_faq_info`(キーごとに型が異なる不均一構造、22節で後回しと判断した
  理由を踏まえてキーごとの既定値設計から着手する)・`all_store_ids`(20節のとおり
  Firestoreの`stores`コレクション自体をクエリする設計になる見込みで最後に着手する)の
  実Firestore接続アダプタ設計。
- (3)他venture・アイデア領域の前進。
- (4)他venture(course-set-pasha・aircon-pasha・kura-pasha・forklift-pasha)の「次回候補」
  記述にも21節で見つかった同種の陳腐化(既に対応済みの項目を未着手として繰り返し記載)が
  ないかの点検(21節から持ち越し)。

## 24. store_faq_infoグループ(2メソッド)(フェーズ続き313、2026-10-11 08:00 UTC)

`get_store_faq_info`/`set_store_faq_info`(`store_profile_store.py` 189-193行目・
343-352行目)を追加設計する。23節(2)で「キーごとに型が異なる不均一構造のため
個別検討が必要」と見込んでいたが、着手して`InMemoryStoreProfileStore`の実装
(343-352行目)を確認した結果、ストア自身は`store_faq_info`の中身(`parking`が
`{"capacity": ...}`のネストdict、`address`が文字列、`payment_methods`が
リスト、`hours`がネストdict、`menu`がリスト等)を一切解釈せず、22節の
`menu_durations`と同じく「丸ごと受け取った辞書をそのまま格納し、丸ごと返す」
という不透明な(opaque)契約になっていることが分かった。キーごとの既定値・
省略時の挙動の解釈は、読み出し側の`cloud_function_process_event.py`
1254-1276行目(`_handle_faq`相当、各トピックごとに`.get("parking")`等で
存在確認してから分岐)が担っており、ストア層・Firestoreアダプタ層の責務では
ない。したがって22節で見込んだような個別検討は不要で、22節の`menu_durations`
設計をそのまま転用できると結論した。

```python
    def get_store_faq_info(self, store_id: str) -> dict:
        try:
            snapshot = self._doc_ref(store_id).get()
        except Exception:
            # 接続エラー時はInMemory実装の未設定時デフォルト(空dict)と揃える。
            # cloud_function_process_event.py 1254-1276行目の各トピック分岐は
            # いずれも`.get(キー)`がFalsyなら「未登録」として扱い、resolved:false
            # (1279行目付近)でオーナー転送経路に合流させるため、22節の
            # menu_durationsと同じ「空に合流=処理を止めて人手に回す」基準に
            # 合致し、新たな分岐の追加は不要である。
            return {}
        if not snapshot.exists:
            return {}
        return dict((snapshot.to_dict() or {}).get("storeFaqInfo", {}))

    def set_store_faq_info(self, store_id: str, store_faq_info: dict) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        # InMemory実装(348-352行目)は呼び出しごとに辞書全体を置き換える契約
        # (個別キーの差分マージではない)ため、22節のmenu_durationsと同じく
        # Firestore側も"storeFaqInfo"フィールドを丸ごと置き換える形で契約を
        # 一致させる。ネストした`parking`/`hours`等の内部dict・`payment_methods`/
        # `menu`等の内部listはFirestoreのmap/array型がそのまま表現できるため、
        # キーごとの型変換は不要である。
        self._doc_ref(store_id).set({"storeFaqInfo": dict(store_faq_info)}, merge=True)
```

- **フィールド名**は9・11・13・15・17・19・22節と同じcamelCase方針で
  `storeFaqInfo`とした。内部のキー(`parking`・`address`・`payment_methods`・
  `hours`・`menu`等)はアプリ側の命名のままFirestoreのmapキーとして格納し、
  変換は行わない(22節のメニュー名キーと同じ扱い)。
- **22節の「個別検討が必要」という見立ては不要だったと訂正する**: 23節(2)の
  時点では構造の不均一性からFirestoreアダプタ側にも個別のキー別分岐が必要と
  見込んでいたが、実際にはストア層が中身を解釈しない不透明な辞書である以上、
  Firestoreアダプタも中身を解釈する必要がなく、22節と全く同型の設計で足りる。
  同種の見立て違いが21節で指摘された「README記述が検証されないまま複製・
  継承され続ける」パターンの再発を防ぐため、本節で着手前の見立てが実装確認に
  よって訂正された経緯を明記した。

## 25. 次回候補(フェーズ続き313時点)

- (1)承認待ち事項(顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)がオーナーから
  承認された場合はその着手を最優先。
- (2)残りグループ`all_store_ids`(20節のとおりFirestoreの`stores`コレクション自体を
  クエリする設計になる見込み)の実Firestore接続アダプタ設計。これで本ventureの
  `StoreProfileStoreProtocol`の全グループ(Stripe顧客ID・9〜24節の各グループ)の
  設計が完了する見込み。
- (3)他venture・アイデア領域の前進。
- (4)他venture(course-set-pasha・aircon-pasha・kura-pasha・forklift-pasha)の「次回候補」
  記述にも21節で見つかった同種の陳腐化がないかの点検(21節・23節(4)から持ち越し)。

## 26. all_store_idsグループ(1メソッド)(フェーズ続き314、2026-10-11 17:00 UTC)

### 26.1. 背景・範囲

25節(2)を受け、`StoreProfileStoreProtocol`最後の残課題である`all_store_ids`
(`store_profile_store.py` 195行目・354-359行目)の実Firestore接続アダプタ設計に着手する。
`InMemoryStoreProfileStore.all_store_ids()`(354-359行目)は「いずれかのsetterが一度でも
呼ばれたstore_idの集合」を昇順ソートして返す実装だが、既存の唯一の呼び出し元
`blocked_but_billing_candidates.py`の`list_blocked_but_billing_candidates()`
(55-69行目)は`all_store_ids()`の戻り値を`sorted(...)`の内側でさらに絞り込みながら
自前でソートしているため、`all_store_ids()`自身が返す列挙順には依存していない
(InMemory実装のソートは単体テストでの決定性確保が目的と見られ、契約上の要求ではない)。
aircon-pashaの`UserProfileStoreProtocol.all_user_ids()`(firestore-provider-adapter-design.md
15節)と全く同じ論点であり、同節の結論をそのまま転用する。

### 26.2. 設計

```python
class FirestoreStoreProfileStore:
    # (2節・9・11・13・15・17・19・22・24節に以下を追加)

    def all_store_ids(self) -> Iterable[str]:
        for snapshot in self._stores.stream():
            yield snapshot.id
```

`self._stores`は2節で`__init__`時に`firestore_client.collection("stores")`として
既に組み立て済みのコレクション参照をそのまま再利用する(本グループのための新規フィールドは
不要)。

### 26.3. 検討事項

- **列挙順序への依存がないことの確認**: 26.1節のとおり、唯一の呼び出し元
  `list_blocked_but_billing_candidates()`は`all_store_ids()`の結果を絞り込んだ上で
  自前で`sorted()`しているため、`stream()`の返却順(ドキュメントID順やシャーディングに
  依存し保証されない)がInMemory実装の昇順ソートと異なっていても正当性に影響しない
  (aircon-pasha firestore-provider-adapter-design.md 15.3節と同じ結論)。
- **走査コストの判断**: `list_blocked_but_billing_candidates()`はoperator-facingの
  能動検知バッチ(日次〜手動実行想定、blocked-but-billing-detection-design.md 3節)からの
  呼び出しのみで、本venture想定の店舗数規模(unit-economics-estimate.md想定の個人経営
  店舗向けサービスという前提)ではコレクション全体の`stream()`がFirestore無料枠の範囲に
  収まる見込みのため、`where`条件による絞り込みや専用インデックスは過剰設計として見送る
  (aircon-pasha 15.3節・本ドキュメント3節と同じ結論)。
- **既存コレクション参照の再利用で足りる**: `all_store_ids()`はStripeグループ用の
  `_stripe_index`コレクションを参照する必要がなく、2節で既に組み立て済みの`_stores`への
  読み取り専用アクセスのみで実装できるため、`__init__`・`_doc_ref`への変更は不要である。

### 26.4. 本節で`StoreProfileStoreProtocol`の設計が完了したことの確認

本節により、1節で列挙した全グループ(Stripe顧客ID・owner_user_id・owner_is_following・
suspension_reason・owner_email・blocked_but_billing_owner_notified_at・plan・
checkout_session_completed_event_time・menu_durations・store_faq_info・
onboarding_completion_message・all_store_ids)の実Firestore接続アダプタ設計が揃った。
line-reservation-aiの`StoreProfileStoreProtocol`は、aircon-pasha・course-set-pasha・
kura-pashaが`UserProfileStoreProtocol`に対して行ってきた段階的設計と同じ粒度で全グループの
設計を完了したことになる(いずれも設計のみで、実Firestoreプロジェクト・GCP環境自体の
構築はオーナー承認待ちのまま、27節)。

## 27. 次回候補(フェーズ続き314時点)

- (1)承認待ち事項(顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)がオーナーから
  承認された場合はその着手を最優先。承認が得られれば、本ドキュメント2〜26節の設計一式
  (`FirestoreStoreProfileStore`)をまとめて実装し、`InMemoryStoreProfileStore`からの
  差し替え・結合テストに着手できる状態にある。
- (2)`_profile_to_dict`/`_profile_from_dict`相当のヘルパーが本venture(line-reservation-ai)
  では必要かどうかの確認(aircon-pasha 19節の`UserProfileStoreProtocol`は専用の
  dataclass/値オブジェクトを介するが、本venture `StoreProfileStoreProtocol`は各グループが
  個別フィールドの直接読み書きのみで値オブジェクトを介していないため、同種のヘルパーは
  不要と見込まれる。次回フェーズで軽く確認する)。
- (3)20節(4)で持ち越された、他venture(course-set-pasha・aircon-pasha・kura-pasha・
  forklift-pasha)の「次回候補」記述に21節と同種の陳腐化(既に対応済みの項目を未着手として
  繰り返し記載)がないかの点検。
- (4)他venture・アイデア領域の前進。

## 28. `_profile_to_dict`相当ヘルパーの要否確認(フェーズ続き315、2026-10-12 00:00 UTC)

フェーズ続き314の次回候補(2)を受け、`_profile_to_dict`/`_profile_from_dict`相当のヘルパーが
本venture(line-reservation-ai)で必要かを`prototype/store_profile_store.py`の
`StoreProfileStoreProtocol`定義(114〜187行目)で確認した。

- aircon-pashaの`UserProfileStoreProtocol`は、連携成立時に`save(user_id, profile:
  UserProfile)`で`UserProfile`値オブジェクト全体を1回のドキュメント書き込みにまとめ、
  `get(user_id) -> Optional[UserProfile]`で全フィールドを1回の読み取りから値オブジェクトへ
  復元する(firestore-provider-adapter-design.md 5節)。この「値オブジェクト全体⇄dict」の
  変換を担うのが`_profile_to_dict`/`_profile_from_dict`である。
- 本venture`StoreProfileStoreProtocol`には、これに相当する`save()`/`get()`(値オブジェクト
  全体を単位とする読み書き)が定義されていない。基盤の`get_stripe_customer_id`/
  `set_stripe_customer_id`から26節の`all_store_ids`まで、全メソッドがフィールド単位
  (またはmenu_durations・store_faq_infoのような1フィールド内の辞書単位)の個別読み書きのみで
  構成されており、値オブジェクト自体が定義されていない(`InMemoryStoreProfileStore`も
  `Dict[str, Dict[str, Any]]`のネストした素のdictで保持しており、専用dataclassを介さない)。
- したがって、本venture固有の値オブジェクト⇄dict変換ヘルパーを新設する必要はなく、
  27節(2)の「同種のヘルパーは不要と見込まれる」という見立ては正しいと確認できた。これにより
  `StoreProfileStoreProtocol`全グループ(2〜26節)の実Firestore接続アダプタ設計は、本節の
  確認をもって追加の未決事項なしで完了したとみなす。

コード変更なし、確認・結論の記録のみ。回帰確認として`python3 -m unittest discover -s
prototype -p "test_*.py"`(906件、変更なし)・`python3 schema/validate_test_cases.py`
(28件、変更なし)を再実行し、いずれもパスすることを確認した。承認が必要なアクション
(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。

次回候補: (1)承認待ち事項(顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)がオーナー
から承認された場合は本ドキュメント2〜26節の設計一式の実装着手を最優先、(2)他venture
(course-set-pasha・aircon-pasha・kura-pasha・forklift-pasha)の「次回候補」記述に21節と
同種の陳腐化がないかの点検(20節(4)・27節(3)から持ち越し)、(3)他venture・アイデア領域の
前進。

## 29. store_deletion_confirmation_sent_at/unreachable_at/unreachable_reasonグループ
(6メソッド)の実Firestore接続アダプタ設計(フェーズ続き329、2026-10-17 UTC)

### 29.1. 背景・26節時点の見落としの訂正

26.4節(フェーズ続き314、2026-10-11)は`StoreProfileStoreProtocol`の全グループの設計が
完了したと記録したが、これは当時のコードの状態に対して正しかっただけで、その後
フェーズ続き327(2026-10-17、aircon-pasha/course-set-pashaの「連絡不能クリア配線」横展開)
で`get/set_store_deletion_confirmation_unreachable_at`・
`get/set_store_deletion_confirmation_unreachable_reason`の4メソッドが`StoreProfileStoreProtocol`
に新規追加されたため、26.4節の「完了」は陳腐化していた(本ドキュメントに同4メソッドへの
言及が無いことで確認済み)。

さらに点検した結果、`firestore-data-model.md`(82-85行)が定義し、
`store_deletion_candidate.StoreDeletionCandidateState`・`cloud_function_send_store_
deletion_confirmations.StoreDeletionState`の両dataclassが「送信済みなら再送しない」
冪等性ガード(`is_store_deletion_candidate()`)に使っていた`storeDeletionConfirmationSentAt`
相当のフィールドには、そもそも`StoreProfileStoreProtocol`側に対応するget/setメソッドが
一度も存在しなかったことも判明した(`unreachable_at`/`unreachable_reason`と同時に追加
されるべきだったが、取り残されていたギャップ)。本フェーズでまず
`get_store_deletion_confirmation_sent_at`/`set_store_deletion_confirmation_sent_at`を
`StoreProfileStoreProtocol`/`InMemoryStoreProfileStore`に追加し(`unreachable_at`と同じ
単純なdict実装、空`store_id`は`ValueError`)、`StoreDeletionConfirmationSentAtTest`
(4件)を追加した上で、本節で3フィールド(計6メソッド)をまとめてFirestoreアダプタ設計する。

ドキュメント構造は本ドキュメント2節以来と同じ`stores/{storeId}`単一ドキュメント
(firestore-data-model.md)。対応フィールドは`storeDeletionConfirmationSentAt`
(Timestamp | null)・`storeDeletionConfirmationUnreachableAt`(Timestamp | null)・
`storeDeletionConfirmationUnreachableReason`(string | null)の3つ。forklift-pasha
フェーズ164(deletion-confirmation-sent-unreachable-firestore-adapter-design.md)の
`FleetOperatorStoreProtocol`向け設計と全く同じ論点構成のため、同ドキュメントの結論を
本venture固有の事情を踏まえて転用する。

### 29.2. 各メソッドの実装方針

**`store_deletion_confirmation_sent_at`(2メソッド)**: `storeDeletionConfirmationSentAt`
フィールドへの単純なget/update。唯一の書き込み元`send_store_deletion_confirmations()`
(cloud_function_send_store_deletion_confirmations.py:126)はLINE push送達成功時にのみ
呼ばれ、送信済みなら`is_store_deletion_candidate()`が候補から除外するため再送経路自体が
無く、上書き制約(「既に設定済みなら上書きしない」規約)は不要(forklift-pasha 2.1節と
同じ結論)。

```python
doc_ref = self._client.collection("stores").document(store_id)
doc_ref.update({"storeDeletionConfirmationSentAt": value})
```

**`store_deletion_confirmation_unreachable_at`(2メソッド)**: 同様に単純なget/update。
`sent_at`と`unreachable_at`はcloud_function_send_store_deletion_confirmations.py:105-126
の分岐内で排他的に一方だけが設定されるため、両フィールド間の整合性を保つ特別な制御
(トランザクション等)は不要(forklift-pasha 2.2節と同じ結論)。本venture固有の点として、
`clear_store_deletion_confirmation_unreachable_at()`(store_deletion_candidate.py:168)
による再フォロー時のクリア配線が既に`cloud_function_process_event.
process_follow_event()`に配線済み(フェーズ続き327)であり、forklift-pashaのような
「クリア経路自体が存在しないventure」とは異なる。

```python
doc_ref = self._client.collection("stores").document(store_id)
doc_ref.update({"storeDeletionConfirmationUnreachableAt": value})
```

**`store_deletion_confirmation_unreachable_reason`(2メソッド)**: `InMemoryStoreProfileStore`
実装はNone書き込みで単純にdict値を上書きするのみで、forklift-pasha 2.3節・kura-pasha/
aircon-pashaの先行結論と同じ理由から`DELETE_FIELD`センチネルではなく**`null`書き込み**を
採用する(本venture固有の相違点なし)。

```python
doc_ref = self._client.collection("stores").document(store_id)
doc_ref.update({"storeDeletionConfirmationUnreachableReason": value})
```

### 29.3. 複合インデックスの要否

フェーズ続き327で既に確認済みのとおり、`send_store_deletion_confirmations()`は呼び出し元が
読み取った店舗一覧全体を受け取りインメモリで絞り込む設計のため、kura-pasha・aircon-pasha・
course-set-pasha・forklift-pashaのような「2段階クエリ→1クエリ統合」の複合インデックスは
本グループには適用対象がない(本節で新たな複合インデックスは追加しない)。

### 29.4. まとめ: `StoreProfileStoreProtocol`全メソッドの設計完了(26.4節の訂正版)

本節により、26.4節が「完了」と誤って確定した後にコードへ追加された本グループ
(sent_at・unreachable_at・unreachable_reason)を含め、`StoreProfileStoreProtocol`が
現時点で持つ全メソッドの実Firestore接続アダプタ机上設計が揃った。

コード変更あり(`store_profile_store.py`: `get/set_store_deletion_confirmation_sent_at`
2メソッド追加、`test_store_profile_store.py`: `StoreDeletionConfirmationSentAtTest`
4件追加)。回帰確認として`python3 -m unittest discover -s prototype -p "test_*.py"`
(946件、新規4件含め全件パス)・`python3 schema/validate_test_cases.py`(28件、変更なし)
を実行し、いずれもパスすることを確認した。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。

次回候補: (1)承認待ち事項がオーナーから承認された場合は本ドキュメント一式の実装着手を
最優先、(2)20節(4)・27節(3)から持ち越しの、他venture(course-set-pasha・aircon-pasha・
kura-pasha・forklift-pasha)の「次回候補」記述の陳腐化点検(本節自身が26.4節の陳腐化を
発見した実例であり、他venture側にも同種の見落としが無いか改めて棚卸しする価値がある)、
(3)他venture・アイデア領域の
前進。

## 30. menu_durationsグループの実コード化(フェーズ続き353、2026-10-27 11:00 UTC)

22節で設計済みだった`get_menu_durations`/`set_menu_durations`(`menuDurations`フィールド、
空dict既定・丸ごと置き換え契約)を`firestore_store_profile_store.py`へそのまま実コード化
した。22節のコード例をそのまま採用し、設計との差異はない。`FirestoreStoreProfileStore`が
実装するグループはこれで9グループ(18メソッド)となった。

テストは`FirestoreStoreProfileStoreAllStoreIdsGroupTest`等の既存グループと同型の
`FirestoreStoreProfileStoreMenuDurationsGroupTest`を新規追加し、(1)ドキュメント未存在時は
空dict、(2)フィールド未設定時も空dict、(3)set→getの往復一致(日本語メニュー名「カット」
「カラー」をキーに含む)、(4)set呼び出しごとに辞書全体が置き換わる(個別キーの差分マージ
ではない)こと、(5)他フィールド(`stripeCustomerId`)を保持すること、(6)空store_idを
拒否すること、(7)クライアント例外時も空dictへ安全側フォールバックすること、の7件を
検証した。

コード変更あり(`firestore_store_profile_store.py`: `get_menu_durations`/
`set_menu_durations`2メソッド追加、`test_firestore_store_profile_store.py`:
`FirestoreStoreProfileStoreMenuDurationsGroupTest`7件追加)。回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(1015→1022件、新規7件含め
全件パス)・`python3 schema/validate_test_cases.py`(28件、変更なし)を実行し、いずれも
パスすることを確認した。実Firestoreクライアントへの接続やアカウント作成は行っていない。
承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ためpending-approval.mdへの追記なし。

次回候補: (1)残るFirestoreアダプタ実コード化グループ(checkout_session_completed_
event_time・store_faq_info・onboarding_completion_message、計3グループ)の実コード化
(いずれも実Firestore接続を待たずに着手可能)、(2)承認待ち事項がオーナーから承認された
場合はその着手を最優先、(3)他venture・アイデア領域の前進。

## 31. store_faq_infoグループの実コード化(フェーズ続き354、2026-10-27 15:00 UTC)

24節で設計済みの`get_store_faq_info`/`set_store_faq_info`をそのまま実コード化した
(`firestore_store_profile_store.py`)。24節のコード例と完全に一致させ、
`storeFaqInfo`フィールドへ空dict既定・丸ごと置き換え契約で読み書きする。これで
`FirestoreStoreProfileStore`が実装するグループは10グループ(20メソッド)になった。

テストは24節の想定どおり、`parking`(ネストdict)・`address`(文字列)・
`payment_methods`(リスト)・`hours`(ネストdict)・`menu`(リスト)という
キーごとに型が異なる不均一構造をまとめて1つのdictとして往復一致させるケースを含め
6件を新規追加した。コード変更あり(`firestore_store_profile_store.py`・
`test_firestore_store_profile_store.py`)。回帰確認として`python3 -m unittest
discover -s prototype -p "test_*.py"`(1022→1029件、新規6件含め全件パス)・
`python3 schema/validate_test_cases.py`(28件、変更なし)を実行しいずれもパス
することを確認した。実Firestoreクライアントへの接続やアカウント作成は行っていない。
承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ためpending-approval.mdへの追記なし。

次回候補: (1)残るFirestoreアダプタ実コード化グループ(checkout_session_completed_
event_time・onboarding_completion_message、計2グループ)の実コード化(いずれも実
Firestore接続を待たずに着手可能)、(2)承認待ち事項がオーナーから承認された場合は
その着手を最優先、(3)他venture・アイデア領域の前進。

## 32. checkout_session_completed_event_timeグループの実コード化(フェーズ続き355、2026-10-27 16:00 UTC)

17節で設計済みの`get_checkout_session_completed_event_time`/
`set_checkout_session_completed_event_time`をそのまま実コード化した
(`firestore_store_profile_store.py`)。17節のコード例と完全に一致させ、
`checkoutSessionCompletedEventTime`フィールドへ単純な読み書きを行う。接続エラー・
未設定時はいずれもNoneへ合流させる17節の安全側方針(配信順序ガードの後方互換パス
〈無条件適用〉に自然に合流させる)をそのまま踏襲した。これで
`FirestoreStoreProfileStore`が実装するグループは11グループ(22メソッド)になった。

テストは17節の想定どおり、未設定時None・set→get往復一致・上書き・他フィールド
(`stripeCustomerId`)非破壊・空`user_id`拒否・接続エラー時None合流の7件を新規追加
した。コード変更あり(`firestore_store_profile_store.py`・
`test_firestore_store_profile_store.py`)。回帰確認として`python3 -m unittest
discover -s prototype -p "test_*.py"`(1029→1036件、新規7件含め全件パス)・
`python3 schema/validate_test_cases.py`(28件、変更なし)を実行しいずれもパス
することを確認した。実Firestoreクライアントへの接続やアカウント作成は行っていない。
承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ためpending-approval.mdへの追記なし。

次回候補: (1)残るFirestoreアダプタ実コード化グループ(onboarding_completion_message、
5節で設計済み)の実コード化、(2)承認待ち事項(本venture全設計の結合実装)がオーナーから
承認された場合はその着手を最優先、(3)他venture・アイデア領域の前進。

## 33. onboarding_completion_messageグループの実コード化時に発見した`SERVER_TIMESTAMP`依存の矛盾と是正(フェーズ続き356、2026-10-27 17:00 UTC)

5節(訂正版は`store-profile-store-firestore-adapter-design-onboarding-flag.md`
2節)の設計コード例は`mark_onboarding_completion_message_sent`の書き込み値として
`firestore.SERVER_TIMESTAMP`(`google.cloud.firestore.SERVER_TIMESTAMP`)を直接
参照しているが、これは本ファイル(`firestore_store_profile_store.py`)の冒頭
docstringが一貫して掲げてきた方針「google-cloud-firestore SDKを直接importしない
(`firestore_client`が`collection`/`document`/`get`/`set`/`batch`を提供すれば、
実SDKでもテスト用フェイクでも差し替え可能)」と矛盾する。実際に本番環境でも
`google-cloud-firestore`パッケージは未インストールであることを確認した(実
Firestoreプロジェクト自体がpending-approval.md記載の承認待ちのため、SDKの導入自体
行っていない)。このまま`from google.cloud import firestore`を本ファイル先頭に
追加すると、承認前の現時点で`python3 -m unittest discover -s prototype`が
モジュールimport時点の`ModuleNotFoundError`で全件失敗する致命的な回帰を招く。

**是正**: `collection`/`document`/`get`/`set`/`batch`と同じ水準の規約として、
`firestore_client`に`SERVER_TIMESTAMP`属性を追加で要求する(ダックタイピング対象に
含める)。本ファイルは`self._client.SERVER_TIMESTAMP`をそのまま書き込み値として
使うのみで、サーバー側タイムスタンプの具体的な実体(実SDKの場合は
`google.cloud.firestore.SERVER_TIMESTAMP`センチネル、テスト用フェイクの場合は
任意の識別可能なセンチネルオブジェクト)には関与しない。承認後の結合実装フェーズで
実`google.cloud.firestore.Client`をラップする合成ルート側のアダプタ
(`firestore_store_document_provider.py`想定箇所)が、`collection`/`document`等の
委譲に加えて`SERVER_TIMESTAMP = google.cloud.firestore.SERVER_TIMESTAMP`を公開する
薄いラッパーとして実装される前提とする。この追加属性はネットワーク接続・認証情報を
一切要しない無害な定数の公開に過ぎないため、「実Firestoreプロジェクト・GCP
アカウントの開設(課金設定を伴う)自体はオーナー承認待ち」という既存の切り分け方針
(4節)に影響しない。

```python
    def is_onboarding_completion_message_sent(self, user_id: str) -> bool:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # design-onboarding-flag.md 2節: 接続エラーは「未送信」側に合流させる
            # (本フラグは送信するか否かの判定にのみ使われ、金銭処理の重複実行防止
            # ではないため、取りこぼしなく機会を確保する側を安全側とする)。
            return False
        if not snapshot.exists:
            return False
        return (
            (snapshot.to_dict() or {}).get("onboardingCompletionMessageSentAt")
            is not None
        )

    def mark_onboarding_completion_message_sent(self, user_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        self._doc_ref(user_id).set(
            {"onboardingCompletionMessageSentAt": self._client.SERVER_TIMESTAMP},
            merge=True,
        )
```

テストは7件追加: 未設定時False・フィールド未設定時False・mark→is往復(True)・
二重mark後もTrue(冪等性)・他フィールド非破壊・空`user_id`拒否・接続エラー時False
合流。フェイク側`_FakeFirestoreClient`に`SERVER_TIMESTAMP`属性(任意のセンチネル
オブジェクト)を追加し、フェイクの`set()`はこれを他の値と同じく素通りで保存する
(実SDKのサーバー側解決は結合実装フェーズの対象外)。

これで`StoreProfileStoreProtocol`の設計(29.4節で完了確認済みの全メソッド)の
うち、実コード化も完了したグループは12グループ(24メソッド)となり、設計済み
メソッド全てが実コード化済みの状態に達した。

次回候補: (1)承認待ち事項(実Firestoreプロジェクト・GCPアカウントの開設、および
合成ルート側で`SERVER_TIMESTAMP`属性を公開する実クライアントラッパーの実装を含む
結合実装)がオーナーから承認された場合はその着手を最優先、(2)他venture・アイデア
領域の前進。
