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
