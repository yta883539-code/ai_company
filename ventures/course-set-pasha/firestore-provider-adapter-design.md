# LinkingCodeStoreProtocol の実Firestore接続アダプタ設計

## 1. 背景

`prototype/user_id_linking.py`には`LinkingCodeStoreProtocol`(`save`/`get`/`delete`/
`items`)と、検証用の`InMemoryLinkingCodeStore`スタブのみが存在し、実際の
`pending_links/{code}`ドキュメント(line-user-id-linking-design.md 2節)を読み書きする
具象実装はまだ存在しない。本venture自身には他に`UserProfileStoreProtocol`
(application_form_submission_flow.py・checkout_session.py・portal_session.py等、
複数モジュールにわたって個別定義された薄いProtocol群)もあるが、定義箇所が1モジュールに
閉じておらず一度に設計すると検討が発散するため、本フェーズは対象外とし次回候補として残す
(aircon-pashaフェーズ294が`LinkingCodeStoreProtocol`から着手した方針を本ventureにも
横展開する)。

aircon-pasha・kura-pasha・line-reservation-aiの3venture(いずれも本venture発のLINE友だち
追加連携コード方式〈line-user-id-linking-design.md〉を横展開済み)には既に同名の
`firestore-provider-adapter-design.md`が存在する一方、発案元である本venture自身には
まだ存在していなかった記載漏れを本フェーズで発見・是正する。本ドキュメントは、実Firestore
プロジェクトへの接続(GCPアカウント・課金設定を伴う、pending-approval.md記載のLINE公式
アカウント開設等と同種の承認待ち事項)が承認されるまでの間に、接続先が決まった際すぐ実装に
移れるよう、具象クラスの設計を先行して詰めておくもの。コード変更・外部アカウント作成の
いずれも行わない。

## 2. 設計方針

本venture自身の`LinkingCodeStoreProtocol`は、aircon-pashaの`PendingLink`データクラス方式
とは異なり、`save(code, user_id, issued_at)`で`user_id`を文字列のまま直接受け取るシンプルな
シグネチャ(`user_id_linking.py`41〜55行目)である。`pending_links/{code}`は`code`をドキュメント
IDとする単純な1ドキュメント1エントリの構造(line-user-id-linking-design.md 2節)のため、
`save`/`get`/`delete`はドキュメント単位の読み書きで素直に実装できる。`items()`のみ、
期限切れパージ(`purge_expired_links()`、`user_id_linking.py`224行目)のために全エントリを
列挙する必要があり、`pending_links`コレクション全体の`stream()`が必要になる。

```python
class FirestorePendingLinkStore:
    """LinkingCodeStoreProtocolの実Firestore接続実装。
    pending_links/{code}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("pending_links")

    def save(self, code: str, user_id: str, issued_at: datetime) -> None:
        self._collection.document(code).set(
            {"user_id": user_id, "issued_at": issued_at}
        )

    def get(self, code: str) -> Optional[Tuple[str, datetime]]:
        try:
            snapshot = self._collection.document(code).get()
        except Exception:
            # ネットワークエラー・権限エラー等はProtocol契約上の「未発見」側
            # (Noneを返す)に合流させる。resolve_linking_code()の「not found」分岐
            # (エラーメッセージを区別しない)と同じ粒度で、一時的なFirestore接続
            # エラーも「無効なコード」として扱い、ユーザーには単に再試行を促す。
            return None
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        if "user_id" not in data or "issued_at" not in data:
            return None
        return (data["user_id"], data["issued_at"])

    def delete(self, code: str) -> None:
        self._collection.document(code).delete()

    def items(self) -> Iterable[Tuple[str, str, datetime]]:
        for snapshot in self._collection.stream():
            data = snapshot.to_dict() or {}
            if "user_id" not in data or "issued_at" not in data:
                continue
            yield (snapshot.id, data["user_id"], data["issued_at"])
```

## 3. 検討事項

- **`get()`の例外方針**: 取得失敗時・フィールド欠損時のいずれも「未発見」(`None`)に倒す。
  `resolve_linking_code()`は無効/使用済み/期限切れでパージ済み/一度も発行されていない
  コードをいずれも同じ「not found」エラーメッセージで扱うため、一時的なFirestore接続
  エラーもこれに合流させて実害がないと判断した(aircon-pasha firestore-provider-
  adapter-design.md 3節と同じ方針)。
- **`items()`のコスト**: `purge_expired_links()`は`issue_linking_code_on_follow()`内の
  間引き呼び出し(`user_id_linking.py`181行目付近のコメント参照)のたびに`pending_links`
  コレクション全件を読み取る。`_LINK_TTL`が24時間であるため`issued_at`に対する複合
  インデックス+範囲クエリでの絞り込みも可能だが、本venture想定トラフィック(小規模
  パーソナルトレーニングジム向け、同時に未解決の連携コードは少数)では全件`stream()`でも
  無料枠に収まる前提のため、クエリ最適化は過剰設計として見送る(aircon-pasha・kura-pasha
  各firestore-provider-adapter-design.mdと同じ判断)。
- **書き込み方式**: `save()`は`set()`(フィールド全体の置き換え)を使う。`pending_links/
  {code}`は発行時に1回書き込まれた後は`delete()`されるだけの使い切りトークンであり、
  既存フィールドとの部分マージを考慮する必要がないため(`merge=True`は不要)。
- **依存ライブラリ**: `google-cloud-firestore`を想定(tech-stack.md想定と一致)。
  `firestore_client`をコンストラクタ注入する形とし、テスト時は`InMemoryLinkingCodeStore`を
  使い続ける(本クラスは実クライアント接続後の結合テストでのみ使用する)。

## 4. 残課題・次回候補(1〜3節分)

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちで
  あり、本設計のコードは承認後の結合実装フェーズまでコミットしない。
- 承認後は、`user_id_linking.py`・`cloud_function_webhook.py`呼び出し側の
  `LinkingCodeStoreProtocol`実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが
  完了する設計になっていることを、結合実装時に確認する。
- `UserProfileStoreProtocol`の実Firestore接続アダプタ設計は、まず基盤2フィールド
  (gym_area_pairs・email)グループから着手した(5節、aircon-pashaフェーズ294・
  kura-pashaフェーズ209と同じ「最小の関連グループから着手する」方針)。

## 5. UserProfileStoreProtocol(基盤2フィールド: gym_area_pairs・emailグループ)の実Firestore接続アダプタ設計

### 5.1. 背景・範囲

`application_form_submission_flow.py`の`UserProfileStoreProtocol`(14メソッド、同ファイル
27〜135行目)は、`checkout_session.py`・`portal_session.py`がそれぞれ別途定義する
`get_stripe_customer_id`のみの最小限Protocol(structural typing用の部分型)とは異なり、
本venture唯一の「本体」Protocolである。aircon-pasha・kura-pashaの`UserProfileStoreProtocol`
が`UserProfile`データクラス1個を丸ごと読み書きする`save`/`get`/`exists`の3メソッドを基盤に
持つのに対し、本venture自身の設計は`UserProfile`データクラスを持たず、フィールドごとに
個別の`set_*`/`get_*`メソッドが直接定義されている(`InMemoryUserProfileStore`も
フィールドごとに別々の`dict`を持つ、1行目のコメント参照)。このため本venture向けの
Firestoreアダプタ設計は、aircon-pashaのような「基盤3メソッド+個別フィールドグループ」
ではなく、関連の強いフィールドを束ねた「フィールドグループ」単位でそのまま`merge=True`の
部分更新メソッド群として設計する。

本フェーズは、申込フォーム提出フロー(application-form-submission-flow-design.md、
本モジュールの発案元)が直接書き込む最も基盤的な2フィールドに限定する。

1. **`gym_area_pairs`**: `set_gym_area_pairs`/`get_gym_area_pairs`。申込フォーム提出時に
   全体上書きされる(3節参照)、本Protocolの発案理由そのもののフィールド。
2. **`email`**: `set_email`/`get_email`。contact-email-field-design.md(フェーズ139)で
   申込フォームに追加された連絡先メールアドレス。`gym_area_pairs`と同じ申込フォーム
   提出イベントで一緒に書き込まれるため、同一グループとして扱う。

残りのグループ(Stripe顧客IDグループ: `set_stripe_customer_id`+順引き+逆引き、
`is_following`+`all_user_ids`、`blocked_but_billing_owner_notified_at`系3メソッド、`plan`、
`checkout_session_completed_event_time`)は本フェーズの対象外とし、次回候補として残す(6節)。

### 5.2. 設計

`user_profile/{user_id}`は`user_id`をドキュメントIDとする1ドキュメント1エントリの構造だが、
LinkingCodeStoreProtocol(使い切りトークンで`set()`による全体書き込みのみ)とは異なり、
本ドキュメントは`gym_area_pairs`・`email`・`stripe_customer_id`・`is_following`等、複数の
フィールドグループが同じドキュメントを共有して個別に読み書きする。このため、本グループの
`set_*`メソッドはいずれも他グループが書き込んだフィールドを消さないよう`merge=True`の
部分更新で実装する(aircon-pashaフェーズ294の5.3節で確立した方針と同じ)。

```python
class FirestoreUserProfileStore:
    """UserProfileStoreProtocolの実Firestore接続実装(基盤2フィールド:
    gym_area_pairs・emailグループのみ。他グループは次回候補、6節)。
    user_profile/{user_id}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._profiles = firestore_client.collection("user_profile")

    def _doc_ref(self, user_id: str):
        return self._profiles.document(user_id)

    def set_gym_area_pairs(self, user_id: str, raw_value: str) -> None:
        self._doc_ref(user_id).set({"gym_area_pairs": raw_value}, merge=True)

    def get_gym_area_pairs(self, user_id: str) -> str:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # LinkingCodeStoreProtocol.get()と同じ安全側方針を踏襲。ただし戻り値の
            # 型がstrのため、呼び出し元(normalize_gym_area_pairs_raw()等)が
            # 既に空文字列を安全に扱える契約に合わせて""を返す(Noneではない)。
            return ""
        if not snapshot.exists:
            return ""
        return (snapshot.to_dict() or {}).get("gym_area_pairs", "")

    def set_email(self, user_id: str, email: str) -> None:
        self._doc_ref(user_id).set({"email": email}, merge=True)

    def get_email(self, user_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("email")
```

