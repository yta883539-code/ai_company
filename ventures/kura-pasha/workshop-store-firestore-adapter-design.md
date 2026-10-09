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

## 9. WorkshopStoreProtocol(trial系グループ)の実Firestore接続アダプタ設計

本節は8節1点目で次回候補として残した複数グループのうち、**trial系2フィールド**に着手する。

着手にあたり、`usage_counter_workshop.py`の`WorkshopStoreProtocol`(303〜642行目)を
確認したところ、`set_trial_start_at`が`InMemoryWorkshopStore`(751行目)には実装されて
いるにもかかわらずProtocol側に宣言されていないことを発見した。1節1.1節で是正した
`set_members`のProtocol宣言漏れと同種の不整合であるため、本フェーズの前提作業として
`get_trial_start_at`(414行目)の直後にProtocol宣言を追加して是正した。

対象は`trial_start_at`(datetime、workshop作成時に1回だけ設定)・`trial_generation_used`
(bool、生涯最初の生成成功時に1回だけTrueへ更新)の2フィールド・4メソッド
(`get_trial_start_at`/`set_trial_start_at`/`get_trial_generation_used`/
`set_trial_generation_used`)。いずれも2節の基盤グループと同じ`craftsman_workshop/
{workshop_id}`ドキューメント内のトップレベルのスカラー値であり、map型フィールドの
ネスト(7節)やArrayUnion(2節`add_member_user_id`)のような特殊な操作を必要としない。

```python
    def get_trial_start_at(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("trial_start_at")

    def set_trial_start_at(self, workshop_id: str, trial_start_at: datetime) -> None:
        self._doc_ref(workshop_id).set(
            {"trial_start_at": trial_start_at}, merge=True
        )

    def get_trial_generation_used(self, workshop_id: str) -> bool:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("trial_generation_used", False)

    def set_trial_generation_used(self, workshop_id: str, used: bool = True) -> None:
        self._doc_ref(workshop_id).set(
            {"trial_generation_used": used}, merge=True
        )
```

### 9.1. 検討事項

- **`get_trial_start_at`が`None`を返すケース**: `trial_start_at`は`workshop_linking.py`の
  workshop新規作成処理(235行目)で必ず設定されるため、正常稼働時には未設定の
  `craftsman_workshop`ドキュメントは存在しない想定である。それでも`.get()`のデフォルト
  引数を省略し`None`を素直に返す実装とした理由は、`is_trial_period_over()`
  (usage_counter_workshop.py 952〜953行目)が`trial_start_at is None`の場合を
  「データ不整合・移行中」として明示的に安全側(トライアル未終了扱い)に倒す分岐を既に
  持っており、アダプタ側で独自のデフォルト値を補って不整合を隠蔽しない方が、この既存の
  安全側分岐を正しく機能させられるため。
- **`set_trial_generation_used`のデフォルト引数**: `used: bool = True`という
  Protocol側のデフォルト引数(usage_counter_workshop.py 424行目)をアダプタの
  メソッドシグネチャにもそのまま引き継いだ。呼び出し元(1149〜1156行目の
  `process_generation_request`)は常に`True`固定で呼び出すためデフォルト値が
  実際に使われる経路は現状ないが、`InMemoryWorkshopStore.set_trial_generation_used`
  (757行目)もProtocol通りのデフォルト引数を持つため、アダプタ側だけ省略すると
  Protocol適合性(構造的部分型)が崩れてしまう。
- **一度切りフラグとしての冪等性**: `set_trial_generation_used`はFalse→Trueへの
  一方向の更新のみを想定する(5節の`apply_member_reduction`のようなクリア操作は
  存在しない)。同じ値への複数回の書き込み(例えば既にTrueの状態へ再度`True`を
  書き込む)もFirestoreの`merge=True`では単純な上書きとして安全に収束するため、
  読み取り後の条件分岐(read-modify-write)は不要と判断した。

## 10. 残課題・次回候補(9節分)

1. `WorkshopStoreProtocol`の残りのグループ(stripe_customer_id順引き逆引き系・
   subscription_status+各種event_time系・payment_failure系・trial_end_notified_at・
   owner_notified_at系2種)の実Firestore接続アダプタ設計。
2. 一時的な接続エラー時の安全側フォールバック方針(3節で未検討のまま残した点)の、
   本venture全体を通じた統一的な整理。
3. 優先順位1・2候補(ライディングショップ池上・エクウスワールド)へのヒアリング実施が
   オーナーから承認された場合はその着手を最優先(6節5点目から継続)。
