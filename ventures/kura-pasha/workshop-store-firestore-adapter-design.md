# WorkshopStoreProtocol(基盤グループ)の実Firestore接続アダプタ設計

## 1. 背景

本venture(kura-pasha)には4つのProtocolが存在し、フェーズ211(`UsageCounterStoreProtocol`)・
フェーズ213(`LinkingCodeStoreProtocol`のpending_links向け)・フェーズ214(同pending_workshop_invites
向け)・`firestore-provider-adapter-design.md`(`UserProfileStoreProtocol`)により、残る
`WorkshopStoreProtocol`(`craftsman_workshop/{workshop_id}`ドキュメント対応、30件超のget/set
メソッドを持つ本venture最大のProtocol)を除く3つの実Firestore接続アダプタ設計が完了している。
本ドキュメントはその残課題に着手するもので、他venture(aircon-pasha・course-set-pasha)の
`UserProfileStoreProtocol`設計と同じ「一度に全メソッドを設計すると検討事項が発散するため、
関連性の高い最小グループから着手する」方針を踏襲する。

本フェーズは以下の**基盤グループ**(workshop新規作成時に書き込まれるフィールド+それに続く
単純な付随フィールド、計9メソッド)に限定する。

- `set_members`/`get_contractor_user_id`/`set_contractor_user_id`/`get_member_user_ids`/
  `add_member_user_id`/`get_member_display_name`: workshop作成(`workshop_linking.
  resolve_linking_code()`)・契約者引き継ぎ・招待コードでのメンバー追加のいずれからも
  触れられる、メンバー構成に関する一群。
- `get_plan_id`/`set_plan`: プラン(`light`/`standard`等)。
- `get_workshop_name`/`set_workshop_name`: 屋号・工房名(workshop-name-owner-notification-
  display-design.md)。
- `get_first_generation_notice_sent`/`set_first_generation_notice_sent`: 初回生成確認案内の
  付記済みフラグ(first-generation-self-check-notification-design.md)。
- `all_workshop_ids`: blocked-but-billing-detection-design.md 3節の候補走査対象列挙
  (aircon-pashaの`all_user_ids`相当)。

残りのグループ(`pending_reduction_effective_at`+`specified_retention_member_name`+
`apply_member_reduction`のメンバー削減系、`pending_contractor_transfer`系、trial系2
フィールド、`stripe_customer_id`順引き・逆引き、`subscription_status`+各種`event_time`系、
`payment_failure`系、`trial_end_notified_at`、`owner_notified_at`系2種)は、それぞれが
他グループと独立した関心事に閉じているため、次回候補として個別に残す(4節)。

### 1.1. `set_members`のProtocol宣言漏れの是正(本フェーズの前提作業)

設計着手にあたり`usage_counter_workshop.py`の`WorkshopStoreProtocol`定義を確認したところ、
`workshop_linking.py`66〜80行目の`resolve_linking_code()`は引数`workshop_store`を
`WorkshopStoreProtocol`型として宣言しているにもかかわらず、同関数が実際に呼び出す
`workshop_store.set_members(...)`(233行目、新規workshop作成時に1回だけ呼ばれる)は
`WorkshopStoreProtocol`に宣言されておらず、`InMemoryWorkshopStore`のみが独自に実装を
持つメソッドだったことが判明した。Pythonの`Protocol`は`@runtime_checkable`を付与していない
限り実行時の型チェックを行わないため、`InMemoryWorkshopStore`を使う限り実害は生じないが、
本フェーズでまさに検討している実Firestore接続アダプタ(`FirestoreWorkshopStore`)を
`WorkshopStoreProtocol`の宣言のみを見て実装した場合、`set_members`を欠いたまま
「Protocol準拠のつもり」になり、`resolve_linking_code()`経由のworkshop作成時に
`AttributeError`で失敗する設計ミスを誘発しうる状態だった。