### 5.3. 検討事項

- **`merge=True`固定の理由**: `user_profile/{user_id}`は本グループ以外にも
  `stripe_customer_id`・`is_following`等、複数のフィールドグループが同じドキュメントを
  共有するため、`set()`を`merge`無しで呼ぶと他グループが既に書き込んだフィールドを
  消してしまう。本venture自身には(aircon-pashaのような)`UserProfile`データクラス丸ごとの
  `save()`メソッドが存在しないため、全`set_*`メソッドが`merge=True`の部分更新になる。
- **`get_gym_area_pairs`のデフォルト値は`""`固定**: `InMemoryUserProfileStore.
  get_gym_area_pairs()`(`application_form_submission_flow.py`167行目)の
  `self._profiles.get(user_id, "")`と型・デフォルト値を揃えた。`get_email`は
  `Optional[str]`のため`None`のままで揃える(型が異なる2メソッドを同じグループで
  設計する際の非対称性であり、InMemory実装の非対称性をそのまま引き継ぐ)。
- **例外方針**: 4節で設計した`LinkingCodeStoreProtocol.get()`・aircon-pashaフェーズ294の
  `FirestoreUserProfileStore.get()`と同じ、一時的な接続エラーも「未発見」側のデフォルト値に
  倒す安全側方針を踏襲。

## 6. UserProfileStoreProtocol(Stripe顧客IDグループ)の実Firestore接続アダプタ設計

### 6.1. 背景・範囲

5節の次回候補を受け、`set_stripe_customer_id`/`get_stripe_customer_id`/
`get_user_id_by_stripe_customer_id`の3メソッド(Stripe顧客IDグループ)の実Firestore接続
アダプタ設計に着手する。aircon-pashaフェーズ294の5節が確立した、`stripe_customer_id`の
逆引きを専用コレクション`stripe_customer_index/{stripe_customer_id}`への同時書き込みで
実現する方式を横展開する。

### 6.2. 設計

`InMemoryUserProfileStore`(`application_form_submission_flow.py`178〜188行目)は
`_stripe_customer_ids`(user_id→stripe_customer_id)と`_user_ids_by_stripe_customer_id`
(逆引き)の2つの辞書を別持ちしている。本venture自身には(aircon-pashaのような)
`UserProfile`データクラス丸ごとの`save()`が存在しないため、`get_stripe_customer_id`は
5節の`get_email`と同様に`user_profile/{user_id}`ドキュメントの単一フィールドを直接
読み出す形で実装する(aircon-pashaの`get_stripe_customer_id`が`self.get(user_id)`経由で
`UserProfile`全体を取得してから`.stripe_customer_id`を参照するのとは異なる)。

```python
class FirestoreUserProfileStore:
    """UserProfileStoreProtocolの実Firestore接続実装(基盤2フィールド+Stripe顧客ID
    グループのみ。他グループは次回候補、7節)。
    user_profile/{user_id}ドキュメントおよびstripe_customer_index/{stripe_customer_id}
    逆引きドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._profiles = firestore_client.collection("user_profile")
        self._stripe_index = firestore_client.collection("stripe_customer_index")

    def _doc_ref(self, user_id: str):
        return self._profiles.document(user_id)

    # ...set_gym_area_pairs/get_gym_area_pairs/set_email/get_emailは5節のまま...

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        # フェーズ286: 再紐付け検出のため、書き込み前に旧customer_idを読み出す
        # (InMemoryUserProfileStore.set_stripe_customer_idの`previous_stripe_customer_id`
        # 分岐と対称。実装自体は実Firestore接続がオーナー承認待ちのため次回以降)。
        previous_stripe_customer_id = self.get_stripe_customer_id(user_id)
        batch = self._client.batch()
        batch.set(
            self._doc_ref(user_id),
            {"stripe_customer_id": stripe_customer_id},
            merge=True,
        )
        if (
            previous_stripe_customer_id is not None
            and previous_stripe_customer_id != stripe_customer_id
        ):
            batch.delete(self._stripe_index.document(previous_stripe_customer_id))
        batch.set(
            self._stripe_index.document(stripe_customer_id),
            {"user_id": user_id},
        )
        batch.commit()

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("stripe_customer_id")

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
```

### 6.3. 検討事項

- **契約整合性チェック(line-reservation-aiフェーズ続き301と同種)**: `set_stripe_customer_id`
  実行時に旧`stripe_customer_id`からの付け替え(同一user_idが2回目の呼び出しを行うケース)が
  起きた場合、`stripe_customer_index`側の旧エントリが削除されず残る点を確認した。
  **(フェーズ286追記)**: `InMemoryUserProfileStore.set_stripe_customer_id`
  (`application_form_submission_flow.py`)側はkura-pashaフェーズ224・line-reservation-aiの
  `stripe-customer-id-reverse-lookup-design.md` 2節と同じ方針で、再紐付け検出時に旧
  `_user_ids_by_stripe_customer_id`エントリを`pop`してから新エントリを書き込む処理を実装済み
  (詳細はフェーズ286追記の新設21節を参照)。実Firestore接続アダプタ側も対称に、
  `set_stripe_customer_id`実行時の`WriteBatch`に旧`stripe_customer_id`が存在する場合の
  `self._stripe_index.document(previous_stripe_customer_id).delete()`を追加する必要がある
  (以下のコード例に反映。実装自体は実Firestore接続がオーナー承認待ちのため次回以降)。
- **`get_stripe_customer_id`の実装方針**: 5節の検討事項で確立した「本venture自身は
  `UserProfile`データクラスを持たないため、各`get_*`は`user_profile/{user_id}`の個別
  フィールドを直接読む」方針をそのまま踏襲した。
- **例外方針**: 5節・4節と同じ、一時的な接続エラーも「未発見」(`None`)に倒す安全側方針を
  踏襲。

## 7. UserProfileStoreProtocol(is_following + all_user_idsグループ)の実Firestore接続アダプタ設計

### 7.1. 背景・範囲

6節の次回候補を受け、`set_is_following`/`get_is_following`/`all_user_ids`の3メソッド
(is_following + all_user_idsグループ)の実Firestore接続アダプタ設計に着手する。
`set_is_following`/`get_is_following`は5節・6節と同じ`merge=True`の単一フィールド部分更新で
素直に実装できるが、`all_user_ids()`は他の2メソッドと異なり特定の`user_id`を受け取らず、
`InMemoryUserProfileStore.all_user_ids()`(application_form_submission_flow.py 196〜205行目)が
`_profiles`・`_emails`・`_stripe_customer_ids`・`_is_following`・`_plans`の5つの辞書のキー集合を
和集合として返す設計になっている点を、単一ドキュメント構造のFirestoreでどう実現するかが本節の
主眼になる。

### 7.2. 設計

`user_profile/{user_id}`は5節で確立した通り、`gym_area_pairs`・`email`・`stripe_customer_id`・
`is_following`等のフィールドグループが同一ドキュメントを共有する構造である。InMemory実装が
5つの辞書を別持ちして和集合を取っているのは、Pythonの素朴なデータ構造上の都合にすぎず、
Firestoreでは該当フィールドのいずれかが一度でも書き込まれた`user_id`は同一の
`user_profile/{user_id}`ドキュメントとして存在することになる。したがって`all_user_ids()`は、
複数コレクション・複数フィールドを個別に集計し直す必要はなく、`user_profile`コレクション全体を
`stream()`してドキュメントIDを列挙するだけで、InMemory版の和集合と同じ集合が得られる
(7.3節で範囲の一致を確認する)。

```python
class FirestoreUserProfileStore:
    """UserProfileStoreProtocolの実Firestore接続実装(基盤2フィールド+Stripe顧客ID
    グループ+is_following/all_user_idsグループのみ。他グループは次回候補、8節)。
    """

    # ...set_gym_area_pairs/get_gym_area_pairs/set_email/get_email/
    #    set_stripe_customer_id/get_stripe_customer_id/get_user_id_by_stripe_customer_idは
    #    5節・6節のまま...

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        self._doc_ref(user_id).set({"is_following": is_following}, merge=True)

    def get_is_following(self, user_id: str) -> bool:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # InMemoryUserProfileStore.get_is_following()のデフォルト(True、
            # 「未記録のuser_idはフォロー中として扱う」安全側の初期値、
            # UserProfileStoreProtocolのdocstring参照)と揃える。
            return True
        if not snapshot.exists:
            return True
        return (snapshot.to_dict() or {}).get("is_following", True)

    def all_user_ids(self) -> Iterable[str]:
        try:
            for snapshot in self._profiles.stream():
                yield snapshot.id
        except Exception:
            # 一時的な接続エラー時は空集合を返す安全側方針(5節・6節と同じ)。
            # all_user_ids()はblocked_but_billing_candidates.list_...()の走査対象
            # であり、空集合を返しても「今回は対象候補なし」として扱われるだけで、
            # 誤って既存ユーザーを巻き込む・誤通知するリスクはない。
            return
```

### 7.3. 検討事項

