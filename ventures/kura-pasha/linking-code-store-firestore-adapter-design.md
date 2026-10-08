# LinkingCodeStoreProtocol の実Firestore接続アダプタ設計

## 1. 背景

`prototype/workshop_linking.py`には`LinkingCodeStoreProtocol`(`save`/`get`/`delete`/
`items`、66〜80行目)と、検証用の`InMemoryLinkingCodeStore`スタブのみが存在し、実際の
`pending_links/{code}`ドキュメント(craftsman-account-linking-design.md 2節、112行目の
データモデル表)を読み書きする具象実装はまだ存在しない。

firestore-provider-adapter-design.md 4節(フェーズ295)が、本venture自身の残課題として
`WorkshopStoreProtocol`(craftsman_workshopドキュメント、30件超のメソッド)・
`UsageCounterStoreProtocol`(usage_counterドキュメント、firestore-usage-counter-
provider-adapter-design.mdでフェーズ211に設計済み)・`LinkingCodeStoreProtocol`
(pending_workshop_invitesドキュメント、と本節で扱う`pending_links`ドキュメントの両方に
`LinkingCodeStoreProtocol`という同名の型が使われている点に注意)を個別に設計する方針を
挙げていた。本ドキュメントはこのうち最もメソッド数が少なく対象ドキュメントも単一である
`pending_links/{code}`向けの`LinkingCodeStoreProtocol`(follow時の新規workshop作成用
連携コード)を先行して設計する。`pending_workshop_invites`向けの招待コード
(craftsman-account-linking-design.md 11節、既存workshopへのメンバー追加用、263行目の
`PendingInviteStoreProtocol`相当)は名前空間が分離された別ドキュメント・別Protocolであり、
本ドキュメントの対象外として次回候補に残す。

course-set-pasha(本venture最新フェーズ274)が自身の`LinkingCodeStoreProtocol`に対して
作成した`firestore-provider-adapter-design.md`と、シグネチャ(`save(code, user_id, issued_at)`
で`user_id`を文字列のまま直接受け取る)・対象ドキュメント構造(`pending_links/{code}`を
`code`をドキュメントIDとする単純な1ドキュメント1エントリ)が完全に一致するため、同じ設計
方針をそのまま本venture向けに適用する。コード変更・外部アカウント作成のいずれも行わない。

## 2. 設計方針

`pending_links`は`code`をドキュメントIDとする単純な1ドキュメント1エントリの構造のため、
`save`/`get`/`delete`はドキュメント単位の読み書きで素直に実装できる。`items()`のみ、
期限切れパージ(`purge_expired_links`、workshop_linking.py 432〜440行目)のために全件を
列挙する必要があり、`pending_links`コレクション全体の`stream()`が必要になる。

```python
class FirestorePendingLinkStore:
    """LinkingCodeStoreProtocol(pending_links/{code}向け)の実Firestore接続実装。"""

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
            # ネットワークエラー・権限エラー等は「未発見」(None)に倒す。連携コード
            # 解決の失敗時フォールバック(「コードが無効です」等の案内)と同じ扱いになり、
            # 誤って例外を伝播させて処理全体を落とすよりも安全側。
            return None
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        user_id = data.get("user_id")
        issued_at = data.get("issued_at")
        if user_id is None or issued_at is None:
            return None
        return (user_id, issued_at)

    def delete(self, code: str) -> None:
        self._collection.document(code).delete()

    def items(self) -> Iterable[Tuple[str, str, datetime]]:
        for snapshot in self._collection.stream():
            data = snapshot.to_dict() or {}
            user_id = data.get("user_id")
            issued_at = data.get("issued_at")
            if user_id is None or issued_at is None:
                continue
            yield (snapshot.id, user_id, issued_at)
```

## 3. 検討事項

- **書き込み方式**: `save()`は`set()`(フィールド全体の置き換え)を使う。`pending_links/
  {code}`は発行時に1回書き込まれた後は`delete()`されるだけの使い切りトークンであり、
  既存フィールドとの部分マージを考慮する必要がないため`merge=True`は不要
  (course-set-pashaの設計と同一の判断)。
- **読み取り失敗・フィールド欠損時のフォールバック**: `get()`はドキュメント取得失敗時・
  `user_id`/`issued_at`いずれかのフィールド欠損時のいずれも`None`を返す
  (`InMemoryLinkingCodeStore.get()`が辞書に存在しないキーに対して`None`を返す挙動と
  一致させる)。呼び出し元(`resolve_linking_code`相当のロジック)は`None`を「コードが
  無効・期限切れ」と同じ経路で処理する前提のため、ここで例外を伝播させない。
- **`items()`のコスト**: `purge_expired_links()`は間引きトリガー(`LinkingCodePurgeThrottle`、
  workshop_linking.py 398行目)経由の呼び出しのたびに`pending_links`コレクション全件を
  読み取る。本venture想定トラフィック(個人〜小規模の鞍・馬具工房、MAX_MEMBER_COUNT=5名
  規模)では過剰設計と判断し、`issued_at`への複合インデックス+範囲クエリでの絞り込みは
  見送る(course-set-pashaの判断を踏襲)。トラフィックが増えた場合の次回候補として記録する。
- **依存ライブラリ**: `google-cloud-firestore`を想定(tech-stack.md記載のCloud Run
  functions (2nd gen) + Firestore選定と一致)。`firestore_client`をコンストラクタ注入する
  形とし、テスト時は`InMemoryLinkingCodeStore`を使い続ける(本クラスは実クライアント接続後の
  結合テストでのみ使用する)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちで
  あり、本設計のコードは承認後の結合実装フェーズまでコミットしない。
- 本ドキュメントの対象外とした`pending_workshop_invites`向け招待コードStore
  (craftsman-account-linking-design.md 11節、既存workshopへのメンバー追加用)の実
  Firestore接続アダプタは、ドキュメント構造(`{workshop_id, issued_at}`を保存、2節の
  `pending_links`と名前空間を分離)が異なるため別ドキュメントとして個別に設計する。
- firestore-provider-adapter-design.md 4節の残課題のうち、本ドキュメントで未着手の
  `WorkshopStoreProtocol`(30件超のメソッド)は引き続き次回候補とする。
- 承認後は、`workshop_linking.py`の各処理関数へ`linking_code_store`として本クラスの
  インスタンスを渡すだけで差し替えが完了する設計になっていることを、結合実装時に確認する。
