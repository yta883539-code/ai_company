# LinkingCodeStoreProtocol の実Firestore接続アダプタ設計

## 1. 背景

`prototype/user_id_linking.py`には`LinkingCodeStoreProtocol`(`save`/`get`/`delete`/
`items`)と、検証用の`InMemoryLinkingCodeStore`スタブのみが存在し、実際の
`pending_links/{code}`ドキュメント(user-account-linking-design.md 117行目)を読み書きする
具象実装はまだ存在しない。同モジュールにはもう1つ`UserProfileStoreProtocol`(20件超の
get/setメソッドを持つ`user_profile/{user_id}`ドキュメントの包括的なProtocol)があるが、
メソッド数・フィールド数が大きく一度に設計すると検討が発散するため、本フェーズは対象外とし
次回候補として残す(kura-pashaフェーズ209が複数Protocolのうち最小のものから着手した方針を
踏襲)。

本ドキュメントは、実Firestoreプロジェクトへの接続(GCPアカウント・課金設定を伴う、
pending-approval.md記載のLINE公式アカウント開設等と同種の承認待ち事項)が承認されるまでの
間に、接続先が決まった際すぐ実装に移れるよう、`LinkingCodeStoreProtocol`の具象クラスの設計を
先行して詰めておくもの。コード変更・外部アカウント作成のいずれも行わない。

## 2. 設計方針

`pending_links/{code}`は`code`をドキュメントIDとする単純な1ドキュメント1エントリの構造
(user-account-linking-design.md 5節)のため、`save`/`get`/`delete`はドキュメント単位の
読み書きで素直に実装できる。`items()`のみ、期限切れパージ(`purge_expired_links()`、
`user_id_linking.py`897行目)のために全エントリを列挙する必要があり、`pending_links`
コレクション全体の`stream()`が必要になる。

```python
class FirestorePendingLinkStore:
    """LinkingCodeStoreProtocolの実Firestore接続実装。
    pending_links/{code}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("pending_links")

    def save(self, code: str, entry: PendingLink) -> None:
        self._collection.document(code).set(
            {
                "form_submission_id": entry.form_submission_id,
                "business_name": entry.business_name,
                "business_type": entry.business_type,
                "email": entry.email,
                "issued_at": entry.issued_at,
            }
        )

    def get(self, code: str) -> Optional[PendingLink]:
        try:
            snapshot = self._collection.document(code).get()
        except Exception:
            # ネットワークエラー・権限エラー等はProtocol契約上の「未発見」側
            # (Noneを返す)に合流させる。issue_linking_code_on_form_submission()の
            # 重複チェック(store.get(code) is None)がエラー時に誤って「コード未使用」と
            # 解釈し再発行を妨げないよう、呼び出し元には例外を伝播させない。
            return None
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        return PendingLink(
            form_submission_id=data.get("form_submission_id", ""),
            business_name=data.get("business_name", ""),
            business_type=data.get("business_type", ""),
            email=data.get("email", ""),
            issued_at=data["issued_at"],
        )

    def delete(self, code: str) -> None:
        self._collection.document(code).delete()

    def items(self) -> Iterable[Tuple[str, PendingLink]]:
        for snapshot in self._collection.stream():
            data = snapshot.to_dict() or {}
            yield (
                snapshot.id,
                PendingLink(
                    form_submission_id=data.get("form_submission_id", ""),
                    business_name=data.get("business_name", ""),
                    business_type=data.get("business_type", ""),
                    email=data.get("email", ""),
                    issued_at=data["issued_at"],
                ),
            )
```

## 3. 検討事項

- **`get()`の例外方針はno-op系とは非対称**: `UserProfileStoreProtocol`側の既存設計
  (`set_*`系は未知の`user_id`に対して何もしない安全側no-op)とは異なり、`get()`の
  例外時は「未発見」(`None`)に倒す。`resolve_linking_code()`(`user_id_linking.py`
  810行目付近)の「not found」エラーメッセージが「コードとして無効/使用済み/期限切れで
  パージ済み/一度も発行されていない」のいずれかを区別しないのと同じ粒度であり、
  一時的なFirestore接続エラーも同じメッセージに合流させることで実害がない
  (ユーザーは単に連携トークを再試行する)と判断した。
- **`items()`のコスト**: `purge_expired_links()`は定期実行(日次バッチ想定)のたびに
  `pending_links`コレクション全件を読み取る。`_LINK_TTL`が24時間であるため、
  `issued_at`に対する複合インデックス+範囲クエリ(`issued_at < now - TTL`のみ取得)で
  読み取り件数を絞ることも可能だが、本venture想定トラフィック(小規模事業者向け、
  同時に未解決の連携コードは少数)では全件`stream()`でも無料枠に収まる前提
  (subscription-billing-cost-estimate.md想定トラフィックと同程度)のため、
  クエリ最適化は過剰設計として見送る。将来的に未解決コード数が増えた場合に再検討する。
