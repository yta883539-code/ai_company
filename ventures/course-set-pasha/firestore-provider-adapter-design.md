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

## 7. 残課題・次回候補(6節分)

- 残りのグループ(`is_following`+`all_user_ids`・
  `blocked_but_billing_owner_notified_at`系3メソッド・`plan`・
  `checkout_session_completed_event_time`)の実Firestore接続アダプタ設計。いずれも
  5節・6節と同じ`_doc_ref(user_id)`ヘルパーの上に`merge=True`の部分更新として
  素直に実装できる見込みだが、本フェーズでは対象外。
- 承認後は、`application_form_submission_flow.py`呼び出し側の`UserProfileStoreProtocol`
  実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが完了する設計になっていることを、
  結合実装時に確認する(ただし全グループの実装完了が前提)。
