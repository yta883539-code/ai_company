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

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちで
  あり、本設計のコードは承認後の結合実装フェーズまでコミットしない。
- `UserProfileStoreProtocol`(application_form_submission_flow.py・checkout_session.py・
  portal_session.py等に個別定義された薄いProtocol群)の実Firestore接続アダプタ設計は
  本フェーズの対象外とし、次回候補として残す。定義箇所が複数モジュールに分かれているため、
  まず対象ドキュメント(`user_profile/{user_id}`)上のフィールド一覧を1箇所に整理した上で
  着手することを検討する。
- 承認後は、`user_id_linking.py`・`cloud_function_webhook.py`呼び出し側の
  `LinkingCodeStoreProtocol`実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが
  完了する設計になっていることを、結合実装時に確認する。
