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
  実Firestore接続アダプタ設計は本フェーズの対象外とし、次回候補として残す。フィールド数が
  多いため、一度に全メソッドを設計するのではなく、既存の関連Protocol(`CurrentPlanStore
  Protocol`・`PaymentFailureStoreProtocol`等、duck typingで同一ストアを満たす薄い
  Protocol群)単位で段階的に設計範囲を区切ることを検討する。
- 承認後は、`cloud_function_webhook.py`・`user_id_linking.py`呼び出し側の
  `LinkingCodeStoreProtocol`実装注入箇所に本クラスのインスタンスを渡すだけで差し替えが
  完了する設計になっていることを、結合実装時に確認する。