4. 他venture・アイデア領域の前進。

## 11. WorkshopStoreProtocol(stripe_customer_id順引き逆引き系グループ)の実Firestore接続アダプタ設計

本節は10節1点目で次回候補として残した複数グループのうち、**stripe_customer_id順引き・
逆引き系**に着手する。対象は`get_stripe_customer_id`/`set_stripe_customer_id`/
`get_workshop_id_by_stripe_customer_id`の3メソッド(usage_counter_workshop.py 436〜452
行目)。`get_workshop_id_by_stripe_customer_id`のdocstringが明記する通り、aircon-pasha・
course-set-pashaの`get_user_id_by_stripe_customer_id`と同じ位置づけ(`client_reference_id`
を持たないStripe Webhookイベントがworkshop_idを解決するための逆引き)であり、aircon-pasha
firestore-provider-adapter-design.md 5節で確立した設計をそのまま踏襲する。

順引き(`get_stripe_customer_id`/`set_stripe_customer_id`)は2節の基盤グループと同じ
`craftsman_workshop/{workshop_id}`ドキューメント内のトップレベルのスカラー値で素直に
実装できる。逆引き(`get_workshop_id_by_stripe_customer_id`)は、`craftsman_workshop`
コレクション全体への`where("stripe_customer_id", "==", ...)`クエリでも実現できるが、
`customer.subscription.*`イベント受信のたびにクエリを発行するより、専用の逆引き
コレクション`stripe_customer_index/{stripe_customer_id}`(値は`workshop_id`の文字列)を
`set_stripe_customer_id`実行時に同時書き込みする方式を採用する(`InMemoryWorkshopStore`
が`_workshop_id_by_stripe_customer_id`辞書を別持ちしている設計〈662〜663行目〉と対応
させるため)。aircon-pasha・line-reservation-aiの両設計と同じコレクション名
`stripe_customer_index`を用いる(本venture〈kura-pasha〉は別のFirestoreプロジェクトを
使う想定のため、コレクション名の衝突は生じない)。

```python
    def get_stripe_customer_id(self, workshop_id: str) -> Optional[str]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("stripe_customer_id")

    def set_stripe_customer_id(self, workshop_id: str, stripe_customer_id: str) -> None:
        batch = self._client.batch()
        batch.set(
            self._doc_ref(workshop_id),
            {"stripe_customer_id": stripe_customer_id},
            merge=True,
        )
        batch.set(
            self._stripe_index.document(stripe_customer_id),
            {"workshop_id": workshop_id},
        )
        batch.commit()

    def get_workshop_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        snapshot = self._stripe_index.document(stripe_customer_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("workshop_id")
```

(`__init__`に`self._stripe_index = firestore_client.collection("stripe_customer_index")`
を2節の`self._workshops`と並べて追加する想定。`set_stripe_customer_id`がバッチ書き込みを
使うため、`self._client`〈firestoreクライアント本体への参照〉も2節の`__init__`に保持して
おく必要がある。)

### 11.1. 検討事項

- **バッチ書き込みによる原子性**: aircon-pasha 5.3節と同じく、`set_stripe_customer_id`は
  `craftsman_workshop/{workshop_id}`の`stripe_customer_id`フィールド更新と
  `stripe_customer_index/{stripe_customer_id}`ドキュメントの新規作成を`WriteBatch`で
  同時実行し、片方のみ書き込まれる不整合を避ける。
- **付け替え時の旧インデックスエントリ**: aircon-pashaはこの問題を5.3節で「本venture想定
  では発生しない契約」として次回候補に残したが、line-reservation-ai
  stripe-customer-id-reverse-lookup-design.mdは既に旧エントリ削除まで実装した、より
  完成度の高い設計を確立している。本venture(kura-pasha)の呼び出し元
  (`checkout-session-completed-handling-design.md`相当の処理、新規Checkout Session完了時
  に1回だけ呼ばれる想定)も同一`workshop_id`からの2回目の`set_stripe_customer_id`呼び出しは
  想定していないため、本節ではaircon-pasha側の簡潔な設計(新規設定ケースのみ)を踏襲し、
  旧インデックス削除はline-reservation-aiの設計を参考にした改善の次回候補として残す
  (12節)。
- **`get_stripe_customer_id`が`None`を返すケース**: `subscription-billing-data-model-design.md`
  1節の通り、未契約(トライアル中含む)のworkshopは`stripe_customer_id`が未設定のため
  `None`を返すのが正しい挙動であり、9.1節の`trial_start_at`と異なり「データ不整合」を
  示す値ではない。アダプタ側で独自のデフォルト値を補う必要はない。
