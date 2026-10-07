# UserProfileStoreProtocol の実Firestore接続アダプタ設計

## 1. 背景

`usage_counter_workshop.py`には`UserProfileStoreProtocol`
(`get_workshop_id(user_id)`・`link(user_id, workshop_id)`・`get_is_following(user_id)`・
`set_is_following(user_id, is_following)`)と、検証用の`InMemoryUserProfileStore`スタブ
のみが存在し、実際の`user_profile/{user_id}`ドキュメント(craftsman-account-linking-
design.md 2節・blocked-but-billing-detection-design.md 2節)から`workshop_id`・
`is_following`フィールドを読み書きする具象実装はまだ存在しない。

本ドキュメントは、実Firestoreプロジェクトへの接続(GCPアカウント・課金設定を伴う)が
承認されるまでの間に、接続先が決まった際すぐ実装に移れるよう具象クラスの設計を
先行して詰めておくもの(line-reservation-aiフェーズ続き297の
`FirestoreStoreDocumentProvider`設計と同種の位置づけ)。コード変更・外部アカウント
作成のいずれも行わない。

本ventureには`WorkshopStoreProtocol`(30件超のメソッドを持つ、craftsman_workshop
ドキュメント対応の大きなProtocol)・`UsageCounterStoreProtocol`・
`LinkingCodeStoreProtocol`も存在するが、一度に全てを設計すると検討事項が発散するため、
本フェーズはメソッド数が少なく対象ドキュメントも単一(`user_profile/{user_id}`)の
`UserProfileStoreProtocol`に限定し、残り3つのProtocolは次回候補として個別に設計する
方針とする。

## 2. 設計方針

`get_workshop_id`・`get_is_following`はいずれも同一ドキュメント(`user_profile/{user_id}`)
からの読み取りであるため、line-reservation-aiの設計と同様に1回のドキュメント読み取りを
共有する1つのアダプタクラス`FirestoreUserProfileProvider`で実装する。書き込み系
(`link`・`set_is_following`)は対象フィールドが異なる(`workshop_id`は`link`時に1回
だけ設定、`is_following`はfollow/unfollowの都度更新)ため、`set()`での部分更新
(マージ)として個別に実装する。

```python
class FirestoreUserProfileProvider:
    """UserProfileStoreProtocolの実Firestore接続実装。
    user_profile/{user_id}ドキュメントを読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client

    def _doc_ref(self, user_id: str):
        return self._client.collection("user_profile").document(user_id)

    def _get_doc(self, user_id: str) -> dict:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # ネットワークエラー・権限エラー等はProtocol契約通りの安全側
            # フォールバック(get_workshop_id→None、get_is_following→True)に
            # 合流させ、呼び出し元に例外を伝播させない。
            return {}
        if not snapshot.exists:
            return {}
        return snapshot.to_dict() or {}

    def get_workshop_id(self, user_id: str) -> str | None:
        return self._get_doc(user_id).get("workshop_id")

    def link(self, user_id: str, workshop_id: str) -> None:
        self._doc_ref(user_id).set({"workshop_id": workshop_id}, merge=True)

    def get_is_following(self, user_id: str) -> bool:
        doc = self._get_doc(user_id)
        if "is_following" not in doc:
            # InMemoryUserProfileStoreと同じ既定値: プロフィール未作成・
            # is_following未設定のuser_idはTrue(未フォロー状態は存在しない)。
            return True
        return bool(doc["is_following"])

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        self._doc_ref(user_id).set({"is_following": is_following}, merge=True)
```

## 3. 検討事項

- **読み取り失敗時のフォールバック**: `get_workshop_id`はドキュメント取得失敗時に
  `{}`経由で`None`を返す(未連携として扱われる)。`get_is_following`は取得失敗時も
  `{}`経由で`True`を返す(InMemoryUserProfileStoreの既定値と一致させ、権限エラー等で
  誤って「ブロック中」と判定してしまう事故を避ける安全側の選択)。
- **書き込みは`merge=True`固定**: `link`・`set_is_following`はいずれも単一フィールドの
  部分更新であり、ドキュメント全体を上書きしない(他フィールドを巻き込んで消さない
  ため`merge=True`を必須とする)。
- **キャッシュ化は見送り**: line-reservation-aiの設計と同じ理由(firestore-traffic-
  cost-estimate.md相当の試算は本venture未作成だが、想定トラフィック規模・1イベントあたりの
  読み取り回数から見て現時点では過剰設計と判断)で、インスタンス単位の簡易キャッシュ等は
  導入しない。
- **依存ライブラリ**: `google-cloud-firestore`を想定(tech-stack.md 4節のCloud Run
  functions (2nd gen) + Firestore選定と一致)。`firestore_client`をコンストラクタ注入する
  形とし、テスト時は`InMemoryUserProfileStore`を使い続ける(本クラスは実クライアント接続後の
  結合テストでのみ使用する)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちで
  あり、本設計のコードは承認後の結合実装フェーズまでコミットしない。
- 本フェーズで設計を見送った`WorkshopStoreProtocol`(craftsman_workshopドキュメント、
  30件超のメソッド)・`UsageCounterStoreProtocol`(usage_counterドキュメント)・
  `LinkingCodeStoreProtocol`(pending_workshop_invitesドキュメント)の実Firestore接続
  アダプタは、本ドキュメントと同じ方針(ドキュメント単位でアダプタクラスを分け、
  `merge=True`の部分更新・安全側フォールバックを踏襲)で今後個別に設計する。
- 承認後は、`usage_counter_workshop.py`・`workshop_linking.py`の各処理関数へ
  `user_profile_store`として本クラスのインスタンスを渡すだけで差し替えが完了する
  設計になっていることを、結合実装時に確認する。