- **`all_user_ids()`をコレクション全件`stream()`に単純化できる根拠**: `InMemoryUserProfileStore.
  all_user_ids()`の和集合コメント(application_form_submission_flow.py 197〜199行目)は、
  `_blocked_but_billing_owner_notified_at`・`_checkout_session_completed_event_time`の2辞書を
  意図的に和集合から除外している。この2フィールドが「和集合に含まれなくても欠落が起きない」
  ことを呼び出し側のコードで確認した。
  - `set_checkout_session_completed_event_time`は`stripe_webhook.py`
    `link_checkout_session_to_user_id()`(902〜914行目)内で、必ず同一呼び出し内で
    `store.set_stripe_customer_id(user_id, ...)`が先に実行された後にのみ呼ばれる
    (staleイベント判定でreturnする分岐は`set_checkout_session_completed_event_time`の手前)。
    このためこのフィールドが書き込まれる時点で`stripe_customer_id`も同一ドキュメントに
    既に書き込まれており、Firestoreでは最初からdocが存在する。
  - `set_blocked_but_billing_owner_notified_at`は`blocked_but_billing_owner_notification.py`
    `send_blocked_but_billing_owner_notifications()`(139行目)内で、引数`candidate_user_ids`
    (`list_blocked_but_billing_candidates()`の呼び出し結果)に含まれる`user_id`に対してのみ
    呼ばれる。この候補者リスト自体が`all_user_ids()`の走査結果を起点に絞り込まれるため
    (application_form_submission_flow.py 198行目のコメント)、このフィールドが書き込まれる
    `user_id`は常に`all_user_ids()`に既出である。
  - 結論として、Firestoreでは`user_profile`コレクションの`stream()`で得られるドキュメントID
    集合は、InMemory版の5辞書和集合と常に一致する(前者が後者を超える`user_id`を含むケースは
    現状のコードパス上発生しない)。`merge=True`の`set()`はドキュメントが存在しなければ新規
    作成するため、この一致を崩さない限り今後も安全(新しいフィールドグループを追加する際は、
    「必ず基盤フィールドのいずれかより後に書き込まれるか」をこの節と同じ方法で確認する必要が
    ある、8節に申し送る)。
- **`get_is_following`のデフォルト値`True`**: 5節で確立した「`get_gym_area_pairs`は`""`、
  `get_email`は`None`」という型ごとのデフォルト値の使い分けと同様、`bool`型の本フィールドは
  `InMemoryUserProfileStore`の`self._is_following.get(user_id, True)`と揃えて`True`固定とした
  (UserProfileStoreProtocolのdocstring: 未記録のuser_idは「安全側」にフォロー中として扱う)。
- **`all_user_ids()`の例外方針**: 5節・6節の個別フィールド取得メソッドは例外時にそのフィールドの
  デフォルト値を返す方針だったが、`all_user_ids()`はイテラブルを返す集合操作のため、例外時は
  空のイテラブルとした。呼び出し元の`list_blocked_but_billing_candidates()`は走査対象が0件でも
  単に「今回は通知対象なし」として扱うだけで誤動作しないため、一時的なFirestore接続エラー時に
  安全側(何もしない)に倒れる。
- **コスト**: `user_profile`コレクション全件`stream()`は本venture想定規模(個人経営ボルダリング
  ジム向け、顧客数は店舗ごとに限定的)では無料枠に収まる前提(4節のpending_links全件走査と
  同じ判断)。将来的に顧客数が大きく増えた場合は、`is_following == false`のユーザーのみを
  絞り込む複合クエリへの最適化が考えられるが、現時点では過剰設計として見送る。

## 8. 残課題・次回候補(7節分)

- 残りのグループ(`blocked_but_billing_owner_notified_at`系3メソッド・`plan`・
  `checkout_session_completed_event_time`)の実Firestore接続アダプタ設計。いずれも
  5節・6節・7節と同じ`_doc_ref(user_id)`ヘルパーの上に`merge=True`の部分更新として
  素直に実装できる見込みだが、本フェーズでは対象外。新しいフィールドグループを追加する際は、
  7.3節で行った「`all_user_ids()`の和集合除外フィールドとの整合確認」と同じ方法で、
  書き込み順序の契約を確認すること。
- 承認後は、`application_form_submission_flow.py`呼び出し側の`UserProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。

## 9. UserProfileStoreProtocol(blocked_but_billing_owner_notified_atグループ)の実Firestore接続アダプタ設計

### 9.1. 背景・範囲

8節の次回候補を受け、`set_blocked_but_billing_owner_notified_at`/
`get_blocked_but_billing_owner_notified_at`/`clear_blocked_but_billing_owner_notified_at`の
3メソッド(blocked_but_billing_owner_notified_atグループ)の実Firestore接続アダプタ設計に
着手する。本フィールドは「ブロック中かつ契約継続中」候補としてオーナーへ通知済みかどうかの
冪等性フラグ(blocked-but-billing-owner-notification-design.md 3節)であり、7.3節で確認した
通り`all_user_ids()`の和集合からは意図的に除外されている。sister venture aircon-pashaは
11節で同種のowner_notified_at系フィールドを設計済みだが、そちらは専用の`clear_*`メソッドを
持たず`set_*(None)`でクリアを表現する設計である点が、本venture(`clear_*`という専用メソッドを
持つ)との差分になる。

### 9.2. 設計

本フィールドも5節で確立した`_doc_ref(user_id)`ヘルパー上の単純な`merge=True`部分更新・
単純読み取りで実装でき、`clear_*`は値を`None`で書き込むことで表現する
(aircon-pasha 11節と同じ結論、9.3節で理由を確認する)。

```python
class FirestoreUserProfileStore:
    # (5節・6節・7節に以下を追加)

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: datetime
    ) -> None:
        self._doc_ref(user_id).set(
            {"blocked_but_billing_owner_notified_at": notified_at}, merge=True
        )

    def get_blocked_but_billing_owner_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # 一時的な接続エラー時は「未通知」として扱う安全側方針(9.3節)。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(
            "blocked_but_billing_owner_notified_at"
        )

    def clear_blocked_but_billing_owner_notified_at(self, user_id: str) -> None:
        self._doc_ref(user_id).set(
            {"blocked_but_billing_owner_notified_at": None}, merge=True
        )
```

`InMemoryUserProfileStore`の同名3メソッド(application_form_submission_flow.py
207〜218行目)は、`set_*`が辞書への代入、`get_*`が`dict.get(user_id)`(デフォルト`None`)、
`clear_*`が`dict.pop(user_id, None)`(キー自体を削除)という構成である。

### 9.3. 検討事項

- **`clear_*`を`None`書き込みで表現できる根拠**: InMemory版の`clear_*`はキー自体を
  辞書から削除するが、`get_*`は`dict.get(user_id, None)`でキー不在時も`None`を返すため、
  「キーが存在しない」状態と「値が`None`として記録されている」状態はget側の観測結果が
  一致する。Firestore側で`merge=True`の`set({"blocked_but_billing_owner_notified_at": None})`を
  行うとフィールドはドキュメントに`null`として残り削除はされないが、本設計の`get_*`は
  `null`も未設定もいずれも`None`として返すため、InMemory版の`clear_*`(pop)と観測可能な
  挙動は一致する(aircon-pasha 11.3節と同じ結論)。
- **例外時に`None`を返す安全性**: `get_blocked_but_billing_owner_notified_at`が一時的な
  接続エラーで`None`を返すと、呼び出し元
  (`blocked_but_billing_owner_notification.py` 67行目、`notified_at_reader.
  get_blocked_but_billing_owner_notified_at(user_id) is None`を抽出条件とする)は
  「未通知」と判定し、既に通知済みのユーザーに対して通知が再送される可能性がある。これは
  5節で確立した「安全側に倒す」方針(通知を誤って止めるより、まれに再送される方が実害が
  小さい)と整合するため許容する。
- **`merge=True`の一貫性**: 5節・6節・7節と同じ方針を踏襲。

## 10. 残課題・次回候補(9節分)

- 残りのグループ(`plan`・`checkout_session_completed_event_time`)の実Firestore接続
  アダプタ設計。いずれも5節・6節・7節・9節と同じ`_doc_ref(user_id)`ヘルパーの上に
  `merge=True`の部分更新として素直に実装できる見込みだが、本フェーズでは対象外。
  `checkout_session_completed_event_time`は7.3節で確認した通り`stripe_customer_id`より
  必ず後に書き込まれる契約があるため、設計時はそれを前提にできる。
- 承認後は、`application_form_submission_flow.py`呼び出し側の`UserProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。

## 11. UserProfileStoreProtocol(planグループ)の実Firestore接続アダプタ設計

### 11.1. 背景・範囲

10節の次回候補を受け、`set_plan`/`get_plan`の2メソッド(planグループ)の実Firestore接続
アダプタ設計に着手する。`application_form_submission_flow.py`121〜125行目
(Protocol定義)・220〜224行目(InMemory実装)が対象。

### 11.2. 設計

`InMemoryUserProfileStore.set_plan`/`get_plan`(220〜224行目)は`_plans`辞書への
単純な代入・`dict.get(user_id)`(デフォルト`None`)のみで、5節・6節で確立した
`_doc_ref(user_id)`ヘルパー上の`merge=True`部分更新・単純読み取りでそのまま実装できる。

```python
class FirestoreUserProfileStore:
    # (5節・6節・7節・9節に以下を追加)

    def set_plan(self, user_id: str, plan: str) -> None:
        self._doc_ref(user_id).set({"plan": plan}, merge=True)

    def get_plan(self, user_id: str) -> Optional[str]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("plan")
```

### 11.3. 検討事項

- **例外時に`None`を返す安全性(他グループとは異なる理由で安全)**: `get_plan`の呼び出し元
  `cloud_function_webhook.py`1478〜1489行目は、`get_plan`が`None`を返した場合
  (未記録、またはFirestore接続エラー)、バッチ呼び出し元が渡す従来の一律`plan`引数に
  フォールバックする設計になっている(1480〜1481行目のコメント: 「未記録(トライアル中等)
  またはprofile_store未指定の場合は、従来通り引数`plan`にフォールバックする」)。つまり
  一時的な接続エラーで`None`を返しても、処理が完全に止まったりブロック判定に誤って
  倒れたりすることはなく、単に「ユーザーごとの実プラン優先」が一時的に効かず従来のバッチ
  一律プランで処理されるだけである。これは6節(Stripe顧客IDグループ、`None`は「未発見」
  として新規扱いになる)や9節(`None`は「未通知」として再通知される可能性がある)とは
  異なる安全性の根拠だが、いずれも「例外時は`None`を返す」という同じ実装方針が許容できる
  ことを個別に確認できた。