- **例外方針は本節では未検討のまま**: 3節で指摘した「一時的な接続エラー時の安全側
  フォールバック方針」は9節までと同様、本節でも個別には検討せず、12節2点目の統一的整理に
  委ねる。

## 12. 残課題・次回候補(11節分)

1. 付け替え時の旧`stripe_customer_index`エントリ削除(11.1節、line-reservation-aiの設計を
   参考に改善)。
2. `WorkshopStoreProtocol`の残りのグループ(subscription_status+各種event_time系・
   payment_failure系・trial_end_notified_at・owner_notified_at系2種)の実Firestore接続
   アダプタ設計。
3. 一時的な接続エラー時の安全側フォールバック方針(3節で未検討のまま残した点)の、
   本venture全体を通じた統一的な整理。
4. 優先順位1・2候補(ライディングショップ池上・エクウスワールド)へのヒアリング実施が
   オーナーから承認された場合はその着手を最優先(6節5点目から継続)。
5. 他venture・アイデア領域の前進。

## 13. WorkshopStoreProtocol(subscription_status+各種event_time系グループ)の実Firestore接続アダプタ設計

### 13.1. 背景・範囲

本節は12節2点目で次回候補として残した複数グループのうち、**subscription_status+各種
event_time系**に着手する。対象は`get_subscription_status`/`set_subscription_status`・
`get_subscription_status_event_time`/`set_subscription_status_event_time`・
`get_checkout_session_completed_event_time`/`set_checkout_session_completed_event_time`・
`get_subscription_updated_event_time`/`set_subscription_updated_event_time`・
`get_current_period_end`/`set_current_period_end`の5フィールド・計10メソッド
(usage_counter_workshop.py 454〜526行目)。

event_time系4フィールドは、aircon-pasha firestore-provider-adapter-design.md 17節が
`UserProfileStoreProtocol`向けに確立した「Stripe Webhookイベントの配信順序入れ替わり
ガード用の基準線としてのみ使われる単純な読み書き」という設計方針と同じ性質を持つ
(本venture側のガード設計も、各フィールドのdocstringが指す
`subscription-status-event-order-guard-design.md`・
`checkout-session-completed-plan-event-order-guard-design.md`・
`subscription-updated-event-order-guard-design.md`という、aircon-pasha・
course-set-pasha・line-reservation-aiと同名の設計ドキュメント群を前提としている)。
いずれも2節の基盤グループ・9節のtrial系・11節のstripe_customer_id順引きと同じ
`craftsman_workshop/{workshop_id}`ドキューメント内のトップレベルのスカラー値であり、
map型フィールドのネスト(7節)やArrayUnion(2節`add_member_user_id`)・専用逆引き
コレクション(11節)のような特殊な操作を必要としない。

### 13.2. 設計

```python
    def get_subscription_status(self, workshop_id: str) -> str:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("subscription_status", "trialing")

    def set_subscription_status(self, workshop_id: str, status: str) -> None:
        if status not in SUBSCRIPTION_STATUSES:
            raise InvalidSubscriptionStatusError(
                f"unknown subscription_status: {status!r} "
                f"(expected one of {SUBSCRIPTION_STATUSES})"
            )
        self._doc_ref(workshop_id).set({"subscription_status": status}, merge=True)

    def get_subscription_status_event_time(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("subscription_status_event_time")

    def set_subscription_status_event_time(
        self, workshop_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"subscription_status_event_time": event_time}, merge=True
        )

    def get_checkout_session_completed_event_time(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("checkout_session_completed_event_time")

    def set_checkout_session_completed_event_time(
        self, workshop_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"checkout_session_completed_event_time": event_time}, merge=True
        )

    def get_subscription_updated_event_time(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("subscription_updated_event_time")

    def set_subscription_updated_event_time(
        self, workshop_id: str, event_time: datetime
    ) -> None:
        self._doc_ref(workshop_id).set(
            {"subscription_updated_event_time": event_time}, merge=True
        )

    def get_current_period_end(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("current_period_end")

    def set_current_period_end(self, workshop_id: str, current_period_end: datetime) -> None:
        self._doc_ref(workshop_id).set(
            {"current_period_end": current_period_end}, merge=True
        )
```

### 13.3. 検討事項

