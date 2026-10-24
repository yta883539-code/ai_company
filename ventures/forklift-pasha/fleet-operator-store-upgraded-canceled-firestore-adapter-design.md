# FleetOperatorStoreProtocolの実Firestore接続アダプタ設計(フェーズ162・解約/昇格グループ)

## 1. 背景

fleet-operator-store-firestore-adapter-design.md(フェーズ160)「次回候補(2)」に残っていた
残りのグループのうち、本フェーズは`upgraded_at`・`canceled_at`・`all_internal_ids`の計3メソッド
(便宜上「解約/昇格グループ」と呼ぶ)に着手する。`trial_generation_count`+`trial_end_notified_at`
(フェーズ161で設計済み)、`deletion_confirmation`系3メソッドは関心事(削除候補処理)が異なるため
対象外とし、次回候補として残す(4節)。

## 2. 各メソッドの実装方針

### 2.1 `upgraded_at`(2メソッド)

`get_upgraded_at`/`set_upgraded_at`は`upgradedAt`フィールド(Firestore Timestamp | null)への
単純なget/update。`InMemoryFleetOperatorStore.set_upgraded_at()`(trial_management.py:187-188)は
上書き可(プラン変更のたびに何度でも書き換えてよい、aircon-pasha/user_id_linking.pyの
`set_upgraded_at()`と同じ方針、trial_start_atのような「初回のみ」制約を持たない)であり、
フェーズ160 3.4節で検討した「呼び出し順序の規約」のような排他制御は不要。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"upgradedAt": value})
```

単純なフィールド更新のみのため、トランザクション化やIncrement等の特別な考慮は不要。

### 2.2 `canceled_at`(2メソッド)

`get_canceled_at`/`set_canceled_at`は`canceledAt`フィールドへのget/update。
`InMemoryFleetOperatorStore.set_canceled_at()`(trial_management.py:220-224)は
`value`が`None`の場合に辞書からキーを削除する(再契約時に解約状態を解除する経路、
stripe_webhook.pyの`customer.subscription.updated`でステータスが`active`に戻った場合に
呼ばれる)。Firestoreでは`None`書き込みと「フィールド自体を消す」は意味が異なるため、
InMemory版の「キー削除=未解約扱いに戻す」をFirestoreでも同じ意味で再現するには、

```python
if value is None:
    doc_ref.update({"canceledAt": firestore.DELETE_FIELD})
else:
    doc_ref.update({"canceledAt": value})
```

のように`DELETE_FIELD`センチネルを使う案と、単に`null`を書き込む案の2つが考えられる。
`get_canceled_at`の読み取り側はいずれの場合も「フィールドが存在しない」「値が`None`」を
区別せず`None`として返せばよい(`doc.get("canceledAt")`は未設定時も`None`相当を返す)ため、
本フェーズでは実装を単純化し、**`null`書き込み案**(`DELETE_FIELD`は使わない)を採用する。
理由: `DELETE_FIELD`はフィールドそのものを消すため、firestore-data-model.md記載のドキュメント
スキーマ(フィールドの存在自体を仕様として明記)との整合性を保ちやすいのは「常に`canceledAt`
フィールドが存在し、値が`Timestamp`か`null`かのいずれか」という単純化された方である。

### 2.3 `all_internal_ids`(1メソッド)

`InMemoryFleetOperatorStore.all_internal_ids()`(trial_management.py:226-227)は保持する
全事業者の`internal_id`一覧を返す。用途はcloud_function_send_trial_end_emails.py・
cloud_function_send_deletion_confirmations.pyの日次バッチが全事業者を走査する起点であり、
実運用での呼び出し頻度は低い(日次1回)がコレクション全件スキャンになる。

```python
return [doc.id for doc in self._client.collection("fleet_operator").stream()]
```

事業者数が増えた場合の全件スキャンコストはkura-pasha/workshop-store-firestore-adapter-design.md
が`all_workshop_ids()`相当のメソッドで既に検討済みの論点と同型であり、本フェーズでは同じ結論
(現在の想定事業者数規模では全件スキャンで十分、ページネーションは次回以降の規模拡大時に再検討)
を踏襲する。

## 3. 未検証・残課題

- 2.2節: `canceled_at`の`null`書き込み案は、将来「解約履行日時の履歴を複数保持したい」等の
  要件が追加された場合は再設計が必要(現状は単一フィールドでの「現在解約中かどうか」のみを
  表現する設計のため)。
- 残りのグループ(`deletion_confirmation_sent_at`+`unreachable_at`+`unreachable_reason`の
  削除候補系3メソッド)の実Firestore接続アダプタ設計。次回候補として残す。
- 実`google-cloud-firestore`ライブラリの導入・`FORKLIFT_PASHA_FIRESTORE_ENABLED`フラグに
  よる実コード化(runtime-dependency-switching-design.md 2節)は、承認後の結合実装フェーズに
  持ち越す(本フェーズはコード変更を行わない机上設計のみ)。

最終更新: 2026-10-16 23:00 UTC(フェーズ162)

## フェーズ183追記(2026-10-24 00:00 UTC定例更新): 実コード化完了

本設計(2節)に基づき、`prototype/firestore_fleet_operator_adapter.py`の
`FirestoreFleetOperatorStore`に`get_upgraded_at`/`set_upgraded_at`・
`get_canceled_at`/`set_canceled_at`・`all_internal_ids`の計5メソッドを実コード化した
(README.mdフェーズ183参照)。2.2節で決定した`canceled_at`の`null`書き込み案も
そのまま実装した。テスト10件追加・schema検証11件いずれもパス。3節に残る削除候補系
3メソッド(`deletion_confirmation_sent_at`+`unreachable_at`+`unreachable_reason`)は
次回候補として残る。