- **`merge=True`の一貫性**: 5節・6節・7節・9節と同じ方針を踏襲。

## 12. 残課題・次回候補(11節分)

- 残り1グループ(`checkout_session_completed_event_time`)の実Firestore接続アダプタ設計。
  5節・6節・7節・9節・11節と同じ`_doc_ref(user_id)`ヘルパー上の`merge=True`部分更新として
  実装できる見込みで、全グループ完了まであとこの1つのみ。
- 承認後は、`application_form_submission_flow.py`呼び出し側の`UserProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。

## 13. UserProfileStoreProtocol(checkout_session_completed_event_timeグループ)の実Firestore接続アダプタ設計

### 13.1. 背景・範囲

12節の次回候補を受け、`set_checkout_session_completed_event_time`/
`get_checkout_session_completed_event_time`の2メソッド(checkout_session_completed_event_
timeグループ)の実Firestore接続アダプタ設計に着手する。
`application_form_submission_flow.py`127〜135行目(Protocol定義)・161行目・226〜234行目
(InMemory実装)が対象。これで`UserProfileStoreProtocol`の全グループの実Firestore接続
アダプタ設計が完了する(2節の基盤グループ以降、5・6・7・9・11・本節で計7グループ)。

### 13.2. 設計

本フィールドも5節で確立した`_doc_ref(user_id)`ヘルパー上の単純な`merge=True`部分更新・
単純読み取りで実装できる。値は`datetime`型のまま`set()`に渡すだけでよく、Firestoreの
Pythonクライアントが`google.cloud.firestore_v1._helpers.DatetimeWithNanoseconds`
(`datetime`のサブクラス)への変換を内部で行うため、本アダプタ側で明示的な型変換は不要
(9節・11節の`notified_at`/`plan`と同じく、Firestoreネイティブ型にそのまま委ねる設計を踏襲)。

```python
class FirestoreUserProfileStore:
    # (5節・6節・7節・9節・11節に以下を追加)

    def set_checkout_session_completed_event_time(
        self, user_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(user_id).set(
            {"checkout_session_completed_event_time": event_time}, merge=True
        )

    def get_checkout_session_completed_event_time(
        self, user_id: str
    ) -> Optional[datetime]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # 一時的な接続エラー時は「基準時刻未記録」として扱う安全側方針(13.3節)。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(
            "checkout_session_completed_event_time"
        )
```

`InMemoryUserProfileStore`の同名2メソッド(application_form_submission_flow.py
226〜234行目)は、`set_*`が辞書への代入、`get_*`が`dict.get(user_id)`(デフォルト`None`)の
みという最も単純な構成(`clear_*`は存在しない)。

### 13.3. 検討事項

- **例外時に`None`を返す安全性(他グループと異なる方向の安全性)**: 本フィールドは
  `stripe_webhook.handle_checkout_session_completed()`(823〜917行目)の配信順序ガードの
  基準線としてのみ使われる。`get_checkout_session_completed_event_time`が一時的な接続
  エラーで`None`を返すと、880〜886行目の判定で`recorded_event_time is None`となり
  ガード自体が「本ガード導入前からの既存ユーザー等、記録済みの時刻が未設定」の場合と同じ
  `is_stale = False`(常に無条件適用)に倒れる。これは9節・11節(「安全側」が通知再送や
  バッチプランへのフォールバックという“処理を止めない”方向の安全性)とは逆に、“ガードを
  素通りさせる”方向の安全性である。しかし864〜866行目のdocstringで元々「記録済みの時刻が
  未設定の場合はチェックを行わず従来通り無条件適用する(後方互換)」という挙動が明示的に
  許容されており、一時的な接続エラーもこの既存の許容範囲に収まる(配信順序が入れ替わる
  事象自体が稀であるため、接続エラーとの重複はさらに稀であり、仮に重複しても誤って
  古いデータで上書きする実害は、処理が完全に止まることに比べ小さいと判断する)。
- **`DatetimeWithNanoseconds`とtz-aware `datetime`の比較**: `get_*`がFirestoreから
  読み出す値は`DatetimeWithNanoseconds`(`datetime`のサブクラス)、885行目の比較対象
  `event_time`は`datetime.fromtimestamp(created, tz=timezone.utc)`(stripe_webhook.py
  524行目等)で生成されるtz-aware UTC `datetime`であり、いずれもtz-aware同士の比較
  (`<=`)として問題なく成立する(tz-naiveとtz-awareの混在による`TypeError`は発生しない)。
- **`merge=True`の一貫性**: 5節・6節・7節・9節・11節と同じ方針を踏襲。

## 14. 残課題・次回候補(13節分)

- `UserProfileStoreProtocol`の全7グループの実Firestore接続アダプタ設計が本節で完了した。
  残るのは、承認待ち事項(2026-09-27 03:00 UTC記載の実Stripeアカウント開設等)がオーナーから
  承認された後の、実際のFirestoreプロジェクト接続・`application_form_submission_flow.py`
  呼び出し側への本クラスのインスタンス注入・結合テストのみ(いずれも未承認のため着手不可)。
- 他venture・アイデア領域の前進、またはcourse-set-pasha内の別論点
  (例: `GymAreaConfigStoreProtocol`等、本designでは未対象の他Protocolの実Firestore接続
  アダプタ設計)への着手を次回候補とする。

## 15. GymAreaConfigStoreProtocol(is_configured)の実Firestore接続アダプタ設計

### 15.1. 背景・範囲

14節の次回候補を受け、`cloud_function_webhook.py`687〜696行目で定義される
`GymAreaConfigStoreProtocol`(読み取り専用、`is_configured(user_id) -> bool`の1メソッドのみ)
の実Firestore接続アダプタ設計に着手する。本Protocolは`UserProfileStoreProtocol`とは別の
クラスとして定義されているが、application-form-submission-flow-design.md 4節・残課題が
既に「実Firestore接続後、`FirestoreUserProfileStore`が`GymAreaConfigStoreProtocol`と
`UserProfileStoreProtocol`の両方を満たす実装になることの最終確認」を残課題として明記して
おり、`InMemoryUserProfileStore.is_configured()`(application_form_submission_flow.py
175〜176行目)も`GymAreaConfigStoreProtocol`互換のメソッドとして既に実装済みである
(5節冒頭のコメント参照)。本節はその「最終確認」を実クラスの設計として行う。

### 15.2. 設計

`is_configured()`は5節で設計済みの`get_gym_area_pairs()`を素直に再利用するだけで実装できる。
`GymAreaConfigStoreProtocol`は読み取り専用のためProtocol側に`set_*`は存在せず、書き込みは
`UserProfileStoreProtocol.set_gym_area_pairs()`(申込フォーム提出フロー)の責務のままである。

```python
class FirestoreUserProfileStore:
    # (5節・6節・7節・9節・11節・13節に以下を追加)

    def is_configured(self, user_id: str) -> bool:
        # InMemoryUserProfileStore.is_configured()(application_form_submission_flow.py
        # 175〜176行目)と同じく、get_gym_area_pairs()の非空判定に委譲する。
        # 専用のドキュメント読み取りを別途行わない(同一ドキュメントへの二重アクセスを避ける)。
        return bool(self.get_gym_area_pairs(user_id))