- **`get_subscription_status`の安全側デフォルト値**: event_time系4フィールドが
  いずれも「未設定=未受信」を表す`None`デフォルトであるのに対し、`subscription_status`
  だけはドキュメント・フィールド欠損時に`"trialing"`をデフォルトとする。これは
  `InMemoryWorkshopStore.get_subscription_status`(779〜780行目)の挙動
  (`self._subscription_status_by_workshop.get(workshop_id, "trialing")`)に合わせた
  もので、docstring(subscription-billing-data-model-design.md 1節)が明記する通り
  「未契約・トライアル中のworkshopは"trialing"」という業務上の初期状態を表す値であり、
  9.1節で`trial_start_at`について検討した「データ不整合を隠蔽しない」方針とは逆に、
  ここでは`None`ではなく明示的なデフォルト値を補うことが正しい実装である。
- **`set_subscription_status`のバリデーションはFirestore書き込み前に完結させる**:
  `InvalidSubscriptionStatusError`の送出は`InMemoryWorkshopStore.set_subscription_status`
  (782〜787行目)と同じく、Firestoreへの`set()`呼び出し自体を行う前にPython側の
  値チェックで完結させる。Firestore側のスキーマバリデーション機能(セキュリティルール等)
  には依存しない設計とした。
- **event_time系4フィールドはaircon-pasha 17節と同型だが取得経路が異なる**: aircon-pasha
  17節は`UserProfileStoreProtocol`が内部で保持する`UserProfile`dataclassの属性として
  これらのフィールドを読み書きするため`self.get(user_id)`経由の間接参照になっているが、
  本venture(kura-pasha)の`WorkshopStoreProtocol`は2節・9節・11節同様dataclassを介さない
  トップレベルのスカラーフィールド群であるため、`self._doc_ref(workshop_id).get()`から
  直接`to_dict()`で読み取る9節・11節と同じ直接参照方式を踏襲した。読み書きの意味論
  (順序ガード用の基準線としてのみ使う、呼び出し元は常にStripe Webhookハンドラ)自体は
  aircon-pasha 17節と変わらない。
- **例外方針は本節でも未検討のまま**: 3節・9.1節・11.1節で指摘した「一時的な接続エラー時の
  安全側フォールバック方針」は、本節でも個別には検討せず、12節3点目・本節末の統一的整理に
  委ねる。

## 14. 残課題・次回候補(13節分)

1. `WorkshopStoreProtocol`の残りのグループ(payment_failure系・trial_end_notified_at・
   owner_notified_at系2種)の実Firestore接続アダプタ設計。
2. 付け替え時の旧`stripe_customer_index`エントリ削除(11.1節・12節1点目、line-reservation-ai
   の設計を参考に改善、未着手のまま継続)。
3. 一時的な接続エラー時の安全側フォールバック方針(3節で未検討のまま残した点)の、
   本venture全体を通じた統一的な整理。
4. 優先順位1・2候補(ライディングショップ池上・エクウスワールド)へのヒアリング実施が
   オーナーから承認された場合はその着手を最優先(6節5点目から継続)。
5. 他venture・アイデア領域の前進。

## 15. WorkshopStoreProtocol(payment_failure系グループ)の実Firestore接続アダプタ設計

### 15.1. 背景・範囲

本節は14節1点目で次回候補として残した複数グループのうち、**payment_failure系**に着手する。
対象は`get_payment_failure_detected_at`/`set_payment_failure_detected_at`/
`clear_payment_failure_detected_at`・`get_payment_failure_reminder_sent_at`/
`set_payment_failure_reminder_sent_at`の2フィールド・計5メソッド
(usage_counter_workshop.py 528〜554行目)。

aircon-pasha firestore-provider-adapter-design.md 394〜421行目は`UserProfileStoreProtocol`
側の同名フィールドを「`set_*`にOptional値を渡すことでクリアも表現する1メソッド方式」で
設計しているが、本venture(kura-pasha)の`WorkshopStoreProtocol`はdocstring(usage_counter_
workshop.py 578〜580行目)が明記する通り、意図的に`set_payment_failure_detected_at`
(値は必須)と`clear_payment_failure_detected_at`(引数なし)を2メソッドに分けている。
さらに`InMemoryWorkshopStore.clear_payment_failure_detected_at`(825〜828行目)は
`payment_failure_detected_at`だけでなく`payment_failure_reminder_sent_at`・
`payment_suspension_owner_notified_at`(14節1点目の owner_notified_at系2種のうち未設計の
1フィールド)の計3フィールドを同時にクリアする仕様であり、本節ではこの3フィールド
同時クリアの挙動も含めて設計する(`payment_suspension_owner_notified_at`自体の
get/set設計は、1個のフィールドのみ先行してここで扱うことになるため、本体のget/set設計は
次回候補に残すowner_notified_at系2種の節に委ねる)。

