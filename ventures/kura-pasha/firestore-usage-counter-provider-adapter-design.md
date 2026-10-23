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

**フェーズ212で実装済み。** `UsageCounterStoreProtocol`へ`increment_or_reset(workshop_id,
current_month) -> int`を追加し、`check_and_increment_usage()`を本メソッド1回の呼び出しに
変更した(`usage_counter_workshop.py`841〜880行目付近)。`InMemoryUsageCounterStore`にも
素朴な実装(保存済みmonthがcurrent_monthと不一致ならcount=0から、一致すれば現在のcountから
+1し、結果を書き込んで返す)を追加した。既存の`get`/`set`は、テスト側が生成リクエスト
ブロック時に「usage_counter_storeへ何も書き込まれていないこと」を検証する用途
(`counters.get(workshop_id) is None`)で引き続き使うため、Protocolから削除していない。
`test_usage_counter_workshop.py`に`increment_or_reset`単体の積み上げ・月替わりリセット
挙動を検証する2件を追加した(`test_increment_or_reset_accumulates_within_same_month`・
`test_increment_or_reset_resets_on_month_change`)。既存テスト(16ファイル)・schema検証
(32件)いずれも回帰なしでパスすることを確認した。

上記`## 2. 設計方針`のFirestore実装例(素朴な`get`/`set`のみ)は、実際にFirestore接続を
行う際には`increment_or_reset`を`@firestore.transactional`で実装する必要がある点を
明記しておく(`get`/`set`はテスト向けの状態検証用途にのみ残す非原子的メソッドとし、
生成リクエスト処理の本流では`increment_or_reset`のみを使う)。

## 4. 残課題・次回候補

- 残り2つのProtocol(`WorkshopStoreProtocol`・`LinkingCodeStoreProtocol`)の実Firestore
  接続アダプタ設計。
- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちで
  あり、本設計のコードは承認後の結合実装フェーズまでコミットしない(`increment_or_reset`の
  `@firestore.transactional`実装自体もこの結合実装フェーズで行う)。
  【フェーズ261追記】上記「pending-approval.md記載」は、本venture固有の独立した
  エントリが実際には一度も記録されていなかった記載漏れであったことが判明(2026-10-23
  19:00 UTCに新規記録・是正済み、詳細はfirestore-provider-adapter-design.md 4節参照)。
- 本フェーズ(211)で発見した競合リスク・フェーズ212の`increment_or_reset`統合は、
  他venture(line-reservation-ai・course-set-pasha・aircon-pasha・forklift-pasha)の
  同種カウンタ系Protocol(存在する場合)にも横展開確認する余地がある。

## 5. フェーズ226横断レビュー: 接続エラー時のフォールバック方針の確定

workshop-store-firestore-adapter-design.md 23節(フェーズ225)で確定した本venture全体の
統一方針(`.get()`自体の例外はtry/exceptで捕捉し既存の「未設定」デフォルト値に合流させる
〈fail-open〉。値が認可・決済ゲートの判定に直接使われ、デフォルト値が「拒否」を意味する
場合のみfail-closed)を、本ドキュメントを含む4つの設計ドキュメント(firestore-provider-
adapter-design.md・本ドキュメント・linking-code-store-firestore-adapter-design.md・
invite-code-store-firestore-adapter-design.md)に横断的に当てはめて見直した結果、本
ドキュメントの`increment_or_reset`についてのみ方針が未確定(`## 2.`の実装例は`get`/`set`の
素朴な実装のみで、本流の`increment_or_reset`自体のFirestore実装例・エラー時の挙動が
示されていなかった)であることが判明した。残り3ドキュメントは以下の理由により確定済みの
方針と矛盾しないことを確認した(変更不要)。

- **firestore-provider-adapter-design.md**: `get_workshop_id`・`get_is_following`は
  いずれも`_get_doc()`内でtry/exceptにより例外を捕捉し、`InMemoryUserProfileStore`と
  同じ既定値(`None`・`True`)にフォールバックしている。`get_workshop_id`・
  `get_is_following`のいずれも「契約者本人確認」や「プラン決定」のような認可・決済ゲートの
  判定に直接使われるものではなく(workshop_id未設定は新規契約フロー未完了として別経路で
  扱われ、is_following=Trueはフォロー解除時の請求停止判定の入力の一つに過ぎず単独で
  決済可否を決めるものではない)、fail-open判定は23節の基準と整合する。
