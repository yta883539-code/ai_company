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
- 残りのグループ(trial系・payment_failure系4フィールド・current_plan_id・
  is_following+all_user_ids・owner_notified_at系4種・event_time系4種)の実Firestore
  接続アダプタ設計。いずれも基盤3メソッド(5.1節)と同じ`_doc_ref(user_id)`ヘルパーの
  上に`merge=True`の部分更新として素直に実装できる見込みだが、本フェーズでは対象外。
  (trial系は7節でフェーズ296として着手済み)
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(datetime⇄Firestore
  タイムスタンプ変換を含む)。

## 7. UserProfileStoreProtocol(trial系グループ)の実Firestore接続アダプタ設計

### 7.1. 背景・範囲

フェーズ295の次回候補(6節)を受け、残りのグループのうち trial 系(`set_trial_start_at`・
`set_trial_end_notified_at`・`set_upgraded_at`・`increment_trial_generation_count`・
`increment_trial_unit_count`・`get_trial_unit_count`、計6メソッド)の実Firestore接続
アダプタ設計に着手する。本グループを次に選んだ理由は、(1)`user_id_linking.py`1モジュール
に閉じており他venture連携のような外部依存がない、(2)2つの`increment_*`メソッドが、
kura-pashaフェーズ212で発見・是正された`UsageCounterStoreProtocol.check_and_increment_usage()`
と同種の「get→ローカル変数で+1→set」という read-modify-write 構成を`InMemoryUserProfileStore`
でも採っており(user_id_linking.py 585〜597行目)、Firestore接続時に同じ並行書き込み競合
(加算の取り落とし)を再現しうる箇所であるため、kura-pashaフェーズ212の教訓を本venture側で
横展開確認する意味もある、の2点による。

### 7.2. 設計

`set_trial_start_at`・`set_trial_end_notified_at`・`set_upgraded_at`は5節の基盤3メソッドと
同じ`_doc_ref(user_id)`ヘルパー上の単純な`merge=True`部分更新で素直に実装できる。

`increment_trial_generation_count`・`increment_trial_unit_count`は、kura-pashaフェーズ212が
採った「`@firestore.transactional`で読み取り+計算+書き込みを1トランザクションにまとめる」
方式ではなく、Firestoreの`Increment`センチネル(フィールド変換〈field transform〉として
サーバー側で加算を実行する仕組み)を使う設計とする。`UsageCounterStoreProtocol.
increment_or_reset`は「月替わりならリセットしてから+1」という条件分岐を伴うため、クライアント
側で現在値を見て分岐する必要がありトランザクションが必須だったが、本グループの2メソッドは
条件分岐のない単純な加算のみであり、`Increment`センチネルだけでクライアント側のread-modify-
write無しに原子性を確保できる(真に並行書き込みを競合させずに両方の加算が失われず反映される)。

```python
from google.cloud import firestore

class FirestoreUserProfileStore:
    # (5節の基盤3メソッド+Stripe顧客IDグループに以下を追加)

    def set_trial_start_at(self, user_id: str, at: datetime) -> None:
        self._doc_ref(user_id).set({"trial_start_at": at}, merge=True)

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        self._doc_ref(user_id).set({"trial_end_notified_at": notified_at}, merge=True)

    def set_upgraded_at(self, user_id: str, at: datetime) -> None:
        self._doc_ref(user_id).set({"upgraded_at": at}, merge=True)

    def increment_trial_generation_count(self, user_id: str) -> int:
        doc_ref = self._doc_ref(user_id)
        doc_ref.set(
            {"trial_generation_count": firestore.Increment(1)}, merge=True
        )
        return (doc_ref.get().to_dict() or {}).get("trial_generation_count", 0)

    def increment_trial_unit_count(self, user_id: str, unit_count: int) -> int:
        doc_ref = self._doc_ref(user_id)
        doc_ref.set(
            {"trial_unit_count": firestore.Increment(unit_count)}, merge=True
        )
        return (doc_ref.get().to_dict() or {}).get("trial_unit_count", 0)

    def get_trial_unit_count(self, user_id: str) -> int:
        profile = self.get(user_id)
        return profile.trial_unit_count if profile is not None else 0
```

### 7.3. 検討事項