- **書き込み方式**: `save()`は`set()`(フィールド全体の置き換え)を使う。
  `pending_links/{code}`は発行時に1回書き込まれた後は`delete()`されるだけの
  使い切りトークンであり、`UserProfileStoreProtocol`側の`merge=True`部分更新方針
  (line-reservation-ai firestore-provider-adapter-design.md・kura-pasha同名ドキュメント
  参照)とは異なり、既存フィールドとの部分マージを考慮する必要がないため。
- **依存ライブラリ**: `google-cloud-firestore`を想定(tech-stack.md想定と一致)。
  `firestore_client`をコンストラクタ注入する形とし、ライブラリの具体的なクライアント型には
  依存しない(テスト時は`InMemoryLinkingCodeStore`を使い続け、本クラスは実クライアント
  接続後の結合テストでのみ使用する)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体は外部サービス側のアカウント作成・
  課金設定を伴うため、オーナー承認待ち(pending-approval.md参照)。本設計のコードは
  承認後の結合実装フェーズまでコミットしない。
- `UserProfileStoreProtocol`(`user_profile/{user_id}`、20件超のget/setメソッド)の
  実Firestore接続アダプタ設計は本フェーズの対象外とし、次回候補として残していたが、
  フェーズ295で基盤3メソッド(`save`/`get`/`exists`)+Stripe顧客ID逆引きグループに
  着手した(5節)。残りのグループは引き続き次回候補として段階的に設計する。
- 承認後は、`cloud_function_webhook.py`・`user_id_linking.py`呼び出し側の
  `LinkingCodeStoreProtocol`実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが
  完了する設計になっていることを、結合実装時に確認する。

## 5. UserProfileStoreProtocol(基盤3メソッド+Stripe顧客IDグループ)の実Firestore接続アダプタ設計

### 5.1. 背景・範囲

フェーズ294の次回候補(4節)を受け、`UserProfileStoreProtocol`(20件超のget/setメソッドを
持つ`user_profile/{user_id}`の包括的Protocol)の実Firestore接続アダプタ設計に、
kura-pashaフェーズ209と同じ「最小の関連グループから着手する」方針で着手する。

本フェーズは以下の2グループに限定する。

1. **基盤3メソッド**: `save`/`get`/`exists`。`UserProfile`データクラス全体
   (`business_name`・`business_type`・`email`・`linked_at`等、user-account-linking-
   design.md 5節で確定した連携時必須フィールドと、以降のフェーズで追加された20件超の
   オプショナルフィールド)を1ドキュメントとして読み書きする、他の全get/setメソッドの
   前提となるグループ。`save()`は連携成立時(`resolve_linking_code()`)に1回だけ
   呼ばれる新規ドキュメント作成であり、既存ドキュメントへの後続の`set_*`系メソッドは
   いずれも個別フィールドの部分更新のため、本グループの設計は後続グループが
   共通で使う`_doc_ref(user_id)`ヘルパーも合わせて確立する。
2. **Stripe顧客IDグループ**: `set_stripe_customer_id`/`get_user_id_by_stripe_customer_id`/
   `get_stripe_customer_id`。`stripe_customer_id`の順引き・逆引きという単一の関心に閉じて
   おり、`checkout-session-completed-handling-design.md`・`portal-session-provider-
   design.md`(フェーズ176)の両方から参照される、比較的独立度の高いグループのため
   次に着手しやすいと判断した。

他のグループ(trial系3フィールド・payment_failure系・current_plan_id・is_following+
all_user_ids・owner_notified_at系4種・event_time系4種等)は、それぞれが独立した
duck typing用の薄いProtocol(`CurrentPlanStoreProtocol`等)に対応しており、本フェーズの
対象外として次回候補に残す(6節)。

### 5.2. 設計

