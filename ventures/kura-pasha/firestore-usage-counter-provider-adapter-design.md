# UsageCounterStoreProtocol の実Firestore接続アダプタ設計

## 1. 背景

`usage_counter_workshop.py`の`UsageCounterStoreProtocol`(`get(workshop_id) ->
Optional[tuple[str, int]]`・`set(workshop_id, month, count) -> None`)は、
`usage_counter/{workshop_id}`ドキュメント(month・count の2フィールド)への読み書きを
表すが、検証用の`InMemoryUsageCounterStore`スタブのみが存在し、実Firestore接続の具象
実装はまだない。本ドキュメントは、firestore-provider-adapter-design.md(フェーズ209、
`UserProfileStoreProtocol`向け)に続き、残り3つのProtocol
(`WorkshopStoreProtocol`・`UsageCounterStoreProtocol`・`LinkingCodeStoreProtocol`)の
うち、対象ドキュメントが単一・メソッド数が最少(2件)の`UsageCounterStoreProtocol`を
対象に設計する。実Firestoreプロジェクトへの接続(GCPアカウント・課金設定を伴う)が
承認されるまでの間の先行設計であり、コード変更・外部アカウント作成のいずれも行わない。

## 2. 設計方針(素朴な実装)

```python
class FirestoreUsageCounterProvider:
    """UsageCounterStoreProtocolの実Firestore接続実装。
    usage_counter/{workshop_id}ドキュメント(month・count)を読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client

    def _doc_ref(self, workshop_id: str):
        return self._client.collection("usage_counter").document(workshop_id)

    def get(self, workshop_id: str) -> tuple[str, int] | None:
        snapshot = self._doc_ref(workshop_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        if "month" not in data or "count" not in data:
            return None
        return (data["month"], data["count"])

    def set(self, workshop_id: str, month: str, count: int) -> None:
        self._doc_ref(workshop_id).set({"month": month, "count": count})
```

`get_workshop_id`系と異なり、本ドキュメントは`month`・`count`の2フィールドが常に対で
意味を持つため、`set()`は`merge=True`を使わずドキュメント全体を置き換える(片方のみの
部分更新は呼び出し元〈`check_and_increment_usage`〉の使い方からも発生しない)。

## 3. 検討事項: 呼び出し元のread-modify-write競合(重要・未解消)

`usage_counter_workshop.py`の`check_and_increment_usage()`は、Protocolの`get`・`set`を
次の順序で**2回の別々の呼び出し**として使う(867〜875行目):

1. `existing = usage_counter_store.get(workshop_id)` で現在の`(month, count)`を読む
2. Pythonのローカル変数上で`count_after = count_before + 1`を計算する(月替わりならリセット)
3. `usage_counter_store.set(workshop_id, current_month, count_after)` で書き戻す

`InMemoryUsageCounterStore`はテスト内で同期的・単一スレッドに呼ばれるため問題にならないが、
実Firestore環境では本venture(LINE公式アカウント経由のchatbot)が同一workshop_idから
ほぼ同時刻に複数の生成リクエストを受け取るケース(例: 職人が連続して複数のメッセージを
送る、複数の職人が同一workshop〈複数職人プラン〉から並行して利用する)で、2つのリクエストが
ステップ1を両方とも`count_before=5`で読み終えた後にそれぞれ`count_after=6`を書き込むと、
本来`count=7`になるべき2回目の利用が記録されず、月間利用回数の集計が実際の利用より少なく
なる(従量課金の取り漏れ・上限判定の誤りにつながる)。これはline-reservation-ai・
course-set-pasha等の決済Webhookで繰り返し扱われてきた「イベント順序ガード」とは異なる種類の
競合(同一フィールドへの並行read-modify-write)であり、本ventureでは今回初めて具体化した
論点である。

対応方針としては、Firestoreの`@firestore.transactional`デコレータでステップ1〜3を
1つのトランザクション内に閉じ込め、読み取り→書き込みの間に他の書き込みが入らないことを
保証する実装が標準的だが、これには`UsageCounterStoreProtocol`自体の見直しが必要になる
(現状の`get`/`set`という2メソッド構成では、呼び出し元〈`check_and_increment_usage`〉が
Pythonレベルで両者の間に計算を挟む限り、アダプタ側だけでは競合を解消できない)。具体的には
次のいずれかが次回候補となる:

- (a) Protocolに`increment_or_reset(workshop_id, current_month) -> int`(月替わりなら
  リセットしてから加算し、加算後のcountを返す)という単一の原子的メソッドを追加し、
  `check_and_increment_usage()`を2メソッド呼び出しから1メソッド呼び出しに変更する。
  Firestore実装は`@firestore.transactional`で内部にトランザクションを隠蔽でき、
  `InMemoryUsageCounterStore`実装も戻り値の意味が変わるだけで引き続き素朴な実装で足りる。
- (b) 現状の`get`/`set`2メソッド構成を維持し、呼び出し元(`check_and_increment_usage`)に
  トランザクション境界を持たせる(Firestoreクライアント自体を関数に渡す必要が生じ、
  Protocol越しの抽象化が崩れるため非推奨)。

(a)が既存の依存注入構造(Protocol経由でテスト用スタブと実装を差し替える設計)を保ったまま
解消できるため望ましいと考えられるが、`check_and_increment_usage()`のシグネチャ変更・
既存テスト(test_usage_counter_workshop.py)への影響が生じるため、本フェーズでは設計の
方向性を記録するのみとし、実際のProtocol変更・コード変更は次回候補として見送る。

## 4. 残課題・次回候補

- 上記3節(a)案(`increment_or_reset`への統合)の具体的なシグネチャ・既存テストへの
  影響整理、および`test_usage_counter_workshop.py`の改修方針の設計。
- 残り2つのProtocol(`WorkshopStoreProtocol`・`LinkingCodeStoreProtocol`)の実Firestore
  接続アダプタ設計。
- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちで
  あり、本設計のコードは承認後の結合実装フェーズまでコミットしない。
- 本フェーズで発見した競合リスクは、他venture(line-reservation-ai・course-set-pasha・
  aircon-pasha・forklift-pasha)の同種カウンタ系Protocol(存在する場合)にも横展開確認
  する余地がある。