- **`Increment`センチネルの原子性**: `firestore.Increment(n)`を`set(..., merge=True)`に
  渡すと、Firestoreはサーバー側で現在値に`n`を加算するフィールド変換として書き込みを実行する
  (クライアントは現在値を読まない)。複数のCloud Function実行が同一`user_id`に対して同時に
  `increment_trial_generation_count`を呼んでも、両方の加算がサーバー側で順に適用され、
  `UsageCounterStoreProtocol.check_and_increment_usage()`が実Firestore環境で起こしうると
  フェーズ211で指摘された「加算の取り落とし」は本グループでは発生しない。
- **書き込み直後の`get()`再読込の限界(契約上は許容)**: 両メソッドの戻り値契約
  (「インクリメント後のカウント値を返す」)を満たすため`set()`直後に`get()`で読み直す
  設計にしたが、他の並行呼び出しが自分の書き込みと読み直しの間に追加の加算を行った場合、
  戻り値は「自分の呼び出し分だけを反映した値」ではなく「それより新しい(他の加算も含む)値」
  になる可能性がある。ただし値の欠落(取り落とし)は発生せず、呼び出し元
  (`handle_media_generation_request`等)はいずれも戻り値を上限判定の参考値として使うのみで
  厳密な排他制御の主体ではないため許容する。厳密に「自分の加算直後の値」を保証したい場合は
  `@firestore.transactional`内で`get`→`Increment`相当の計算→`set`を行う必要があるが、それは
  本設計が避けたいクライアント側read-modify-write(トランザクションでラップしても毎呼び出しで
  往復コストが増える)を再導入するため、本フェーズでは採用しない。
- **`merge=True`の一貫性**: 5節の基盤3メソッド・Stripe顧客IDグループと同じ方針
  (kura-pasha・line-reservation-aiのUserProfileStoreProtocol設計とも一致)。

## 8. 残課題・次回候補(7節分)

- 残りのグループ(payment_failure系4フィールド・current_plan_id・is_following+
  all_user_ids・owner_notified_at系4種・event_time系4種)の実Firestore接続アダプタ設計。
  (payment_failure系4フィールドは9節でフェーズ297として着手済み)
- `increment_trial_generation_count`・`increment_trial_unit_count`と同種の
  read-modify-write構成(get→ローカル変数で+1→set)を`InMemoryUserProfileStore`以外の
  場所(course-set-pasha・line-reservation-ai・forklift-pashaの同種カウンタ系Protocol)が
  まだ持っていないか、横展開確認を行う。

## 9. UserProfileStoreProtocol(payment_failure系グループ)の実Firestore接続アダプタ設計

### 9.1. 背景・範囲

フェーズ296の次回候補(8節)を受け、残りのグループのうちpayment_failure系4フィールド
(`payment_failure_detected_at`・`payment_suspended_at`・`payment_failure_reminder_sent_at`・
`payment_failure_detection_notified_at`、計4フィールドの8メソッド
get/set)の実Firestore接続アダプタ設計に着手する。本グループを次に選んだ理由は、
(1)4フィールドとも`payment_failure.py`・`payment_failure_reminder_scheduler.py`という
dunning関連の薄いProtocol(`PaymentFailureStoreProtocol`等)のみから参照され関心が
まとまっている、(2)いずれも`Optional[datetime]`の単純な読み書きで、7節のtrial系と異なり
`increment_*`のような加算を伴わずread-modify-write競合のリスク自体が存在しない、という
2点により、残りのグループの中で最も設計が単純であるため。

### 9.2. 設計

4フィールドとも5節の基盤3メソッドと同じ`_doc_ref(user_id)`ヘルパー上の単純な
`merge=True`部分更新・単純読み取りで実装できる。`set_*`系はいずれも
`Optional[datetime]`を受け取り(`None`を渡すことでクリアする運用、
`InMemoryUserProfileStore`の同名メソッドと同じ契約)、`get_*`系は5節で設計した
`get()`(ドキュメント全体読み取り+`_profile_from_dict`変換)をそのまま呼び、
対象フィールドを取り出すだけで素直に実装できる(7節の`get_trial_unit_count`と
同じ構成)。