本フェーズはこの設計ドキュメント着手に先立ち、`WorkshopStoreProtocol`へ`set_members`を
正式に宣言として追加し是正した(usage_counter_workshop.py)。シグネチャは
`InMemoryWorkshopStore.set_members`(655〜670行目)と完全に一致させ、動作変更は伴わない
(`InMemoryWorkshopStore`は元々このシグネチャで実装済みのため、Protocolへの追記のみで
サブタイピングは引き続き成立する)。回帰確認として`python3 -m unittest discover -s
prototype -p "test_*.py"`(171件、変更なし)・`python3 schema/validate_test_cases.py`
(32件、変更なし)を再実行し、いずれもパスすることを確認した。

## 2. 設計方針

`craftsman_workshop/{workshop_id}`は`workshop_id`をドキュメントIDとする1ドキュメント1
エントリの構造(craftsman-account-linking-design.md 2節・114行目)。基盤グループの各
フィールドはいずれも同一ドキュメント内の独立したキーであり、読み取り系は単純な
フィールド参照、書き込み系は`set(merge=True)`による部分更新で素直に実装できる
(UserProfileStoreProtocol設計・フェーズ209以降の一貫方針を踏襲)。

`all_workshop_ids()`のみ単一ドキュメントに閉じず、コレクション全体の走査
(`craftsman_workshop.stream()`で全ドキュメントIDを列挙)が必要になる。
blocked-but-billing-detection-design.md 3節の定期バッチ用途であり高頻度アクセスではない
ため、インデックス専用コレクションは設けずコレクションスキャンで素直に実装する
(`InMemoryWorkshopStore.all_workshop_ids()`が`dict.keys()`を返すのと対応)。

```python
class FirestoreWorkshopStore:
    """WorkshopStoreProtocolの実Firestore接続実装(基盤グループのみ。残りのグループは
    次回候補、4節)。craftsman_workshop/{workshop_id}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._workshops = firestore_client.collection("craftsman_workshop")

    def _doc_ref(self, workshop_id: str):
        return self._workshops.document(workshop_id)

    def set_members(
        self,
        workshop_id: str,
        contractor_user_id: str,
        member_user_ids: list[str],
        display_names: Optional[dict[str, str]] = None,
    ) -> None:
        # resolve_linking_code()からの新規作成時の1回のみの呼び出しを想定するため、
        # 既存ドキュメントの有無を問わずset(merge=True)で素直に書き込む(新規作成でも
        # 部分更新でも同じコードパスで扱える)。
        all_ids = [contractor_user_id] + [
            uid for uid in member_user_ids if uid != contractor_user_id
        ]
        self._doc_ref(workshop_id).set(
            {
                "contractor_user_id": contractor_user_id,
                "member_user_ids": all_ids,
                "member_display_names": dict(display_names or {}),
            },
            merge=True,
        )

    def get_contractor_user_id(self, workshop_id: str) -> str:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {})["contractor_user_id"]

    def set_contractor_user_id(self, workshop_id: str, user_id: str) -> None:
        self._doc_ref(workshop_id).set({"contractor_user_id": user_id}, merge=True)

    def get_member_user_ids(self, workshop_id: str) -> list[str]:
        snapshot = self._doc_ref(workshop_id).get()
        return list((snapshot.to_dict() or {}).get("member_user_ids", []))

    def add_member_user_id(self, workshop_id: str, user_id: str) -> None:
        # Firestoreのarray_union()はサーバー側で重複排除される原子的操作のため、
        # InMemory実装のin演算子チェック(694〜696行目)と同じ冪等性を、読み取りなしの
        # 1回の書き込みで実現できる。
        self._doc_ref(workshop_id).update(
            {"member_user_ids": firestore.ArrayUnion([user_id])}
        )

    def get_member_display_name(self, workshop_id: str, user_id: str) -> Optional[str]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("member_display_names", {}).get(user_id)

    def get_plan_id(self, workshop_id: str) -> str:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {})["plan_id"]

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        self._doc_ref(workshop_id).set({"plan_id": plan_id}, merge=True)

    def get_workshop_name(self, workshop_id: str) -> Optional[str]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("workshop_name")

    def set_workshop_name(self, workshop_id: str, workshop_name: str) -> None:
        self._doc_ref(workshop_id).set({"workshop_name": workshop_name}, merge=True)

    def get_first_generation_notice_sent(self, workshop_id: str) -> bool:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("first_generation_notice_sent", False)

    def set_first_generation_notice_sent(self, workshop_id: str) -> None:
        self._doc_ref(workshop_id).set(
            {"first_generation_notice_sent": True}, merge=True
        )

    def all_workshop_ids(self) -> Iterable[str]:
        return (doc.id for doc in self._workshops.stream())
```