```

これにより、`FirestoreUserProfileStore`は`UserProfileStoreProtocol`
(`application_form_submission_flow.py`)と`GymAreaConfigStoreProtocol`
(`cloud_function_webhook.py`)の両方を1つのクラス・1つの`user_profile/{user_id}`ドキュメント
アクセスで満たす設計となり、application-form-submission-flow-design.md 4節が見越していた
構成がそのまま成立することを確認した。

### 15.3. 検討事項

- **例外方針の継承**: `get_gym_area_pairs()`は5.3節の方針により、一時的な接続エラー時に
  `""`(空文字列)を返す。`is_configured()`はその結果を`bool()`に通すだけなので、接続エラー時は
  自動的に`False`(未設定)を返す。これは2節(application-form-submission-flow-design.md)の
  「誤ったタグ付けより“タグ無し”の安全側を優先する」既存方針とも一致する方向の安全性であり、
  13.3節で見たような方向の食い違いは発生しない。
- **二重ドキュメント読み取りの回避**: `is_configured()`と`get_gym_area_pairs()`を呼び出し側が
  両方呼ぶケース(例: `first_generation_notice`の確認案内文言組み立てとusage判定を同一リクエスト
  内で両方行う場合)は、本設計のままでは`_doc_ref(user_id).get()`が2回発生しうる。現状の
  呼び出しパターン(cloud_function_webhook.pyの各呼び出し箇所)を確認した限り同一リクエスト内で
  両方を呼ぶ箇所は無く、現時点では個別最適化(読み取り結果のキャッシュ等)を導入する必要性は
  無いと判断した。将来両方を同時に呼ぶ呼び出し箇所が増えた場合の最適化は次回候補として残す。
- **`merge=True`との関係**: `is_configured()`自体は読み取り専用のため`merge=True`は関係しない
  (5節・6節・7節・9節・11節・13節の`set_*`系との非対称性はProtocol自体の非対称性に由来する)。

## 16. 残課題・次回候補(15節分)

- `GymAreaConfigStoreProtocol`の実Firestore接続アダプタ設計が本節で完了し、
  application-form-submission-flow-design.md 4節・残課題が残していた「最終確認」も解消した。
  これにより、本venture(course-set-pasha)で把握している全Protocol
  (`UserProfileStoreProtocol`・`GymAreaConfigStoreProtocol`)の実Firestore接続アダプタ設計が
  完了した。
- 残るのは、承認待ち事項(実Stripeアカウント開設・LINE公式アカウント開設・LIFFアプリ登録・
  Googleフォーム作成等)がオーナーから承認された後の、実際のFirestore/Stripe/LINEプロジェクト
  接続・各呼び出し側への本クラスのインスタンス注入・結合テストのみ(いずれも未承認のため
  着手不可)。
- 他venture・アイデア領域の前進を次回候補とする。

## 17. 付け替え時の旧`stripe_customer_id`逆引きエントリ削除(フェーズ286)

6.3節「検討事項」で次回候補として残していた、同一`user_id`に別の`stripe_customer_id`が
再紐付けされた場合の旧逆引きエントリ削除を実装した。kura-pashaフェーズ224・
line-reservation-aiの`stripe-customer-id-reverse-lookup-design.md` 2節・
`store_profile_store.py`の`InMemoryStoreProfileStore.set_stripe_customer_id`と同じ方針を
踏襲し、`InMemoryUserProfileStore.set_stripe_customer_id`
(`application_form_submission_flow.py`)に、再紐付け検出時に古い`stripe_customer_id`の
逆引きエントリ(`_user_ids_by_stripe_customer_id`)を`pop`してから新しいエントリを書き込む
処理を追加した。これにより、通常は同一user_idが決済をやり直す際も同一Stripe顧客を再利用する
想定だが、何らかの理由で同一user_idに別のStripe顧客IDが再設定された場合でも、古い
`stripe_customer_id`宛のWebhookイベント(Stripe側の遅延配送・リトライ等)が
(たまたま他venture・他システムで再利用された場合に)別のuser_idに誤って解決されるリスクを
防ぐ。

- 実Firestore接続アダプタ側(6.2節`FirestoreUserProfileStore.set_stripe_customer_id`)の
  コード例にも、`WriteBatch`実行時に旧エントリの削除
  (`self._stripe_index.document(previous_stripe_customer_id).delete()`)を反映した
  (実装自体は実Firestore接続がオーナー承認待ちのため次回以降)。
- `InMemoryUserProfileStore`側の実装・テストは本フェーズで完結している。

### 17.1. 動作確認

`test_application_form_submission_flow.py`に
`test_relinking_same_user_to_new_customer_id_removes_stale_reverse_lookup`(旧customer_idの
逆引きがNoneに戻ることを確認)・
`test_relinking_to_same_customer_id_is_noop_for_reverse_lookup`(同一customer_idでの
再設定は削除分岐に入らず維持されることを確認)の2件を追加した。
`python3 -m unittest discover -s prototype -p "test_*.py"`(692件、+2)・
`python3 schema/validate_test_cases.py`(21件、変更なし)をいずれも再実行しパスを確認した。

- **承認待ちアクション**: 本フェーズはコード・テスト・設計文書の変更のみで、支払い・
  アカウント作成・外部公開・送信等は発生していないためpending-approval.mdへの追記なし。

## 18. 残課題・次回候補(17節分)

1. 実Firestore接続アダプタ(6節・17節のコード例含む全Protocol分)の実装自体は、
   実Firestoreプロジェクト接続がオーナー承認待ちのため着手不可(16節から継続)。
2. kura-pasha・forklift-pasha・line-reservation-aiのStripe顧客ID逆引きストアについて、
   本フェーズと同種の「再紐付け時の旧エントリ削除」実装状況の横展開確認(kura-pashaは
   フェーズ224で対応済み、line-reservation-aiは元々対応済みであることをaircon-pashaフェーズ
   306で確認済み。forklift-pashaはStripe連携コード自体が未着手のため非該当〈同フェーズ306で
   確認済み〉。本フェーズの対象であった本venture自身が最後の未対応箇所だったため、本横展開は
   本フェーズで完結し新たな次回候補は無い)。
3. 16節の「本venture自身で把握している全Protocolの実Firestore接続アダプタ設計が完了した」
   という結論は誤りで、`UsageCounterProtocol`(`cloud_function_webhook.py`、
   `UserProfileStoreProtocol`等とは別モジュールに定義)が対象から漏れていた(フェーズ301で
   発見・README.md次回候補に記録)。19節で着手する。

## 19. UsageCounterProtocol(get_count/incrementグループ)の実Firestore接続アダプタ設計

### 19.1. 背景・範囲

`UsageCounterProtocol`(`cloud_function_webhook.py`296行目)は`get_count`/`increment`の
基本2メソッドに加え、`AtomicNoticeUsageCounterProtocol.increment_and_mark_notice`
(478行目)・`set_trial_start_at_if_unset`等、既出の`UserProfileStoreProtocol`(5〜17節)
より多くのメソッド群を持つ。本venture固有の`InMemoryUsageCounter`はこれらを複数の
`dict`に分けて保持しているが、`AtomicNoticeUsageCounterProtocol`のクラスdocstring
(「usage_counterとfirst_generation_notice_storeが同一ドキュメント(同一インスタンス)を
表す場合にのみ実装される」)が示す通り、実Firestoreでは全フィールドが`usage_counter/
{user_id}`の単一ドキュメントに同居する設計である(kura-pashaの`workshop_id`単位の
`usage_counter/{workshop_id}`〈month・countの2フィールドのみ〉と同型だが、本venture
では同一ドキュメントに積む付随フィールドがより多い)。本venture自身の`UserProfileStore
Protocol`と同じ「最小の関連グループから着手する」方針(5節)に倣い、本フェーズは最も
基本的な`get_count`/`increment`(月次カウント)ペアのみを対象とし、`increment_and_mark_
notice`等の原子的な複合書き込みメソッドは次回候補とする。実Firestoreプロジェクトへの
接続自体はpending-approval.md記載の承認待ちのため、本フェーズもコード変更・外部アカウント
作成のいずれも行わない設計文書止まりである。

### 19.2. ドキュメント構造

`usage_counter/{user_id}`ドキュメントに`month`(文字列、`current_month_jst()`形式の
`"YYYY-MM"`)・`count`(整数)の2フィールドを持たせる。`get_count(user_id, month)`は
ドキュメントの`month`フィールドが引数`month`と一致する場合のみ`count`を返し、不一致
(月が変わった)・ドキュメント未存在のいずれも`0`を返す。`InMemoryUsageCounter`が
`(user_id, month)`をキーとする別々のエントリとして持つ挙動(新しい月は常に`0`から
始まる)と、単一ドキュメント+`month`フィールド比較による「月が変わっていれば実質0」
という扱いは、観測可能な振る舞いとして等価である(kura-pashaのworkshop版と同じ設計上の
対応関係)。

```python
class FirestoreUsageCounter:
    """UsageCounterProtocolの実Firestore接続実装(get_count/incrementの基本2メソッドのみ)。
    usage_counter/{user_id}ドキュメントのmonth・countフィールドを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("usage_counter")

    def get_count(self, user_id: str, month: str) -> int:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return 0
        data = snapshot.to_dict() or {}
        if data.get("month") != month:
            return 0
        return data.get("count", 0)

    def increment(self, user_id: str, month: str) -> int:
        doc_ref = self._collection.document(user_id)

        @firestore.transactional
        def _increment_in_transaction(transaction):
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {} if snapshot.exists else {}
            count_before = data.get("count", 0) if data.get("month") == month else 0
            count_after = count_before + 1
            transaction.set(doc_ref, {"month": month, "count": count_after})
            return count_after

        transaction = self._collection._client.transaction()
        return _increment_in_transaction(transaction)
```

### 19.3. 原子性の課題(kura-pashaフェーズ212と同種の懸念)

`get_count`を先に呼び、Python側で`+1`した値を`set`で書き戻す素朴な実装では、
kura-pashaの`usage_counter-provider-adapter-design.md`3節で指摘された
read-modify-write競合がそのまま再現する(同一user_idから短時間に複数のメッセージが
連投された場合、2つの生成リクエストが同じ`count_before`を読んでそれぞれ`count_before+1`
を書き込み、1回分の利用が記録から失われる)。`increment()`の戻り値(インクリメント後の
カウント値)は`limit-approaching-notification-design.md`のプラン別閾値判定にそのまま
使われるため、戻り値が不正確だと閾値到達通知の送信漏れ・重複送信に直結する。本節の
コード例では`@firestore.transactional`で読み取り→計算→書き込みを1トランザクションに
閉じ込め、kura-pashaフェーズ212の`increment_or_reset`と同じ考え方で対応した。

### 19.4. 次回候補(19節分)

1. `increment_and_mark_notice`(`count`増分・`first_generation_notice_sent`更新・
   `trial_start_at`設定を単一書き込みに相乗りさせる原子的メソッド)の実Firestore接続
   アダプタ設計。本節の`increment()`と同じトランザクション内に`first_generation_
   notice_sent`・`trial_start_at`フィールドへの書き込みを追加する形になる見込み。
2. `set_trial_start_at_if_unset`以降の残り全メソッド群(upgraded_at・trial_end_
   notified_at・trial_generation_count・trial_area_count・payment_failure系・
   subscription系、計10メソッド超)の実Firestore接続アダプタ設計。
3. 実Firestore接続アダプタ(本節・UserProfileStoreProtocol分含む全Protocol)の実装
   自体は、実Firestoreプロジェクト接続がオーナー承認待ちのため引き続き着手不可。

## 20. UsageCounterProtocol(increment_and_mark_noticeグループ)の実Firestore接続アダプタ設計

### 20.1. 背景・範囲

19節の次回候補(1)を受け、`AtomicNoticeUsageCounterProtocol.increment_and_mark_notice`
(cloud_function_webhook.py 485行目)の実Firestore接続アダプタ設計に着手する。本メソッドは
`count`増分・(`mark_notice_sent=True`の場合のみ)`first_generation_notice_sent`の更新・
(`trial_start_at`が渡され、かつ未設定の場合のみ)`trial_start_at`の設定を単一書き込みとして
行う契約であり(クラスdocstring「書き込みの原子性」準拠)、19.3節で指摘したread-modify-write
競合への対応を、`count`増分だけでなく3フィールドまとめて1トランザクションに閉じ込める必要が
ある点が本節の主眼になる。

### 20.2. 設計

19.2節で確立した`usage_counter/{user_id}`ドキュメント(`month`・`count`)に、
`first_generation_notice_sent`(bool)・`trial_start_at`(Timestamp、未設定時はフィールド
自体が存在しない)の2フィールドを追加する。`InMemoryUsageCounter.increment_and_mark_notice()`
(641〜652行目)が内部で`self.increment()`・`self.set_trial_start_at_if_unset()`を呼び出す
委譲実装になっているのに対し、Firestore版は19.2節の`increment()`のトランザクションを再利用
するのではなく、3フィールドの更新をすべて同一トランザクション内に展開する(委譲すると
`increment()`用トランザクションの中からさらに別のトランザクションを開始することになり、
Firestoreではネストしたトランザクションが扱えないため)。

```python
class FirestoreUsageCounter:
    # ...get_count/incrementは19.2節のまま...

    def increment_and_mark_notice(
        self,
        user_id: str,
        month: str,
        mark_notice_sent: bool,
        trial_start_at: Optional[datetime] = None,
    ) -> int:
        doc_ref = self._collection.document(user_id)

        @firestore.transactional
        def _increment_and_mark_notice_in_transaction(transaction):
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {} if snapshot.exists else {}
            count_before = data.get("count", 0) if data.get("month") == month else 0
            count_after = count_before + 1
            updates = {"month": month, "count": count_after}
            if mark_notice_sent:
                updates["first_generation_notice_sent"] = True
            if trial_start_at is not None and "trial_start_at" not in data:
                updates["trial_start_at"] = trial_start_at
            transaction.set(doc_ref, updates, merge=True)
            return count_after

        transaction = self._collection._client.transaction()
        return _increment_and_mark_notice_in_transaction(transaction)
```

### 20.3. 検討事項

- **`trial_start_at`の「未設定時のみ」判定をトランザクション内に含める理由**: `set_trial_
  start_at_if_unset()`単体の冪等性(「既に値がある場合は上書きしない」)を、19.2節の
  `increment()`トランザクションの外で後から`set_trial_start_at_if_unset()`を別呼び出しする
  実装にすると、2回の書き込みに割れてしまい、`first-generation-notice-implementation-
  design.md`3節「書き込みの原子性」の要件(1回のドキュメント更新で完結させる)を満たせない。
  本節のコード例では、`trial_start_at`の有無判定を同一トランザクション内の`snapshot`
  読み取り結果(`data`)に対して行うことで、原子性を保ったまま冪等性も両立させた。
- **`merge=True`を使う理由**: 19.2節の`increment()`は常に`month`・`count`の2フィールドのみを
  書くため`transaction.set(doc_ref, {...})`(merge無し)で足りたが、本メソッドは
  `first_generation_notice_sent`・`trial_start_at`が既にドキュメントに存在する場合に
  それらを消してしまわないよう(`mark_notice_sent=False`かつ`trial_start_at=None`で
  呼ばれた場合、`count`のみ更新したい)、`merge=True`を指定する必要がある。
- **委譲実装にしなかった理由**: `InMemoryUsageCounter`は`increment()`・`set_trial_start_
  at_if_unset()`への委譲で実装が簡潔になっているが、Firestoreの`@firestore.transactional`
  デコレータは呼び出しのたびに新しいトランザクションを開始するため、19.2節の`increment()`を
  そのまま呼び出すと「トランザクションの中で別のトランザクションを開始する」形になり
  `InvalidArgument`相当のエラーになる(Firestoreクライアントライブラリの制約)。このため
  Firestore版のみ、3フィールドの更新をすべて展開した単一トランザクションとして書き直した
  (観測可能な振る舞いはInMemory版と等価)。
- **戻り値**: `increment()`と同じく「インクリメント後のカウント値」を返す契約
  (cloud_function_webhook.py 495行目)を満たす。

### 20.4. 次回候補(20節分)

1. 本節で扱わなかった`FirstGenerationNoticeStoreProtocol`単体(`has_sent`/`mark_sent`、
   `increment_and_mark_notice`を経由しない呼び出し経路向け)の実Firestore接続アダプタ設計。
   `usage_counter`と同一ドキュメントの`first_generation_notice_sent`フィールドを読み書き
   するだけで足りる見込みだが、`increment_and_mark_notice`側(本節)との同時書き込みが
   起きないことを呼び出し元コードで確認する必要がある。
2. `set_trial_start_at_if_unset`以降の残り全メソッド群(upgraded_at・trial_end_
   notified_at・trial_generation_count・trial_area_count・payment_failure系・
   subscription系、計10メソッド超)の実Firestore接続アダプタ設計(19.4節(2)から継続)。
3. 実Firestore接続アダプタ(本節・UserProfileStoreProtocol分含む全Protocol)の実装
   自体は、実Firestoreプロジェクト接続がオーナー承認待ちのため引き続き着手不可。
4. 他venture・アイデア領域の前進。

(2026-10-17 08:00 UTC定例更新で発見・修正: 本節末尾に「4. 他venture・アイデア領域の
前進。」が重複して2行記載されていた記載漏れを1行に修正した。内容面の変更ではない。)

## 21. FirstGenerationNoticeStoreProtocol単体の実Firestore接続アダプタ設計

### 21.1. 背景・範囲

20節の次回候補(1)を受け、`FirstGenerationNoticeStoreProtocol`(`cloud_function_
webhook.py`672行目、`has_sent`/`mark_sent`の2メソッドのみ)単体の実Firestore接続アダプタ
設計に着手する。本venture本番コードの実際の呼び出し経路
(`cloud_function_webhook.py`1519〜1541行目・1580〜1581行目)では、`usage_counter`と
`first_generation_notice_store`に同一インスタンスを渡し、かつそのインスタンスが
`increment_and_mark_notice`に対応している場合は常に20節の単一トランザクション経路が使われ、
本節で設計する独立クラスは呼ばれない(`notice_marked_atomically`が`True`になり、1581行目の
`first_generation_notice_store.mark_sent(notice_user_id)`はスキップされる)。本節が対象とする
のは、両者に別インスタンスを渡す(`usage_counter is first_generation_notice_store`が`False`、
または`increment_and_mark_notice`未実装の)呼び出し経路で、`has_sent`は1491行目で
`usage_counter`の種類を問わず常に呼ばれ、`mark_sent`は1580行目の`not notice_marked_
atomically`分岐でのみ呼ばれる。実Firestoreプロジェクトへの接続自体はpending-approval.md
記載の承認待ちのため、本フェーズもコード変更・外部アカウント作成のいずれも行わない設計文書
止まりである。

### 21.2. 設計

19.2節で確立した`usage_counter/{user_id}`ドキュメントに同居する`first_generation_notice_sent`
(bool、未設定時はフィールド自体が存在しない)フィールドを読み書きする。本節のクラスは20節の
`FirestoreUsageCounter`とは別クラスとして定義するが、同じコレクション・同じドキュメントID
(`user_id`)を参照する(`InMemoryFirstGenerationNoticeStore`がset(集合)で保持する「送信済み
user_idの集合」と、ドキュメント内の1フィールドの有無は観測可能な振る舞いとして等価)。

```python
class FirestoreFirstGenerationNoticeStore:
    """FirstGenerationNoticeStoreProtocolの実Firestore接続実装(has_sent/mark_sentのみ)。
    19.2節のFirestoreUsageCounterと同じusage_counter/{user_id}ドキュメントの
    first_generation_notice_sentフィールドを読み書きする、独立したcollection・documentを
    新設しない薄いアダプタ。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("usage_counter")

    def has_sent(self, user_id: str) -> bool:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return False
        return bool((snapshot.to_dict() or {}).get("first_generation_notice_sent", False))

    def mark_sent(self, user_id: str) -> None:
        self._collection.document(user_id).set(
            {"first_generation_notice_sent": True}, merge=True,
        )