```python
class FirestoreUserProfileStore:
    # (5節・7節に以下を追加)

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.payment_failure_detected_at if profile is not None else None

    def set_payment_failure_detected_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_failure_detected_at": value}, merge=True
        )

    def get_payment_suspended_at(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.payment_suspended_at if profile is not None else None

    def set_payment_suspended_at(self, user_id: str, value: Optional[datetime]) -> None:
        self._doc_ref(user_id).set({"payment_suspended_at": value}, merge=True)

    def get_payment_failure_reminder_sent_at(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.payment_failure_reminder_sent_at if profile is not None else None

    def set_payment_failure_reminder_sent_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_failure_reminder_sent_at": value}, merge=True
        )

    def get_payment_failure_detection_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        profile = self.get(user_id)
        return (
            profile.payment_failure_detection_notified_at
            if profile is not None
            else None
        )

    def set_payment_failure_detection_notified_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_failure_detection_notified_at": value}, merge=True
        )
```

### 9.3. 検討事項

- **`None`書き込みによるクリア**: `merge=True`の`set()`に`None`を渡すと、Firestoreは
  当該フィールドを削除せず値`null`として保存する(フィールド自体は残る)。
  `get_*`側は`_profile_from_dict`がdict内の`null`を`None`として復元する前提のため、
  「未設定(ドキュメント作成時からフィールドが無い)」と「明示的に`None`に戻した」は
  いずれも`get()`時に`None`として扱われ区別されない。dunning系の呼び出し元
  (`clear_payment_failure_on_success()`等)はいずれも「`None`=未発生/解消済み」の
  意味でのみ使っており、両者を区別する必要がないため、5節の基本方針(フィールドの
  存在/非存在ではなく値そのもので判定する)と一致し問題ない。
- **read-modify-write競合が存在しないことの確認**: 7節のtrial系2メソッド
  (`increment_trial_generation_count`等)と異なり、本グループの4フィールドは
  いずれも「現在値を見てから計算する」操作を持たず、常に呼び出し元が確定した値を
  そのまま`set`するだけのため、Firestore接続時にkura-pashaフェーズ212・本venture
  フェーズ296で発見されたような並行書き込み競合のリスク自体が存在しない
  (横展開確認の対象外であることをここに明記する)。
- **`merge=True`の一貫性**: 5節・7節と同じ方針を踏襲。

## 10. 残課題・次回候補(9節分)

- 残りのグループ(current_plan_id・is_following+all_user_ids・owner_notified_at系4種・
  event_time系4種)の実Firestore接続アダプタ設計。このうちowner_notified_at系4種
  (`blocked_but_billing_owner_notified_at`・`payment_suspension_owner_notified_at`等)は
  本節のpayment_failure系と同じ「単純なOptional[datetime]の読み書きのみ」の構成のため、
  次に着手しやすい候補と見込む。
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(5節から持ち越し、
  datetime⇄Firestoreタイムスタンプ変換を含む)は依然未着手。
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(5節と共通、未着手)。

## 11. UserProfileStoreProtocol(owner_notified_at系グループ)の実Firestore接続アダプタ設計

### 11.1. 背景・範囲

フェーズ297の次回候補(2)を受け、残りのグループのうちowner_notified_at系2フィールド
(`blocked_but_billing_owner_notified_at`・`payment_suspension_owner_notified_at`、
計2フィールドの4メソッドget/set)の実Firestore接続アダプタ設計に着手する。本グループを
次に選んだ理由は、(1)`blocked-but-billing-owner-notification-design.md`・
`payment-suspension-owner-notification-design.md`というオーナー通知関連の薄い設計書
のみから参照され関心がまとまっている、(2)いずれも9節のpayment_failure系と同じ
`Optional[datetime]`の単純な読み書きで、`increment_*`のような加算を伴わず
read-modify-write競合のリスク自体が存在しない、という2点により、残りのグループの中で
9節に続いて設計が単純であるため。

### 11.2. 設計

2フィールドとも5節の基盤3メソッドと同じ`_doc_ref(user_id)`ヘルパー上の単純な
`merge=True`部分更新・単純読み取りで実装でき、9節のpayment_failure系4メソッドと
完全に同型である。

