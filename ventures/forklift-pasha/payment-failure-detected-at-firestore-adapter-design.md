# FleetOperatorStoreProtocolの実Firestore接続アダプタ設計(フェーズ168・payment_failure_detected_atグループ)

## 1. 背景

fleet-operator-store-firestore-adapter-design.md(フェーズ160)・
fleet-operator-store-upgraded-canceled-firestore-adapter-design.md(フェーズ162)・
deletion-confirmation-sent-unreachable-firestore-adapter-design.md(フェーズ164)の
3ファイルにより「`FleetOperatorStoreProtocol`全メソッドの実Firestore接続アダプタ設計が
完了した」と確定していたが、その後フェーズ167(payment-failure-dunning-design.md)で
同Protocolに`get_payment_failure_detected_at`/`set_payment_failure_detected_at`の
2メソッド(`prototype/trial_management.py`)が新規追加されていた。本フェーズでは
aircon-pasha・line-reservation-ai側で過去に発生した「完了宣言後に追加されたフィールドが
データモデル文書・アダプタ設計に反映されないまま取り残される」という同種のギャップが
本ventureにも存在していないかを棚卸しし、本グループ(1フィールド・2メソッド)に
その欠落を発見したため、本フェーズで設計する。

ドキュメント構造はフェーズ160・162・164と同じ`fleet_operator/{internal_id}`
(firestore-data-model.md)。対応フィールドは`paymentFailureDetectedAt`
(Timestamp | null、firestore-data-model.md本フェーズで追記)。

## 2. 各メソッドの実装方針

`get_payment_failure_detected_at`/`set_payment_failure_detected_at`は
`paymentFailureDetectedAt`フィールドへの単純なget/update。

`prototype/payment_failure.py`の`mark_payment_failure_detected()`は
`invoice.payment_failed`受信のたびに(Stripeスマートリトライによる複数回の失敗連続通知を
含め)既存値を考慮せず最新の検知時刻で上書きする「安全側」の設計であり、
`set_trial_start_at_if_unset`相当の「既に設定済みなら上書きしない」制約は不要
(course-set-pasha 24.2節・aircon-pasha・kura-pashaの同フィールドと同じ結論)。

`clear_payment_failure_on_success()`(`invoice.payment_succeeded`受信時)は専用の
`clear_payment_failure_detected_at()`メソッドを持たず、`set_payment_failure_detected_at
(internal_id, None)`を直接呼ぶ設計になっている(payment_failure.py:66-70)。これは
course-set-pashaの`UsageCounterProtocol`(専用`clear_*`メソッドを持つ)とは異なる本venture
固有の実装選択だが、`InMemoryFleetOperatorStore.set_payment_failure_detected_at()`は
`value: Optional[datetime]`を受け取る契約のため`None`書き込みにも対応しており、Firestore
アダプタ側も同じ`set`メソッド1つで両方(検知・消去)をカバーできる。したがって本グループは
`get`/`set`の2メソッドのみで、deletion-confirmation系グループ(フェーズ164)のような
「clear用の専用メソッドの要否」の検討は不要である。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"paymentFailureDetectedAt": value})
```

`get_payment_failure_detected_at`は`doc.get("paymentFailureDetectedAt")`が未設定時・
`null`時いずれも`None`相当を返すため、`InMemoryFleetOperatorStore`の
「キーが無ければ`None`」と同じ挙動になる(deletion-confirmation系グループと同じ確認結果)。

## 3. 複合インデックスの要否

`is_payment_suspended()`(payment_failure.py)は呼び出し元が単一の`internal_id`に対して
呼ぶ設計であり、`paymentFailureDetectedAt`を条件とする複数事業者への横断クエリ(未送信の
リマインド対象者の一覧取得等)は、design 6節「残課題」の通りリマインド送信スケジューラ
自体が本venture未着手のため、本フェーズの対象外。スケジューラ新設時に改めて検討する
(フェーズ167の次回候補(2)と同じ)。

## 4. まとめ: `FleetOperatorStoreProtocol`全メソッドの設計完了(フェーズ164の訂正版)

本節により、フェーズ164が「完了」と誤って確定した後にコードへ追加された本グループ
(`payment_failure_detected_at`)を含め、`FleetOperatorStoreProtocol`が現時点で持つ
全メソッドの実Firestore接続アダプタ机上設計が揃った。

コード変更なし(文書新設・firestore-data-model.md修正のみ)。回帰確認として
`python3 prototype/run_all_tests.py`(全19ファイル、変更なし)・`python3 schema/
validate_test_cases.py`(11件、変更なし)を実行し、いずれも変更なしでパスすることを
確認した。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生
していないためpending-approval.mdへの追記なし。

## 5. 未検証・残課題

- 実`google-cloud-firestore`ライブラリの導入・`FORKLIFT_PASHA_FIRESTORE_ENABLED`フラグに
  よる実コード化は、承認後の結合実装フェーズに持ち越す(本フェーズもコード変更を行わない
  机上設計のみ)。
- 次回候補: (1)承認待ち事項がオーナーから承認された場合はその着手を最優先、
  (2)リマインド送信スケジューラ・運営者向け通知の設計(design 6節「残課題」、本venture側の
  日次スケジューラ自体の新設から必要)、(3)他venture(kura-pasha・course-set-pasha等)でも
  同種の「完了宣言後の追加フィールド反映漏れ」棚卸しを行う価値がある、(4)他venture・
  アイデア領域の前進。

最終更新: 2026-10-18 00:00 UTC(フェーズ168)