### 15.2. 設計

```python
    def get_payment_failure_detected_at(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("payment_failure_detected_at")

    def set_payment_failure_detected_at(self, workshop_id: str, detected_at: datetime) -> None:
        self._doc_ref(workshop_id).set(
            {"payment_failure_detected_at": detected_at}, merge=True
        )

    def clear_payment_failure_detected_at(self, workshop_id: str) -> None:
        self._doc_ref(workshop_id).set(
            {
                "payment_failure_detected_at": None,
                "payment_failure_reminder_sent_at": None,
                "payment_suspension_owner_notified_at": None,
            },
            merge=True,
        )

    def get_payment_failure_reminder_sent_at(self, workshop_id: str) -> Optional[datetime]:
        snapshot = self._doc_ref(workshop_id).get()
        return (snapshot.to_dict() or {}).get("payment_failure_reminder_sent_at")

    def set_payment_failure_reminder_sent_at(self, workshop_id: str, sent_at: datetime) -> None:
        self._doc_ref(workshop_id).set(
            {"payment_failure_reminder_sent_at": sent_at}, merge=True
        )
```

### 15.3. 検討事項

- **`clear_payment_failure_detected_at`は単一ドキュメントへの1回の`set(merge=True)`で
  3フィールドを同時にクリアする**: 11節の`stripe_customer_index`のような別ドキュメントへの
  書き込みを伴わないため、`WriteBatch`は不要で、1回の`set()`呼び出し自体がFirestore上で
  アトミックに完結する(同一ドキュメント内の複数フィールド更新は単一の書き込み操作として
  扱われる)。
- **クリアは`DELETE_FIELD`センチネルではなく`None`値の書き込みで表現する**: aircon-pasha
  394〜421行目・本venture自身の`set_blocked_but_billing_owner_notified_at`
  (docstring578〜581行目)と同じ方針を踏襲し、フィールド自体をドキュメントから削除する
  のではなく値を`None`にする。`get_*`側が`.get(フィールド名)`で`None`デフォルトを返す
  実装(9節以降で踏襲している方式)と対称であり、どちらの手段でも`get_*`の観測結果は
  同じになるため、既存設計との一貫性を優先して値`None`書き込み方式を採用した。
- **`payment_suspension_owner_notified_at`への書き込みは本節のclear経路のみを先行設計**:
  15.1節の通り、同フィールド自体の`get_payment_suspension_owner_notified_at`/
  `set_payment_suspension_owner_notified_at`の設計(owner_notified_at系2種グループ)は
  次回候補に残すが、`clear_payment_failure_detected_at`が同フィールドにも書き込む仕様
  (InMemory実装828行目)は本節の対象(payment_failure系)に含まれるdocstring
  (usage_counter_workshop.py 596〜599行目)上の要求であるため、ここで先行して
  組み込んだ。次回のowner_notified_at系2種の節では、本節のclear経路との整合性
  (両者が同じフィールド名`payment_suspension_owner_notified_at`に書き込むこと)を
  確認する作業が残る。
- **例外方針は本節でも未検討のまま**: 3節・9.1節・11.1節・13.3節で指摘した「一時的な
  接続エラー時の安全側フォールバック方針」は、本節でも個別には検討せず、12節3点目・
  14節3点目の統一的整理に委ねる。

## 16. 残課題・次回候補(15節分)

1. `WorkshopStoreProtocol`の残りのグループ(trial_end_notified_at・owner_notified_at系2種)
   の実Firestore接続アダプタ設計。owner_notified_at系2種の節では15.3節で先行実装した
   `payment_suspension_owner_notified_at`へのclear経路との整合性確認も行う。
2. 付け替え時の旧`stripe_customer_index`エントリ削除(11.1節・12節1点目、line-reservation-ai
   の設計を参考に改善、未着手のまま継続)。
3. 一時的な接続エラー時の安全側フォールバック方針(3節で未検討のまま残した点)の、
   本venture全体を通じた統一的な整理。
4. 優先順位1・2候補(ライディングショップ池上・エクウスワールド)へのヒアリング実施が
   オーナーから承認された場合はその着手を最優先(6節5点目から継続)。
5. 他venture・アイデア領域の前進。