```python
class FirestoreUserProfileStore:
    # (5節・7節・9節に以下を追加)

    def get_blocked_but_billing_owner_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        profile = self.get(user_id)
        return (
            profile.blocked_but_billing_owner_notified_at
            if profile is not None
            else None
        )

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"blocked_but_billing_owner_notified_at": notified_at}, merge=True
        )

    def get_payment_suspension_owner_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        profile = self.get(user_id)
        return (
            profile.payment_suspension_owner_notified_at
            if profile is not None
            else None
        )

    def set_payment_suspension_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        self._doc_ref(user_id).set(
            {"payment_suspension_owner_notified_at": notified_at}, merge=True
        )
```

`InMemoryUserProfileStore`の同名メソッド(`user_id_linking.py` 674〜694行目付近)は
いずれも「プロファイルが存在しなければ何もしない」(`set_*`側)・「存在しなければ`None`を
返す」(`get_*`側)という9節までと同じ契約であり、本設計もそれに対応する。

### 11.3. 検討事項

- **`None`書き込みによるクリア**: 9節と同じく、`merge=True`の`set()`に`None`を渡しても
  フィールドは削除されず値`null`として保存される。呼び出し元
  (`blocked_but_billing_owner_notification.clear_blocked_but_billing_owner_notified_at()`
  等)は「`None`=未通知/再送可能」の意味でのみ使っており、「未設定」と「明示的に`None`に
  戻した」を区別する必要がないため、9節と同じ結論で問題ない。
- **read-modify-write競合が存在しないことの確認**: 本グループの2フィールドは
  いずれも「現在値を見てから計算する」操作を持たず、呼び出し元が確定した値をそのまま
  `set`するだけのため、9節と同じ理由でFirestore接続時の並行書き込み競合のリスク自体が
  存在しない(横展開確認の対象外であることをここに明記する)。
- **`merge=True`の一貫性**: 5節・7節・9節と同じ方針を踏襲。

## 12. 残課題・次回候補(11節分)

- 残りのグループ(current_plan_id・is_following+all_user_ids・event_time系4種)の
  実Firestore接続アダプタ設計。このうちcurrent_plan_idは9節・11節と同じ
  「単純なOptional[str]の読み書きのみ」の構成(ただし型が`datetime`ではなく`str`)で
  あるため、次に着手しやすい候補と見込む。is_following+all_user_idsは真偽値の単純な
  読み書き(`set_is_following`)に加え、`all_user_ids()`(全ユーザーID一覧取得)という
  5節のLinkingCodeStoreProtocol `items()`相当の全件走査系メソッドを含むため、
  走査方法(コレクション全体の`stream()`か専用インデックスか)の検討が必要になる点で
  current_plan_idより設計がやや複雑になる見込み。
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(5節と共通、未着手)。

## 13. UserProfileStoreProtocol(current_plan_id)の実Firestore接続アダプタ設計

### 13.1. 背景・範囲

フェーズ298の次回候補(2)を受け、残りのグループのうち`current_plan_id`
(1フィールド・2メソッドget/set)の実Firestore接続アダプタ設計に着手する。本フィールドを
次に選んだ理由は、9節・11節と同じ「現在値を見てから計算する操作を持たない単純な読み書き
のみ」の構成であり、型が`Optional[datetime]`ではなく`Optional[str]`である点を除けば
設計が完全に同型であるため、残りのグループ(is_following+all_user_ids・event_time系4種)
より着手しやすい候補と見込んだため。

### 13.2. 設計

`user_id_linking.py` 651〜659行目の`InMemoryUserProfileStore.get_current_plan_id`/
`set_current_plan_id`は、9節・11節までと同じ「プロファイルが存在しなければ`set_*`は
何もしない・`get_*`は`None`を返す」契約であり、本設計もそれに対応する。

```python
class FirestoreUserProfileStore:
    # (5節・7節・9節・11節に以下を追加)

    def get_current_plan_id(self, user_id: str) -> Optional[str]:
        profile = self.get(user_id)
        return profile.current_plan_id if profile is not None else None

    def set_current_plan_id(self, user_id: str, plan_id: Optional[str]) -> None:
        self._doc_ref(user_id).set({"current_plan_id": plan_id}, merge=True)
```

### 13.3. 検討事項

- **`None`書き込みによるクリア**: 9節・11節と同じく、`merge=True`の`set()`に`None`を
  渡してもフィールドは削除されず値`null`として保存される。呼び出し元
  (`subscription_plan_sync.clear_current_plan_id_on_cancellation()`等)は
  「`None`=未契約」の意味でのみ使っており、「未設定」と「明示的に`None`に戻した」を
  区別する必要がないため、9節・11節と同じ結論で問題ない。