## 3. 検討事項

- **`add_member_user_id`の`ArrayUnion`採用**: 基盤グループの他メソッドと異なり、本メソッドは
  読み取り→ローカルでのin判定→書き込みという2段階にせず、Firestoreの`ArrayUnion`
  センチネルで原子的に実装できる(フェーズ212で発見・解消した`UsageCounterStoreProtocol`の
  read-modify-write競合と同種のリスクが、本メソッドでは`ArrayUnion`の存在により最初から
  回避できる)。複数職人が同時に招待コードを解決して同一workshopへ加入しようとする競合
  ケース(craftsman-account-linking-design.md 11節)でも、書き込み順序によらず両者が
  正しく反映される。
- **`get_contractor_user_id`・`get_plan_id`の例外方針**: InMemory実装(672〜673行目・
  652〜653行目)はいずれも辞書への直接アクセス(`dict[key]`)で未作成workshop_idに対し
  `KeyError`を送出する契約になっている。これは`UserProfileStoreProtocol.get()`等の
  「未発見はNoneに倒す安全側方針」とは異なり、`get_contractor_user_id`・`get_plan_id`が
  いずれも「workshop作成(`set_members`→`set_plan`)が完了済みであることを呼び出し元が
  前提にできる」設計(workshop_linking.py 233〜234行目で両方とも作成直後に必ず設定される)
  であるため、本グループの実装もInMemoryと同じ契約を維持し、未作成ドキュメントに対しては
  例外的ケースとして扱う(`snapshot.to_dict() or {}`に対する`["key"]`アクセスが自然に
  `KeyError`を送出する)。一時的な接続エラー(`get()`自体の例外)を安全側Noneに倒すかどうかは
  本グループでは未検討のまま残し、次回候補(4節)とする。
- **`member_display_names`のフィールド命名**: InMemory実装は`_display_names_by_workshop`を
  `member_user_ids`とは別の辞書として保持しているが(630行目)、Firestoreでは同一
  ドキュメント内のネストしたmapフィールド(`member_display_names`)として格納する設計とした。
  読み取り回数を増やさずに済む(`get_member_user_ids`・`get_member_display_name`のいずれも
  1回の`get()`で完結する)ため。

## 4. 残課題・次回候補

1. 優先順位1・2候補(ライディングショップ池上・エクウスワールド)へのヒアリング実施が
   オーナーから承認された場合はその着手を最優先。
2. `WorkshopStoreProtocol`の残りのグループ(メンバー削減系・契約者引き継ぎ系・trial系・
   stripe_customer_id順引き逆引き系・subscription_status+event_time系・payment_failure系・
   trial_end_notified_at・owner_notified_at系2種)の実Firestore接続アダプタ設計。
   `UserProfileStoreProtocol`で先行設計済みの同名・同型グループ(stripe_customer_idの
   WriteBatch逆引き等)との横展開確認も合わせて行う。
3. 一時的な接続エラー時の安全側フォールバック方針(3節で未検討のまま残した点)の、
   本venture全体(UserProfileStoreProtocol・LinkingCodeStoreProtocol等)を通じた統一的な
   整理。
4. 他venture・アイデア領域の前進。

## 5. WorkshopStoreProtocol(メンバー削減系グループ)の実Firestore接続アダプタ設計