```

### 21.3. 検討事項

- **`merge=True`を使う理由**: 20.3節の`increment_and_mark_notice`と同じ理由で、本クラス単体の
  `mark_sent`が`month`・`count`・`trial_start_at`等、同一ドキュメントの他フィールドを消して
  しまわないようにする必要がある。
- **トランザクションを使わない理由**: `mark_sent`は常に`True`への単純な上書きで、読み取った
  現在値に依存する計算を行わない(20節の`increment`のような`count_before + 1`相当の計算が
  無い)ため、`has_sent`(読み取り)と`mark_sent`(書き込み)の間にread-modify-write競合は
  発生しない。`InMemoryFirstGenerationNoticeStore.mark_sent()`も同様に集合への単純な追加
  (`self._sent.add(user_id)`相当)であり、トランザクション無しでも観測可能な振る舞いは
  InMemory版と等価である。
- **本クラスが実際に使われる場面**: 21.1節の通り、本venture本番コードの設計上の想定配線
  (`usage_counter`と`first_generation_notice_store`に同一の`FirestoreUsageCounter`インスタンス
  を渡す)では本クラスは呼ばれず、20節の`increment_and_mark_notice`に一本化される。本節は
  「両者に別インスタンスを渡すテストコード・将来の配線変更」に備えた完全性のための設計であり、
  `FirestoreUsageCounter`自体に`has_sent`/`mark_sent`を実装すれば本クラスを別途インスタンス化
  する必要自体がなくなる(どちらの構成でもProtocol上は区別がつかない)。

### 21.4. 次回候補(21節分)

1. `set_trial_start_at_if_unset`以降の残り全メソッド群(upgraded_at・trial_end_
   notified_at・trial_generation_count・trial_area_count・payment_failure系・
   subscription系、計10メソッド超)の実Firestore接続アダプタ設計(19.4節(2)・20.4節(2)から
   継続。本venture固有の`UsageCounterProtocol`関連では最後に残る大きなグループ)。
2. 実Firestore接続アダプタ(本節・UserProfileStoreProtocol分含む全Protocol)の実装自体は、
   実Firestoreプロジェクト接続がオーナー承認待ちのため引き続き着手不可。
3. 他venture・アイデア領域の前進。

最終更新: 2026-10-17 09:00 UTC(フェーズ304: 20節次回候補(1)を受け、
`FirstGenerationNoticeStoreProtocol`単体〈has_sent/mark_sent〉の実Firestore接続アダプタを
設計。19.2節のusage_counter/{user_id}ドキュメントに同居するfirst_generation_notice_sent
フィールドを読み書きする薄いアダプタとし、本venture本番コードの想定配線では実際には
increment_and_mark_noticeに一本化されるため呼ばれないことを確認した。あわせて20節末尾の
次回候補リストに残っていた記載重複〈「4. 他venture・アイデア領域の前進。」が2行〉を修正した。
コード変更なし、設計文書のみのため回帰テストの実行対象外)

## 22. UsageCounterProtocol(upgraded_at・trial_end_notified_atグループ)の実Firestore接続アダプタ設計

### 22.1. 背景・範囲

21.4節(1)の次回候補群のうち、本節では`set_upgraded_at_if_unset`/`get_upgraded_at`・
`set_trial_end_notified_at`/`get_trial_end_notified_at`の計4メソッドを対象とする
(`cloud_function_webhook.py`316〜336行目)。残る`trial_generation_count`・
`trial_area_count`・`payment_failure`系・`subscription`系は次回候補に持ち越す。
いずれも19.2節で確立した`usage_counter/{user_id}`ドキュメントに追加フィールドを
積む設計であり、独立したcollectionやdocumentを新設しない点は21節の
`FirstGenerationNoticeStoreProtocol`と同じである。本節は19.2節の`FirestoreUsageCounter`
クラス自体にメソッドを追加する形で設計する(21節とは異なり、本節の2メソッド群は
`UsageCounterProtocol`自身のメソッドであり別Protocolではないため)。

### 22.2. 設計

`upgraded_at`は`set_trial_start_at_if_unset`(20節)と同じ「既に値がある場合は上書きしない」
冪等性を持つため、読み取り→未設定判定→書き込みをトランザクションに閉じ込める。
`trial_end_notified_at`は`select_due_trial_end_notifications()`側(呼び出し元)で既に
`trial_end_notified_at is None`のユーザーのみに絞り込まれる(326〜332行目のdocstring)
ため、本メソッド自体は単純な上書きでよく、トランザクションは不要である。

```python
class FirestoreUsageCounter:
    # ...(19.2節のget_count/increment、20節のincrement_and_mark_noticeに続けて追加)

    def set_upgraded_at_if_unset(self, user_id: str, upgraded_at: datetime) -> None:
        doc_ref = self._collection.document(user_id)

        @firestore.transactional
        def _set_if_unset(transaction):
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {} if snapshot.exists else {}
            if "upgraded_at" in data:
                return
            transaction.set(doc_ref, {"upgraded_at": upgraded_at}, merge=True)

        transaction = self._collection._client.transaction()
        _set_if_unset(transaction)

    def get_upgraded_at(self, user_id: str) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("upgraded_at")

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        self._collection.document(user_id).set(
            {"trial_end_notified_at": notified_at}, merge=True,
        )

    def get_trial_end_notified_at(self, user_id: str) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("trial_end_notified_at")