- **read-modify-write競合が存在しないことの確認**: `current_plan_id`は
  `subscription_plan_sync.sync_plan_from_subscription_event()`が解決したプランIDを
  そのまま`set`するだけで、現在値を見てから計算する操作を持たないため、9節・11節と同じ
  理由でFirestore接続時の並行書き込み競合のリスク自体が存在しない(横展開確認の対象外
  であることをここに明記する)。なお`stripe_dispatch.py`側で`get_current_plan_id`を
  読んでから無駄な`set`を避ける最適化(フェーズ283付近)があるが、これは呼び出し回数を
  減らす目的のみで正当性には影響しない(読んだ値と異なる値のみ書き込むため、読み取り後に
  他プロセスが値を変えても「最後に書いた値が最終的な値になる」というlast-write-wins
  の挙動自体は変わらない)。
- **型の違い**: 9節・11節は`Optional[datetime]`だったが、本フィールドは
  `Optional[str]`。Firestoreのドキュメントフィールドとしてはどちらも素直にシリアライズ
  可能(`datetime`はFirestore Timestamp型、`str`はそのまま文字列)で、設計上の扱いに
  差はない。

## 14. 残課題・次回候補(13節分)

- 残りのグループ(is_following+all_user_ids・event_time系4種)の実Firestore接続アダプタ
  設計。is_following+all_user_idsは真偽値の単純な読み書き(`set_is_following`)に加え、
  `all_user_ids()`(全ユーザーID一覧取得)という5節のLinkingCodeStoreProtocol
  `items()`相当の全件走査系メソッドを含むため、走査方法(コレクション全体の`stream()`か
  専用インデックスか)の検討が必要になる点で、これまでのグループより設計がやや複雑になる
  見込み。
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(5節と共通、未着手)。

## 15. UserProfileStoreProtocol(is_following+all_user_ids)の実Firestore接続アダプタ設計

### 15.1. 背景・範囲

フェーズ299の次回候補(2)を受け、残りのグループのうち`is_following`+`all_user_ids`
(2フィールド・3メソッド`get_is_following`/`set_is_following`/`all_user_ids`)の実
Firestore接続アダプタ設計に着手する。`get_is_following`/`set_is_following`自体は
9節・11節・13節と同型の単純な読み書きだが、`all_user_ids()`が本`UserProfileStoreProtocol`
グループでは初めての`user_profile`コレクション全体の列挙系メソッドであるため、2節の
`LinkingCodeStoreProtocol.items()`(`pending_links`コレクション全体の`stream()`)と
同じ論点を踏襲しつつ設計する。

### 15.2. 設計

`user_id_linking.py` 661〜672行目の`InMemoryUserProfileStore.get_is_following`/
`set_is_following`/`all_user_ids`は、`get_is_following`が未知の`user_id`に対して
`True`(存在しないprofileを「フォロー中」扱いする安全側デフォルト、342〜344行目の
コメント参照)を返す点を除き、9節・11節・13節までの単純な読み書き契約と同型。
`all_user_ids()`は`self._profiles.keys()`(保持している全プロファイルの`user_id`)を
返すのみで、本実装では`user_profile`コレクション全体の`stream()`で対応する。

```python
class FirestoreUserProfileStore:
    # (5節・7節・9節・11節・13節に以下を追加)

    def get_is_following(self, user_id: str) -> bool:
        profile = self.get(user_id)
        return profile.is_following if profile is not None else True

    def set_is_following(self, user_id: str, value: bool) -> None:
        self._doc_ref(user_id).set({"is_following": value}, merge=True)

    def all_user_ids(self) -> Iterable[str]:
        for snapshot in self._profiles.stream():
            yield snapshot.id
```

### 15.3. 検討事項