本節は4節2点目で次回候補として残した複数グループのうち、**メンバー削減系**
(`get_pending_reduction_effective_at`/`set_pending_reduction_effective_at`/
`get_specified_retention_member_name`/`set_specified_retention_member_name`/
`apply_member_reduction`の5メソッド)に着手する。downgrade-excess-member-handling-design.md
「3. 確定する設計」の都度チェック処理(`check_and_apply_pending_member_reduction()`、
usage_counter_workshop.py 988〜1040行目)が利用する一群で、複数職人プランから単数プランへの
ダウングレード確定時に、猶予期間(`pending_member_reduction_effective_at`)到達後1回だけ
`member_user_ids`を絞り込む(`apply_member_reduction`)。

`InMemoryWorkshopStore`では3フィールドをそれぞれ別の辞書
(`_pending_reduction_effective_at_by_workshop`・`_specified_retention_name_by_workshop`、
`member_user_ids`自体は基盤グループで既存)で保持しているが(651〜652行目)、基盤グループと
同じ`craftsman_workshop/{workshop_id}`ドキュメントの独立フィールドとして素直に設計できる。

```python
    def set_pending_reduction_effective_at(
        self, workshop_id: str, effective_at: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"pending_member_reduction_effective_at": effective_at}, merge=True
        )

    def get_pending_reduction_effective_at(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("pending_member_reduction_effective_at")

    def set_specified_retention_member_name(self, workshop_id: str, name: str) -> None:
        self._doc_ref(workshop_id).set(
            {"specified_retention_member_name": name}, merge=True
        )

    def get_specified_retention_member_name(self, workshop_id: str) -> Optional[str]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("specified_retention_member_name")

    def apply_member_reduction(self, workshop_id: str, retained_user_ids: list[str]) -> None:
        # InMemory実装(733〜735行目)はmember_user_idsの置き換えと
        # pending_reduction_effective_atのpop(キー削除)を2行に分けて行うが、
        # 両者は同一ドキュメントの2フィールドのため、Firestore側は単一のset(merge=True)
        # で原子的に反映できる(課題承継=InMemoryの2行が1回のドキュメント更新として
        # 観測される点は、呼び出し元から見た可視結果に差が出ない)。
        self._doc_ref(workshop_id).set(
            {
                "member_user_ids": list(retained_user_ids),
                "pending_member_reduction_effective_at": None,
            },
            merge=True,
        )
```

### 5.1. 検討事項

- **`pending_member_reduction_effective_at`のクリア方式**: `apply_member_reduction`内で
  `None`を書き込む方式は、3節で先行設計済みの他フィールドのクリア方針とは異なり専用の
  `clear_*`メソッドを持たない(`apply_member_reduction`という既存の書き込みメソッドに
  「ついでにクリアする」役割が元々組み込まれている設計のため)。course-set-pasha
  firestore-provider-adapter-design.md 9節で確立した「InMemoryのpop()とFirestoreの
  明示的None書き込みは、get側が常に`.get(key)`(存在しないキーも`None`扱い)である限り
  観測可能な挙動が一致する」という根拠がここでも同様に成立することを確認した。
- **`specified_retention_member_name`が`apply_member_reduction`でクリアされない点**:
  `InMemoryWorkshopStore.apply_member_reduction`(733〜735行目)は
  `_specified_retention_name_by_workshop`を一切触らず、`pending_reduction_effective_at`
  のみをpopする。これは意図的な設計(縮小実行時に指定名の履歴を保持する)か、単に
  見落としかが実装コード・既存設計ドキュメント(downgrade-excess-member-handling-design.md・
  member-retention-notice-design.md)のいずれからも断定できなかった。次回
  `set_pending_reduction_effective_at`が呼ばれる(=新たなダウングレードが確定する)際に
  `set_specified_retention_member_name`が呼ばれなければ、前回サイクルの指定名が
  再利用されてしまう余地がInMemory実装にも既に存在する。本フェーズはFirestore接続
  アダプタの設計がスコープであり、ビジネスロジックの仕様変更(InMemory実装の挙動修正)は
  対象外のため、Firestore側もInMemoryと同一の挙動(クリアしない)を忠実に再現するに留め、
  この観察事項を6節の次回候補として記録するのみとする。
