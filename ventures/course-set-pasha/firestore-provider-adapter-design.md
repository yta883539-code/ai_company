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
  `InMemoryUserProfileStore.set_stripe_customer_id`(`application_form_submission_flow.py`
  178〜180行目)自身も旧`_user_ids_by_stripe_customer_id`エントリを明示的に削除しておらず、
  本venture自身のInMemory実装はaircon-pashaの元の設計(5.3節、旧インデックス削除を次回候補と
  した簡潔版)と契約が一致していることを確認した。line-reservation-aiのInMemory実装
  (`store_profile_store.py`)が旧エントリ削除を既に実装しておりaircon-pashaの元設計と
  契約差異があったのとは異なり、本ventureでは契約差異は発生していないため、本グループの
  Firestoreアダプタ設計はaircon-pashaの元の設計をそのまま横展開してよいと判断した
  (旧インデックス削除は以後も次回候補のまま据え置く)。
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