- **`get_is_following`の安全側デフォルトは`get()`経由でそのまま踏襲できる**: 5節で
  設計した`get()`は未発見・接続エラーいずれも`None`に倒すため、`get_is_following`は
  「`profile is None`→`True`」の1分岐を`get()`の戻り値にそのまま乗せるだけで、
  `InMemoryUserProfileStore`と同じ安全側デフォルト(存在しないprofileを「フォロー中」
  扱いする)を実現できる。`blocked_but_billing_candidates.py`の候補抽出が対象とするのは
  常に連携済み(=profileが存在する)`user_id`のみ(342〜344行目のコメントの通り)のため、
  このデフォルト値が実際に使われるケース自体は想定されていない。
- **`set_is_following`はno-op方針を適用しない**: 9節・11節・13節までの`set_*`は
  Firestoreの`merge=True`の`set()`が「ドキュメントが存在しなければ新規作成する」挙動を
  持つため、厳密には`InMemoryUserProfileStore`の「存在しないprofileへの`set_*`は
  何もしない」no-op契約と完全には一致しない(Firestore版は新規ドキュメントを作ってしまう)。
  この非対称自体は5節で確立した`merge=True`部分更新方針に最初から内在する差分であり、
  9節・11節・13節でも同様に踏襲してきたため本節で新たに導入される問題ではない。
  `set_is_following`の呼び出し元(LINE Platform側のフォロー/アンフォローWebhook想定)は
  既に連携済みのユーザーのみを対象とするため、実害は想定しない。
- **`all_user_ids()`の走査コスト**: `blocked_but_billing_candidates.py`67行目・
  `deletion_candidate.py`173行目のいずれも、日次バッチ想定の定期実行のたびに全ユーザーを
  線形走査する用途であり、3節で`LinkingCodeStoreProtocol.items()`について検討した
  論点と同じ構造を持つ。本venture想定ユーザー規模(unit-economics-estimate.md・
  subscription-billing-cost-estimate.md想定の小規模事業者向けサービスという前提)では、
  ユーザー総数がFirestoreの`stream()`無料枠の範囲に収まる見込みのため、`where`条件による
  絞り込みや専用インデックスは過剰設計として見送り、コレクション全体の`stream()`を
  採用する(3節と同じ結論)。将来的にユーザー数が増え読み取りコストが問題になった場合、
  `blocked_but_billing_candidates.py`側の候補抽出条件(未フォロー+支払い遅延等)に
  対応する複合インデックス+範囲クエリへの切り替えを再検討する。
- **列挙順序への依存がないことの確認**: `all_user_ids()`の戻り値は`Iterable[str]`
  契約であり、呼び出し元(`blocked_but_billing_candidates.py`67行目・
  `deletion_candidate.py`173行目)はいずれも`for user_id in store.all_user_ids()`で
  順不同に処理するのみで、`InMemoryUserProfileStore`の辞書挿入順と`stream()`の
  返却順(ドキュメントID順やシャーディングに依存し保証されない)が異なっていても
  正当性に影響しない。

## 16. 残課題・次回候補(15節分)

- 残りのグループ(event_time系4種)の実Firestore接続アダプタ設計。
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(5節と共通、未着手)。
- 承認後の結合実装時に、`blocked_but_billing_candidates.py`・`deletion_candidate.py`の
  日次バッチ実行環境(Cloud Scheduler、オーナー承認待ち)が整った段階で、`all_user_ids()`
  の実際の読み取り件数・レイテンシを計測し、15.3節の「過剰設計として見送り」判断を
  再検証する。

## 17. UserProfileStoreProtocol(event_time系4種)の実Firestore接続アダプタ設計

### 17.1. 背景・範囲

フェーズ300の次回候補(2)を受け、`UserProfileStoreProtocol`の残りグループである
`event_time`系4種(`subscription_state_event_time`・`payment_failure_state_event_time`・
`checkout_session_completed_event_time`・`subscription_updated_event_time`、各get/set
計8メソッド)の実Firestore接続アダプタ設計に着手する。これで5節・7節・9節・11節・
13節・15節・本節により`UserProfileStoreProtocol`の全グループの設計が完了する
(`_profile_to_dict`/`_profile_from_dict`ヘルパー自体の実装を除く)。

4フィールドはいずれも`stripe_dispatch.py`・`stripe_webhook.py`側の配信順序ガード
(Stripe Webhookイベントが順不同に届いた場合、より新しい`event.created`時刻を記録済みの
イベントより古いイベントの適用をスキップする)の基準線としてのみ使われ、`user_id_linking.py`
716〜756行目の`InMemoryUserProfileStore`実装を見る限り、`get_*`は「プロファイルが
存在しなければ`None`」、`set_*`は「プロファイルが存在しなければ何もしない」という、
9節・11節・13節までと完全に同型の単純な読み書き契約である。