- **`member_user_ids`の書き込み競合**: `apply_member_reduction`は`add_member_user_id`
  (基盤グループ、`ArrayUnion`採用)と異なり`member_user_ids`全体を上書きする
  `set(merge=True)`であるため、両者が同時に実行された場合(縮小確定処理と招待コード
  解決によるメンバー追加が競合するケース)は後勝ちで片方の更新が失われる可能性がある。
  ただし`check_and_apply_pending_member_reduction()`は生成リクエスト受信時の都度チェック
  (usage_counter_workshop.py 996行目コメント)であり、縮小確定時点で`member_user_ids`を
  `[contractor_user_id]`の1名に絞り込む設計上、この競合はInMemory実装でも同様に存在する
  既存のリスクである。本フェーズでは新規に導入される問題ではないため、WriteBatch化等の
  対策は6節の次回候補として記録するに留める。

## 6. 残課題・次回候補(5節分)

1. `specified_retention_member_name`が縮小実行時にクリアされない点(5.1節2点目)の、
   本venture全体を通じた意図確認・必要であれば仕様としての明文化(downgrade-excess-
   member-handling-design.mdへの追記)。
2. `member_user_ids`の上書き更新(`apply_member_reduction`)とArrayUnion追記
   (`add_member_user_id`)が競合する余地(5.1節3点目)への対策検討。
3. `WorkshopStoreProtocol`の残りのグループ(契約者引き継ぎ系・trial系2フィールド・
   stripe_customer_id順引き逆引き系・subscription_status+各種event_time系・
   payment_failure系・trial_end_notified_at・owner_notified_at系2種)の実Firestore接続
   アダプタ設計。
4. 一時的な接続エラー時の安全側フォールバック方針(3節で未検討のまま残した点)の、
   本venture全体を通じた統一的な整理。
5. 優先順位1・2候補(ライディングショップ池上・エクウスワールド)へのヒアリング実施が
   オーナーから承認された場合はその着手を最優先(4節1点目から継続)。
6. 他venture・アイデア領域の前進。

## 7. WorkshopStoreProtocol(契約者引き継ぎ系グループ)の実Firestore接続アダプタ設計

本節は6節3点目で次回候補として残した複数グループのうち、**契約者引き継ぎ系**に着手する。
`get_contractor_user_id`/`set_contractor_user_id`は2節(基盤グループ)で既に設計済み
(`contractor_user_id`は`set_members`が書き込む基盤フィールドのため)であり、本節が新規に
対象とするのは`pending_contractor_transfer`フィールドの3メソッド
(`get_pending_contractor_transfer`/`set_pending_contractor_transfer`/
`clear_pending_contractor_transfer`)のみである。contractor-transfer-confirmation-
detection-design.md 1節・usage_counter_workshop.py 267〜278行目(`PendingContractorTransfer`
dataclass)の通り、`candidate_user_id`/`candidate_member_name`/`requested_at`/`expires_at`の
4フィールドを持つ値を、契約者からの引き継ぎ申請の確定・キャンセル・期限切れのいずれかまで
1件だけ保持する(`InMemoryWorkshopStore`は`workshop_id`をキーとする辞書
`_pending_contractor_transfer_by_workshop`で1workshopにつき1件のみを保持、653行目)。

`InMemoryWorkshopStore`では`PendingContractorTransfer`インスタンスをそのまま辞書の値として
保持しているが、Firestoreでは基盤グループと同じ`craftsman_workshop/{workshop_id}`ドキュメント
内の`pending_contractor_transfer`という単一のmap型フィールドとして、4フィールドをネストした
構造で保存する(他venture・本venture内の既存フィールドはいずれもトップレベルのスカラー値の
みで、本venture初の「1フィールドに複数の値をまとめて保存する」ケースになる)。