`user_profile/{user_id}`は`user_id`をドキュメントIDとする1ドキュメント1エントリの構造
(user-account-linking-design.md 5節)。基盤3メソッドはドキュメント単位の読み書きで
素直に実装できる。Stripe顧客IDの逆引き(`get_user_id_by_stripe_customer_id`)は、
`user_profile`コレクション全体のクエリ(`where("stripe_customer_id", "==", ...)`)でも
実現できるが、`customer.subscription.*`イベント受信のたびにクエリを発行するより、
専用の逆引きコレクション`stripe_customer_index/{stripe_customer_id}`(値は`user_id`の
文字列)を`set_stripe_customer_id`実行時に同時書き込みする方式を採用する
(`InMemoryUserProfileStore`が`_user_ids_by_stripe_customer_id`辞書を別持ちしている
設計〈prototype/user_id_linking.py 528行目付近〉と対応させるため)。Firestoreは
複数ドキュメントへの原子的な書き込みに`WriteBatch`が使えるため、`set_stripe_customer_id`は
`user_profile/{user_id}`の`stripe_customer_id`フィールード更新と`stripe_customer_index/
{stripe_customer_id}`ドキュメントの作成をバッチで実行し、部分失敗(片方のみ書き込まれる
不整合)を避ける。

```python
class FirestoreUserProfileStore:
    """UserProfileStoreProtocolの実Firestore接続実装(基盤3メソッド+Stripe顧客ID
    グループのみ。他グループは次回候補、6節)。
    user_profile/{user_id}ドキュメントおよびstripe_customer_index/{stripe_customer_id}
    逆引きドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._profiles = firestore_client.collection("user_profile")
        self._stripe_index = firestore_client.collection("stripe_customer_index")

    def _doc_ref(self, user_id: str):
        return self._profiles.document(user_id)

    def save(self, user_id: str, profile: UserProfile) -> None:
        # 連携成立時の新規作成のみを想定するためset()(merge無し)。
        # 既存フィールドの部分更新は個別グループのset_*メソッド(merge=True)で行う。
        self._doc_ref(user_id).set(_profile_to_dict(profile))

    def get(self, user_id: str) -> Optional[UserProfile]:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # LinkingCodeStoreProtocol.get()と同じ安全側方針(3節): 一時的な接続エラーも
            # 「未発見」(None)に合流させる。呼び出し元のno-op系デフォルト処理
            # (未知のuser_idと同じ扱い)にそのまま乗せられるため。
            return None
        if not snapshot.exists:
            return None
        return _profile_from_dict(snapshot.to_dict() or {})

    def exists(self, user_id: str) -> bool:
        try:
            return self._doc_ref(user_id).get().exists
        except Exception:
            return False

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

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        profile = self.get(user_id)
        if profile is None:
            return None
        return profile.stripe_customer_id
```

(`_profile_to_dict`/`_profile_from_dict`は`UserProfile`の全フィールド⇄dict変換の
ヘルパーで、`dataclasses.asdict`相当の変換に加え`datetime`フィールドをFirestoreの
タイムスタンプ型とそのまま対応させる想定。フィールド数が多いため実装時に`dataclasses.
asdict`+`None`値の扱い〈Firestoreは`None`を「フィールドが存在しfalsy」として
保存できるため、未設定と`None`明示の区別は不要〉を基本線とする。)

### 5.3. 検討事項

- **`save()`はmerge無し固定**: 連携成立時の新規ドキュメント作成のみが呼び出し元
  (`resolve_linking_code()`)であり、既存ドキュメントの上書きを想定していないため。
  後続グループのフィールド単位`set_*`はすべて`merge=True`(kura-pasha・line-reservation-ai
  のUserProfileStoreProtocol設計と同じ方針)。
- **Stripe逆引きインデックスの整合性**: `set_stripe_customer_id`は`WriteBatch`で
  2ドキュメントを同時書き込みするため、Firestoreのバッチ書き込みが原子的である前提で
  不整合(片方のみ反映)は発生しない。旧`stripe_customer_id`からの付け替え
  (同一`user_id`が2回目の`set_stripe_customer_id`を呼ぶケース)は本venture想定では
  発生しない契約(`InMemoryUserProfileStore.set_stripe_customer_id`が旧エントリを
  明示的に削除している理由と同じだが、実装を簡潔にするため本グループでは旧インデックス
  エントリの削除は次回候補とし、まず新規設定ケースのみを設計した)。
- **`get()`の例外方針**: 4節で設計した`LinkingCodeStoreProtocol.get()`と同じ、
  一時的な接続エラーも「未発見」(`None`)に倒す安全側方針を踏襲。

## 6. 残課題・次回候補(5節分)

- 旧`stripe_customer_id`からの付け替え時の旧インデックスエントリ削除(5.3節)。
- 残りのグループ(trial系3フィールド・payment_failure系4フィールド・current_plan_id・
  is_following+all_user_ids・owner_notified_at系4種・event_time系4種)の実Firestore
  接続アダプタ設計。いずれも基盤3メソッド(5.1節)と同じ`_doc_ref(user_id)`ヘルパーの
  上に`merge=True`の部分更新として素直に実装できる見込みだが、本フェーズでは対象外。
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(datetime⇄Firestore
  タイムスタンプ変換を含む)。