```

### 22.3. 検討事項

- **`set_upgraded_at_if_unset`だけトランザクションを使う理由**: `set_trial_start_
  at_if_unset`と同じ「1回だけ設定」契約だが、本節では`increment()`等の他の書き込みと
  同一トランザクションに相乗りさせる経路が無い(20節の`increment_and_mark_notice`とは
  異なり、`checkout.session.completed`受信時に単独で呼ばれる)。そのため`has_sent`/
  `mark_sent`(21節、トランザクション不要)とは異なり、読み取り→判定→書き込みの間に
  同一user_idからの重複Webhook配信(Stripeの配信保証はat-least-onceであり再送され得る)
  が競合する可能性があり、素朴な「`get_upgraded_at`で読んでNoneなら`set`」という
  2回の独立呼び出しでは、ごく稀に2回の重複配信が共にNoneを読んで`upgraded_at`を
  2回とも書き込み、2回目の書き込み時刻が1回目を上書きしてしまうrace conditionが
  起こり得る(19.3節のカウンタ競合と同種だが、トライアル開始日時という「最初の値を
  保持し続けるべき」フィールドでの発生のため、影響は「有料転換日時がわずかに
  ずれて記録される」という比較的軽微な不整合に留まる)。
- **`merge=True`を使う理由**: 20・21節と同じ理由で、`month`・`count`・
  `first_generation_notice_sent`・`trial_start_at`等、同一ドキュメントの他フィールドを
  消してしまわないようにする必要がある。
- **`get_upgraded_at`/`get_trial_end_notified_at`がトランザクション不要な理由**:
  いずれも単純な読み取りのみで、読み取った値を基に計算して書き戻す処理が無いため。

### 22.4. 次回候補(22節分)

1. 残る`trial_generation_count`・`trial_area_count`の実Firestore接続アダプタ設計
   (いずれも`increment_*`系で19.3節と同種の原子性課題への対応が必要)。
2. `payment_failure`系・`subscription`系(計10メソッド超)の実Firestore接続アダプタ設計。
3. 実Firestore接続アダプタ(本節・UserProfileStoreProtocol分含む全Protocol)の実装自体は、
   実Firestoreプロジェクト接続がオーナー承認待ちのため引き続き着手不可。
4. 他venture・アイデア領域の前進。

最終更新: 2026-10-17 10:00 UTC(フェーズ305: 21節次回候補(1)を受け、
`UsageCounterProtocol`の`upgraded_at`・`trial_end_notified_at`グループ(計4メソッド)の
実Firestore接続アダプタを設計。19.2節の`FirestoreUsageCounter`クラスへのメソッド追加
として設計し、`set_upgraded_at_if_unset`は重複Webhook配信によるrace conditionを避けるため
トランザクション化、`set_trial_end_notified_at`は呼び出し元側の絞り込みに依存して単純な
上書きとした。コード変更なし、文書追加のみのため回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(761件)・
`python3 schema/validate_test_cases.py`(21件)を実行しいずれも変更なしでパスすることを
確認した(回帰なし)。承認が必要なアクションは発生していないためpending-approval.mdへの
追記なし)

## 23. UsageCounterProtocol(trial_generation_count・trial_area_countグループ)の実Firestore接続アダプタ設計

### 23.1. 背景・範囲

22.4節の次回候補(1)を受け、`increment_trial_generation_count`/`get_trial_generation_count`・
`increment_trial_area_count`/`get_trial_area_count`の計4メソッドを対象とする
(`cloud_function_webhook.py`338〜364行目)。両カウンタは`trial-end-notification-design.md`
3節の通知文言(「投稿文生成: ○回」「エリア更新: ○件」)に使うトライアル期間限定の累計値で、
月次でリセットされる`get_count`/`increment`(19節、Stripe請求・上限判定用)とは別に、
`trial_start_at`〜通知時点の期間をまたいで月境界の影響を受けずに積み上げる契約である
(338〜342行目docstring)。いずれも未実装でも`hasattr()`判定により後方互換的にスキップされる
設計(フェーズ109以前の単純化式へのフォールバック)のため、本節で設計するアダプタが
未配線の間も既存の通知処理自体は壊れない。19節と同じく`usage_counter/{user_id}`
ドキュメントに追加フィールドを積む設計であり、19.2節の`FirestoreUsageCounter`クラスへの
メソッド追加として設計する。実Firestoreプロジェクトへの接続自体はpending-approval.md記載の
承認待ちのため、本フェーズもコード変更・外部アカウント作成のいずれも行わない設計文書止まりである。

### 23.2. 設計

両メソッドとも「インクリメント後の累計値を返す」契約(343行目・357行目)であり、19.3節で
`increment()`に適用したread-modify-write競合対策がそのまま当てはまる。`increment_trial_
area_count`は加算量が固定の`+1`ではなく引数`area_count`(1回の生成におけるhistory_rowsの
要素数)であるため、トランザクション内で読み取った現在値に`area_count`を加算する形に
する。`get_*`側は単純な読み取りのみで計算を伴わないため、19.2節の`get_count`と同じく
トランザクション不要である。

```python
class FirestoreUsageCounter:
    # ...(19.2節のget_count/increment、20〜22節の各メソッドに続けて追加)

    def increment_trial_generation_count(self, user_id: str) -> int:
        doc_ref = self._collection.document(user_id)

        @firestore.transactional
        def _increment_in_transaction(transaction):
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {} if snapshot.exists else {}
            count_after = data.get("trial_generation_count", 0) + 1
            transaction.set(
                doc_ref, {"trial_generation_count": count_after}, merge=True,
            )
            return count_after

        transaction = self._collection._client.transaction()
        return _increment_in_transaction(transaction)

    def get_trial_generation_count(self, user_id: str) -> int:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return 0
        return (snapshot.to_dict() or {}).get("trial_generation_count", 0)

    def increment_trial_area_count(self, user_id: str, area_count: int) -> int:
        doc_ref = self._collection.document(user_id)

        @firestore.transactional
        def _increment_in_transaction(transaction):
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() or {} if snapshot.exists else {}
            count_after = data.get("trial_area_count", 0) + area_count
            transaction.set(
                doc_ref, {"trial_area_count": count_after}, merge=True,
            )
            return count_after

        transaction = self._collection._client.transaction()
        return _increment_in_transaction(transaction)

    def get_trial_area_count(self, user_id: str) -> int:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return 0
        return (snapshot.to_dict() or {}).get("trial_area_count", 0)