```python
    def get_pending_contractor_transfer(
        self, workshop_id: str
    ) -> Optional[PendingContractorTransfer]:
        snapshot = self._doc_ref(workshop_id).get()
        data = (snapshot.to_dict() or {}).get("pending_contractor_transfer")
        if data is None:
            return None
        return PendingContractorTransfer(
            candidate_user_id=data["candidate_user_id"],
            candidate_member_name=data["candidate_member_name"],
            requested_at=data["requested_at"],
            expires_at=data["expires_at"],
        )

    def set_pending_contractor_transfer(
        self, workshop_id: str, pending: PendingContractorTransfer
    ) -> None:
        self._doc_ref(workshop_id).set(
            {
                "pending_contractor_transfer": {
                    "candidate_user_id": pending.candidate_user_id,
                    "candidate_member_name": pending.candidate_member_name,
                    "requested_at": pending.requested_at,
                    "expires_at": pending.expires_at,
                }
            },
            merge=True,
        )

    def clear_pending_contractor_transfer(self, workshop_id: str) -> None:
        self._doc_ref(workshop_id).set(
            {"pending_contractor_transfer": None}, merge=True
        )
```

### 7.1. 検討事項

- **map型フィールドとしてのネスト方式**: `pending_contractor_transfer`を独立コレクション
  (例: `pending_contractor_transfers/{workshop_id}`)に分離する案も検討したが、1workshopに
  つき同時に1件しか存在しない・`craftsman_workshop`ドキュメント自体を取得する既存の処理
  (`check_and_expire_pending_contractor_transfer`等)と同じ読み取りタイミングで参照される
  ため、2節の基盤フィールドと同じドキュメント内のmap型フィールドとする方が読み取り回数を
  増やさずに済む。`pending_links`・`pending_workshop_invites`(2節・フェーズ213・214)が
  独立コレクションなのは、それらが`workshop_id`ではなく発行された`code`をドキュメントID
  とする別の参照経路を持つためであり、本フィールドのように常に`workshop_id`経由でのみ
  参照される値とは構造的な前提が異なる。
- **クリア方式**: `clear_pending_contractor_transfer`は5節の`apply_member_reduction`と同じ
  `None`書き込み方式を採用する。`get_pending_contractor_transfer`が`data is None`判定で
  `None`を返す経路と対応しており、course-set-pasha firestore-provider-adapter-design.md
  9節で確立した「InMemoryのpop()とFirestoreの明示的None書き込みは、get側が常に欠損を
  None扱いする限り観測可能な挙動が一致する」という根拠がここでも成立する。
- **`requested_at`/`expires_at`の型**: Firestoreのmap型フィールド内のタイムスタンプ値も、
  トップレベルフィールドと同様にクライアントライブラリが`datetime`として直接返す
  (`pending_links`の`issued_at`〈2節、本ファイルとは別ドキュメント〉と同じ扱い)ため、
  読み取り側での追加の型変換は不要と判断した。
- **部分更新時の事故防止**: `set_pending_contractor_transfer`はmapフィールド全体を
  `merge=True`で上書きするため、4フィールドのうち一部のみを更新するような呼び出しは
  想定していない(実際の呼び出し元`start_pending_contractor_transfer`〈usage_counter_
  workshop.py〉も常に新しい`PendingContractorTransfer`インスタンス全体を渡す設計であり、
  部分更新の必要性自体が生じない)。

## 8. 残課題・次回候補(7節分)

1. `WorkshopStoreProtocol`の残りのグループ(trial系2フィールド・stripe_customer_id順引き
   逆引き系・subscription_status+各種event_time系・payment_failure系・
   trial_end_notified_at・owner_notified_at系2種)の実Firestore接続アダプタ設計。
2. 一時的な接続エラー時の安全側フォールバック方針(3節で未検討のまま残した点)の、
   本venture全体を通じた統一的な整理。
3. 優先順位1・2候補(ライディングショップ池上・エクウスワールド)へのヒアリング実施が
   オーナーから承認された場合はその着手を最優先(6節5点目から継続)。
4. 他venture・アイデア領域の前進。