- **linking-code-store-firestore-adapter-design.md / invite-code-store-firestore-
  adapter-design.md**: `get()`はtry/exceptで例外を捕捉し「未発見」(`None`)に
  フォールバックしており(連携・招待コードの無効化と同じ扱いになる安全側の選択)、23節の
  fail-open方針と整合する。`save`/`delete`/`items`はいずれも例外を捕捉せず伝播させる設計
  だが、これは書き込み系メソッド(ドキュメントへの`set`/`delete`、`WorkshopStoreProtocol`の
  各`set_*`系も同様に例外を捕捉していない)に共通する意図的な設計であり、23節が対象とした
  「`.get()`自体の例外」(読み取り系)の範囲外であるため矛盾ではない。書き込みが失敗した場合に
  静かに成功したものとして処理を続けるとデータ不整合(例: 連携コードが実際には保存されていない
  のに発行成功として案内してしまう)を招くため、書き込み系は常に例外を呼び出し元に伝播させ、
  呼び出し元(Cloud Functions のエラーハンドリング・Webhookの再試行)に委ねる方針で一貫して
  いることを本節で明文化する。

これに対し`increment_or_reset`は、`check_and_increment_usage()`内で`within_limit`
(従量課金要否)の判定に直接使われるが、認可・決済ゲートというよりは「今回の利用1回分を
カウントできるか」という計測目的のメソッドであり、23節が「拒否をデフォルトに持つ認可判定」
のみをfail-closed対象とした趣旨からは外れる。また、`get_contractor_user_id`・`get_plan_id`
(23節でfail-closedと確定した2メソッド)がいずれも「値を取得できないこと自体が不正・
不整合の兆候であり処理を止めるべき」ケースであるのに対し、Firestoreの接続エラー・
トランザクション競合(最大試行回数超過)は本venture側のデータ不整合ではなく一時的な基盤側の
問題であるため、fail-openとして扱う方が23節の趣旨(一時的エラーで職人がサービスを使えなく
なる事故を避ける)に合致する。以上により、`increment_or_reset`の実Firestore実装は
**fail-open(接続エラー時は当月の集計を1件分取り漏らす代わりに生成を許可する)**と確定する。

```python
class FirestoreUsageCounterProvider:
    """UsageCounterStoreProtocolの実Firestore接続実装(フェーズ226版)。
    usage_counter/{workshop_id}ドキュメント(month・count)を読み書きする。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client

    def _doc_ref(self, workshop_id: str):
        return self._client.collection("usage_counter").document(workshop_id)

    def get(self, workshop_id: str) -> tuple[str, int] | None:
        # テスト向けの状態検証用途にのみ残す非原子的メソッド。本流では使わない。
        snapshot = self._doc_ref(workshop_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        if "month" not in data or "count" not in data:
            return None
        return (data["month"], data["count"])

    def set(self, workshop_id: str, month: str, count: int) -> None:
        # テスト向けの状態検証用途にのみ残す非原子的メソッド。本流では使わない。
        self._doc_ref(workshop_id).set({"month": month, "count": count})

    def increment_or_reset(self, workshop_id: str, current_month: str) -> int:
        """check_and_increment_usage()本流で使う原子的メソッド。

        読み取り→月替わり判定→加算→書き込みを1つのFirestoreトランザクションに
        閉じ込め、並行リクエストによるread-modify-write競合(3節)を防ぐ。
        トランザクション自体が失敗した場合(接続エラー・最大試行回数超過等)は
        fail-open方針(本節)に従い、当月初回利用として1を返す(取り漏れは許容し、
        生成リクエストを止めない)。
        """
        transaction = self._client.transaction()

        @firestore.transactional
        def _run(transaction):
            doc_ref = self._doc_ref(workshop_id)
            snapshot = doc_ref.get(transaction=transaction)
            data = snapshot.to_dict() if snapshot.exists else None
            if data is None or data.get("month") != current_month:
                count_after = 1
            else:
                count_after = data.get("count", 0) + 1
            transaction.set(
                doc_ref, {"month": current_month, "count": count_after}
            )
            return count_after

        try:
            return _run(transaction)
        except Exception:
            return 1
```

- **既存InMemory実装との整合**: `InMemoryUsageCounterStore.increment_or_reset`
  (usage_counter_workshop.py)は例外を発生させない実装のため、本フォールバックは実
  Firestore接続時のみ発生する経路であり、既存テストへの影響はない(コード変更なし、
  テスト16ファイル・schema検証32件いずれも変更なしで再実行しパスを確認)。
- **残課題**: 取り漏れが実際にどの程度発生し得るか(トランザクション競合の再試行回数・
  タイムアウト設定次第)は結合実装フェーズでの計測が必要。取り漏れ件数が無視できない規模に
  なった場合は、月次の従量課金確定処理(存在する場合)側でCloud Loggingのエラーログと
  突合せる補正運用を検討する(本フェーズでは設計のみ記録し、実装は次回候補とする)。
