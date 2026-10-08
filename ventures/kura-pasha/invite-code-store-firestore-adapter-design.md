# 招待コードStore(pending_workshop_invites)の実Firestore接続アダプタ設計

## 1. 背景

linking-code-store-firestore-adapter-design.md(フェーズ213)は、`LinkingCodeStoreProtocol`
(`save`/`get`/`delete`/`items`、workshop_linking.py 66〜80行目)のうち`pending_links/{code}`
(follow時の新規workshop作成用連携コード、値は`user_id`)向けの実Firestore接続アダプタ
`FirestorePendingLinkStore`を設計し、同ドキュメントの対象外として`pending_workshop_invites`
(既存workshopへのメンバー追加用招待コード、craftsman-account-linking-design.md 11節)向けの
アダプタを次回候補に残していた。本ドキュメントはその残課題を扱う。

`pending_workshop_invites`は`issue_invite_code_for_workshop()`・`resolve_invite_code()`・
`add_member_from_invite_code()`(workshop_linking.py 251〜394行目)が同じ
`LinkingCodeStoreProtocol`型の`invite_store`引数経由で読み書きする、`pending_links`とは
名前空間が分離された別コレクションである。保存する値が`user_id`ではなく`workshop_id`である点
(289〜290行目`invite_store.save(code, workshop_id, now)`)のみが`pending_links`との構造上の
差分で、コード仕様(6文字・31種アルファベット・24時間TTL)・使い切り一回限りの挙動は同一。

## 2. 設計方針

`pending_links`向けの`FirestorePendingLinkStore`(フェーズ213)と同じ理由により、`save`/`get`/
`delete`はドキュメント単位の読み書き、`items()`のみ`purge_expired_links()`
(workshop_linking.py 432〜440行目、`LinkingCodePurgeThrottle`経由で間引きされる)のための
全件`stream()`とする。コレクション名と、保存・取得するフィールド名(`user_id`→`workshop_id`)
のみが差分であり、クラス構造はフェーズ213の設計をそのまま転用する。

```python
class FirestoreWorkshopInviteStore:
    """LinkingCodeStoreProtocol(pending_workshop_invites/{code}向け)の実Firestore接続実装。

    招待コード発行時(issue_invite_code_for_workshop)は`workshop_id`を保存し、解決時
    (resolve_invite_code)は保存した`workshop_id`を復元する。フィールド名が`user_id`では
    なく`workshop_id`である点以外は、FirestorePendingLinkStore(linking-code-store-
    firestore-adapter-design.md)と設計方針が完全に一致する。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("pending_workshop_invites")

    def save(self, code: str, workshop_id: str, issued_at: datetime) -> None:
        self._collection.document(code).set(
            {"workshop_id": workshop_id, "issued_at": issued_at}
        )

    def get(self, code: str) -> Optional[Tuple[str, datetime]]:
        try:
            snapshot = self._collection.document(code).get()
        except Exception:
            # pending_links向け実装と同じ理由(フェーズ213)で「未発見」(None)に倒す。
            # 招待コード解決の失敗時フォールバック(resolve_invite_code、workshop_linking.py
            # 324〜329行目)と同じ扱いになり、誤って例外を伝播させるよりも安全側。
            return None
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        workshop_id = data.get("workshop_id")
        issued_at = data.get("issued_at")
        if workshop_id is None or issued_at is None:
            return None
        return (workshop_id, issued_at)

    def delete(self, code: str) -> None:
        self._collection.document(code).delete()

    def items(self) -> Iterable[Tuple[str, str, datetime]]:
        for snapshot in self._collection.stream():
            data = snapshot.to_dict() or {}
            workshop_id = data.get("workshop_id")
            issued_at = data.get("issued_at")
            if workshop_id is None or issued_at is None:
                continue
            yield (snapshot.id, workshop_id, issued_at)
```

## 3. 検討事項

- **`LinkingCodeStoreProtocol`という同名の型を2つの異なるコレクションに使う設計への対応**:
  `pending_links`向け(`FirestorePendingLinkStore`)と本ドキュメントの
  `FirestoreWorkshopInviteStore`はいずれも同じ`LinkingCodeStoreProtocol`を実装するが、
  コンストラクタで異なる`firestore_client.collection(...)`を参照するだけの別クラスとする
  (フェーズ251の`issue_invite_code_for_workshop`呼び出し箇所で`invite_store`に本クラスの
  インスタンスを、`create_workshop_from_linking_code`呼び出し箇所で`linking_code_store`に
  `FirestorePendingLinkStore`のインスタンスを、それぞれ結合実装時に渡すだけで差し替えが
  完了する)。1つのクラスをコレクション名だけ引数化して共用する案も検討したが、
  `pending_links`と`pending_workshop_invites`は将来的にフィールド追加等で構造が分岐し得る
  (例: 招待コード側にのみ発行者情報を追加する等)ため、別クラスとして分離した方が
  変更の影響範囲を閉じ込められると判断した。
- **書き込み方式・読み取り失敗時のフォールバック**: `FirestorePendingLinkStore`
  (フェーズ213)と同じ判断(`set()`で全体置き換え、取得失敗・フィールド欠損はいずれも
  `None`へのフォールバック)を踏襲する。
- **`items()`のコスト**: `purge_expired_links()`は`pending_links`・
  `pending_workshop_invites`の両コレクションに対してそれぞれ独立した`LinkingCodePurgeThrottle`
  インスタンス経由で呼ばれる想定(cloud_function_webhook.py側の結合実装で2つのスケジューラ
  トリガーを設ける、または1つのトリガーから両コレクションへ順に`purge_expired_links()`を
  呼ぶ)。本venture想定トラフィック(個人〜小規模の鞍・馬具工房、MAX_MEMBER_COUNT=5名規模)
  では、フェーズ213と同じ判断により複合インデックス+範囲クエリでの絞り込みは見送る。
- **依存ライブラリ**: `google-cloud-firestore`を想定(tech-stack.md記載の選定と一致)。
  `firestore_client`をコンストラクタ注入する形とし、テスト時は`InMemoryLinkingCodeStore`
  (workshop_linking.py、`pending_links`・`pending_workshop_invites`どちらの検証にも
  同じスタブを使い分けて使用中)を使い続ける。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちで
  あり、本設計のコードは承認後の結合実装フェーズまでコミットしない。
- firestore-provider-adapter-design.md 4節の残課題のうち、`WorkshopStoreProtocol`
  (craftsman_workshopドキュメント、30件超のメソッド)は未着手で引き続き次回候補とする。
  これにより、本venture自身が残していた個別Protocol(`UsageCounterStoreProtocol`
  〈フェーズ211〉・`LinkingCodeStoreProtocol`のpending_links向け〈フェーズ213〉・
  pending_workshop_invites向け〈本フェーズ〉)の設計は、`WorkshopStoreProtocol`を残し
  一通り完了した。
- 承認後は、`issue_invite_code_for_workshop`・`resolve_invite_code`・
  `add_member_from_invite_code`の各呼び出し箇所へ`invite_store`として本クラスの
  インスタンスを渡すだけで差し替えが完了する設計になっていることを、結合実装時に確認する。