```

### 23.3. 検討事項

- **両方トランザクション化する理由**: 19.3節で指摘した「同一user_idからの短時間の連投に
  よるread-modify-write競合」は、月次カウンタ(`count`)だけでなくこの2つの専用カウンタにも
  同様に当てはまる。特に`increment_trial_generation_count`の戻り値は`trial_end_scheduler.py`
  側の通知文言生成に直接使われるため(339〜342行目)、競合により1回分の生成がカウントから
  失われると、トライアル終了通知の文言(「投稿文生成: ○回」)がオーナーに過少な実績として
  表示されてしまう。
- **`increment_trial_area_count`の加算量が可変である点**: 19節・20〜22節の既存メソッドは
  いずれも固定`+1`だが、本メソッドは引数`area_count`を加算する点が異なる。トランザクション
  内で読み取った現在値に対して加算する設計のため、固定`+1`と同じ排他制御で対応でき、
  追加の設計上の懸念は生じない。
- **`merge=True`を使う理由**: 19〜22節と同じ理由で、`month`・`count`・
  `first_generation_notice_sent`・`trial_start_at`・`upgraded_at`・`trial_end_notified_at`等、
  同一ドキュメントの他フィールドを消してしまわないようにする必要がある。
- **両カウンタに上限や月次リセットが無い点**: `trial-end-notification-design.md`の通知は
  トライアル終了時に1回だけ送られる想定のため、`get_count`/`increment`(19節)のような
  月境界でのリセット判定は不要で、`usage_counter/{user_id}`ドキュメントが存在する限り
  単調増加する。トライアル再開(2回目のトライアル)の扱いは現時点のドキュストアでは
  想定されておらず、本節の設計対象外とする(次回候補)。

### 23.4. 次回候補(23節分)

1. `payment_failure`系・`subscription`系(計10メソッド超)の実Firestore接続アダプタ設計
   (本venture固有の`UsageCounterProtocol`関連で最後に残る大きなグループ)。
2. トライアル再開(2回目以降のトライアル)時の`trial_generation_count`・`trial_area_count`の
   扱い(リセットすべきか、累計を維持すべきか)の検討(本節で設計対象外とした残課題)。
3. 実Firestore接続アダプタ(本節・UserProfileStoreProtocol分含む全Protocol)の実装自体は、
   実Firestoreプロジェクト接続がオーナー承認待ちのため引き続き着手不可。
4. 他venture・アイデア領域の前進。

最終更新: 2026-10-17 14:00 UTC(フェーズ306: 22節次回候補(1)を受け、
`UsageCounterProtocol`の`trial_generation_count`・`trial_area_count`グループ(計4メソッド)の
実Firestore接続アダプタ設計に着手。19.2節の`FirestoreUsageCounter`クラスへのメソッド追加
として設計し、両方とも19.3節と同種のread-modify-write競合を避けるためトランザクション化
(`increment_trial_area_count`は固定+1ではなく可変の`area_count`を加算)。コード変更なし、
文書追加のみのため回帰確認として`python3 -m unittest discover -s prototype -p "test_*.py"`
(761件、変更なし)・`python3 schema/validate_test_cases.py`(21件、変更なし)を実行し
いずれも変更なしでパスすることを確認した(回帰なし)。承認が必要なアクションは発生していないため
pending-approval.mdへの追記なし)

## 24. UsageCounterProtocol(payment_failure_detected_at・payment_failure_reminder_sent_atグループ)の実Firestore接続アダプタ設計

### 24.1. 背景・範囲

23.4節の次回候補(1)「`payment_failure`系・`subscription`系(計10メソッド超)」のうち、
本節では`set_payment_failure_detected_at`/`get_payment_failure_detected_at`/
`clear_payment_failure_detected_at`・`set_payment_failure_reminder_sent_at`/
`get_payment_failure_reminder_sent_at`/`clear_payment_failure_reminder_sent_at`の計6メソッド
(`cloud_function_webhook.py`366〜396行目)を対象とする。残る`payment_suspension_owner_
notified_at`グループ・`subscription_canceled_at`グループ・3種の`*_event_time`
(順序ガード用)は次回候補に持ち越す。6メソッドとも19.2節で確立した
`usage_counter/{user_id}`ドキュメントへの追加フィールドとして設計し、
`FirestoreUsageCounter`クラスへのメソッド追加とする。両フィールドは
payment-failure-dunning-design.md 6節・payment-failure-reminder-scheduler-design.md 3節の
通り、決済失敗(dunning)フローの猶予期間計算・リマインド送信済み判定に使う一対のフラグで、
`invoice.payment_succeeded`による復旧時にいずれも消去される(366〜398行目docstring)。

### 24.2. 設計

いずれのメソッドも19.3節の`increment()`・22.3節の`set_upgraded_at_if_unset`のような
「読み取った現在値に基づいて書き戻す」計算を伴わないため、トランザクションは不要である。
`set_payment_failure_detected_at`は(`set_upgraded_at_if_unset`と異なり)「1回だけ」では
なく、複数回の決済失敗検知のたびに最新の検知時刻で上書きする単純な書き込み契約
(366〜372行目docstring)であり、`set_payment_failure_reminder_sent_at`も
`set_trial_end_notified_at`(22節)と同じく呼び出し元(`select_due_payment_failure_
reminders()`)側の絞り込みに依存する単純な上書きでよい。`clear_*`は9節(aircon-pasha 11節と
同じ結論)で確認した`None`書き込みで表現する方針を踏襲する。

```python
class FirestoreUsageCounter:
    # ...(19.2節のget_count/increment、20〜23節の各メソッドに続けて追加)

    def set_payment_failure_detected_at(
        self, user_id: str, detected_at: datetime
    ) -> None:
        self._collection.document(user_id).set(
            {"payment_failure_detected_at": detected_at}, merge=True,
        )

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("payment_failure_detected_at")

    def clear_payment_failure_detected_at(self, user_id: str) -> None:
        self._collection.document(user_id).set(
            {"payment_failure_detected_at": None}, merge=True,
        )

    def set_payment_failure_reminder_sent_at(
        self, user_id: str, sent_at: datetime
    ) -> None:
        self._collection.document(user_id).set(
            {"payment_failure_reminder_sent_at": sent_at}, merge=True,
        )

    def get_payment_failure_reminder_sent_at(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("payment_failure_reminder_sent_at")

    def clear_payment_failure_reminder_sent_at(self, user_id: str) -> None:
        self._collection.document(user_id).set(
            {"payment_failure_reminder_sent_at": None}, merge=True,
        )
```

### 24.3. 検討事項

- **`set_payment_failure_detected_at`がトランザクション不要な理由**: `set_upgraded_at_
  if_unset`(22節)は「既存値があれば書かない」冪等性のため読み取り→判定→書き込みを
  アトミックにする必要があったが、本メソッドは複数回の検知のたびに最新の検知時刻へ
  単純に上書きする契約(366〜372行目docstring、「古い検知時刻を残す理由がない」)のため、
  読み取りを介さない`set(merge=True)`一発で契約を満たせる。同一user_idからの重複
  Webhook配信(at-least-once)が同時に2回`set`を呼んでも、最終的にどちらかの`detected_at`
  が残るだけで契約上の不整合は生じない(通常は同一イベントの`event.created`に基づく
  ほぼ同一の時刻になる)。
- **`clear_*`を`None`書き込みで表現できる根拠**: 9.3節と同じ理由。`InMemoryUsageCounter`
  相当のテストダブル(test_payment_failure_reminder_scheduler.py・test_payment_recovery_
  notification.py等)の`get_*`はキー不在・`None`値のいずれも`None`として返す前提のため、
  Firestore側の`null`書き込みと観測可能な挙動が一致する。
- **一対のフィールドを同一節で設計した理由**: `payment-failure-reminder-scheduler-
  design.md`3節の通り、両フィールドは同じdunningフロー(検知→猶予期間→リマインド→
  (復旧 or 制限モード))の中で常にペアで読み書きされ(`payment_recovery_notification.py`
  191〜200行目の復旧処理も両方を同時にclearする)、設計上分離する理由がないため、
  19節(get_count/increment)・22節(upgraded_at/trial_end_notified_at)と同様に
  関連フィールドをまとめて1節で扱う方針を踏襲した。
- **`merge=True`を使う理由**: 19〜23節と同じ理由で、同一ドキュメントの他フィールド
  (`month`・`count`・`trial_generation_count`等)を消してしまわないようにする必要がある。

### 24.4. 次回候補(24節分)

1. 残る`payment_suspension_owner_notified_at`グループ(3メソッド、24節と同型の
   「単純上書き+None clear」で設計できる見込み)の実Firestore接続アダプタ設計。
2. `subscription_canceled_at`グループ(3メソッド)・3種の`*_event_time`(順序ガード用、
   いずれも単純な上書き・読み取りのみで設計できる見込み)の実Firestore接続アダプタ設計。
3. 実Firestore接続アダプタ(本節・UserProfileStoreProtocol分含む全Protocol)の実装自体は、
   実Firestoreプロジェクト接続がオーナー承認待ちのため引き続き着手不可。
4. 他venture・アイデア領域の前進。

最終更新: 2026-10-17 16:00 UTC(フェーズ307: 23節次回候補(1)を受け、
`UsageCounterProtocol`の`payment_failure_detected_at`・`payment_failure_reminder_sent_at`
グループ(計6メソッド)の実Firestore接続アダプタ設計に着手。19.2節の`FirestoreUsageCounter`
クラスへのメソッド追加として設計し、いずれも読み取り→書き戻しの計算を伴わないため
トランザクション不要、`clear_*`は9節(aircon-pasha 11節)と同じ`None`書き込みで表現する
方針を踏襲した。コード変更なし、文書追加のみのため回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(761件、変更なし)・
`python3 schema/validate_test_cases.py`(21件、変更なし)を実行しいずれも変更なしで
パスすることを確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし)