### 17.2. 設計

```python
class FirestoreUserProfileStore:
    # (5節・7節・9節・11節・13節・15節に以下を追加)

    def get_subscription_state_event_time(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.subscription_state_event_time if profile is not None else None

    def set_subscription_state_event_time(self, user_id: str, event_time: datetime) -> None:
        self._doc_ref(user_id).set(
            {"subscription_state_event_time": event_time}, merge=True
        )

    def get_payment_failure_state_event_time(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.payment_failure_state_event_time if profile is not None else None

    def set_payment_failure_state_event_time(self, user_id: str, event_time: datetime) -> None:
        self._doc_ref(user_id).set(
            {"payment_failure_state_event_time": event_time}, merge=True
        )

    def get_checkout_session_completed_event_time(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.checkout_session_completed_event_time if profile is not None else None

    def set_checkout_session_completed_event_time(
        self, user_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(user_id).set(
            {"checkout_session_completed_event_time": event_time}, merge=True
        )

    def get_subscription_updated_event_time(self, user_id: str) -> Optional[datetime]:
        profile = self.get(user_id)
        return profile.subscription_updated_event_time if profile is not None else None

    def set_subscription_updated_event_time(self, user_id: str, event_time: datetime) -> None:
        self._doc_ref(user_id).set(
            {"subscription_updated_event_time": event_time}, merge=True
        )
```

### 17.3. 検討事項

- **`set_*`のno-op契約との非対称は15節までと同じ既知の差分**: `merge=True`の`set()`は
  存在しないドキュメントを新規作成してしまうため、`InMemoryUserProfileStore`の
  「プロファイル不在時は何もしない」契約とは厳密には一致しない。9節・11節・13節・15節で
  確立した既知の差分であり、呼び出し元(Stripe Webhookハンドラ群)は常に`user_id`解決
  (`stripe_customer_id`からの逆引き等)済みの既存プロファイルのみを対象とするため実害
  なしと判断する(横展開の結論を踏襲)。
- **ガード自体の安全側は「無条件適用」方向であることの再確認**: 13節で検討した
  `current_plan_id`とは異なり、本4フィールドは「`get_*`が接続エラーで`None`を返す→
  ガードが『記録済み時刻未設定』と同じ扱いになり、順序チェックをスキップしてイベントを
  無条件適用する」という挙動を持つ。これは9節で確立した「処理を止めない方向の安全側
  フォールバック」の方針そのものであり、各設計ドキュメント
  (subscription-event-out-of-order-guard-design.md等)のdocstringが元々想定する
  挙動の範囲内に収まることを確認した。
- **4フィールドが同型であることの確認**: いずれも「他のイベントとの比較・計算を伴わない
  単純な値の読み書き」であり、read-modify-write競合のリスクは存在しない(13節と同じ
  理由で横展開確認の対象外)。型はすべて`datetime`(Firestore Timestamp型としてそのまま
  シリアライズ可能)で、`set_*`側に`Optional`型がない(常に非`None`の`event_time`を
  渡す契約)点が9節・11節・13節の`Optional[datetime]`/`Optional[str]`とは異なるが、
  書き込み処理自体に違いはない。

## 18. 残課題・次回候補(17節分)

- `UserProfileStoreProtocol`の全7グループ(基盤3メソッド+Stripe顧客IDグループ・trial系・
  payment_failure系・owner_notified_at系・current_plan_id・is_following+all_user_ids・
  event_time系4種)の実Firestore接続アダプタ設計が本節で完了した。
- `_profile_to_dict`/`_profile_from_dict`ヘルパーの具体的な実装(5節以来、未着手のまま
  残っている)。
- 本designでは未対象の他Protocol(`SubscriptionDeletionCandidateStoreProtocol`等、
  user_id_linking.py以外のモジュールで定義されるもの)の実Firestore接続アダプタ設計。
- 承認が得られ次第、実GCPプロジェクト・Firestoreインスタンスでの結合テスト(現時点では
  机上設計とInMemory実装での回帰確認にとどまる)。
