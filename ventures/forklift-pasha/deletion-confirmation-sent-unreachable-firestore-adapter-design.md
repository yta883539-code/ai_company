# FleetOperatorStoreProtocolの実Firestore接続アダプタ設計(フェーズ164・削除候補系グループ)

## 1. 背景

fleet-operator-store-firestore-adapter-design.md(フェーズ160)「4. 未検証・残課題」、
および fleet-operator-store-upgraded-canceled-firestore-adapter-design.md(フェーズ162)
「3. 未検証・残課題」に残っていた最後のグループ、`deletion_confirmation_sent_at`・
`deletion_confirmation_unreachable_at`・`deletion_confirmation_unreachable_reason`の
3フィールド(計6メソッド、便宜上「削除候補系グループ」と呼ぶ)に着手する。これで
`FleetOperatorStoreProtocol`の全メソッドの実Firestore接続アダプタ設計が完了する。

ドキュメント構造はフェーズ160・161・162と同じ`fleet_operator/{internal_id}`
(firestore-data-model.md)。対応フィールドは`deletionConfirmationSentAt`
(Timestamp | null)・`deletionConfirmationUnreachableAt`(Timestamp | null)・
`deletionConfirmationUnreachableReason`(string | null)の3つ(firestore-data-model.md
78-83行)。

## 2. 各メソッドの実装方針

### 2.1 `deletion_confirmation_sent_at`(2メソッド)

`get_deletion_confirmation_sent_at`/`set_deletion_confirmation_sent_at`は
`deletionConfirmationSentAt`フィールドへの単純なget/update。
`InMemoryFleetOperatorStore.set_deletion_confirmation_sent_at()`
(trial_management.py:232-233)は常に値(非`None`)を書き込むだけで上書き制約を持たない
(送信試行のたびに最新の送信日時へ更新してよい)。唯一の呼び出し元
`send_deletion_candidate_final_confirmations()`(deletion_candidate.py:108)は
メール送達に成功した場合にのみ本メソッドを呼ぶため、`trialStartAt`のような
「既に設定済みなら上書きしない」規約は不要。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"deletionConfirmationSentAt": value})
```

### 2.2 `deletion_confirmation_unreachable_at`(2メソッド)

`get_deletion_confirmation_unreachable_at`/`set_deletion_confirmation_unreachable_at`も
同様に`deletionConfirmationUnreachableAt`フィールドへの単純なget/update。呼び出し元
(deletion_candidate.py:111)はメール送達失敗時(`email is None`を含む)にのみ呼ばれ、
`sent_at`と`unreachable_at`は同じ呼び出しの中で排他的に一方だけが設定される
(deletion_candidate.py:102-117の分岐)ため、Firestore側で両フィールドの整合性を保つ
特別な制御(トランザクション等)は不要。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"deletionConfirmationUnreachableAt": value})
```

フェーズ163(deletion-candidate-query-consolidation-decision.md)の決定により、
本venture固有の方針として連絡不能候補は自然復帰イベント(LINEの「ブロック→再フォロー」に
相当するもの)を持たず、本フィールドを`None`に戻す(クリアする)経路は本番コードに
存在しない。したがってaircon-pashaフェーズ321の`clear_deletion_confirmation_unreachable_at()`
相当のメソッド・Firestoreアダプタは本ventureには不要(フェーズ163で既に確認済みの結論を
本フェーズでも踏襲する)。

### 2.3 `deletion_confirmation_unreachable_reason`(2メソッド)

`get_deletion_confirmation_unreachable_reason`/
`set_deletion_confirmation_unreachable_reason`は`deletionConfirmationUnreachableReason`
フィールドへのget/update。`InMemoryFleetOperatorStore.
set_deletion_confirmation_unreachable_reason()`(trial_management.py:246-252)は
`value`が`None`の場合に辞書からキーを削除する分岐を持つが、本番コードの唯一の呼び出し元
(deletion_candidate.py:117、`send_deletion_candidate_final_confirmations()`内の
送達失敗分岐)は常に`UNREACHABLE_REASON_NO_EMAIL`/`UNREACHABLE_REASON_SEND_FAILED`の
いずれかの非`None`値を渡し、`None`を渡す呼び出しは2.2節で述べた通りクリア経路が
本ventureに存在しないため実際には発生しない(テスト・リセット用途のみ)。

フェーズ162 2.2節(`canceled_at`)で下した判断と同じ理由により、`None`書き込みの
挙動を設計する必要はあるが実運用では到達しないパスであることを明記した上で、
一貫性のため同じ**`null`書き込み案**(`DELETE_FIELD`は使わない)を採用する。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"deletionConfirmationUnreachableReason": value})
```

`get_deletion_confirmation_unreachable_reason`は`doc.get("deletionConfirmationUnreachableReason")`
が未設定時・`null`時いずれも`None`相当を返すため、InMemory版の「キーが無ければ`None`」と
同じ挙動になる。

## 3. まとめ: `FleetOperatorStoreProtocol`全メソッドの設計完了

フェーズ160(基盤グループ: email・plan_id・stripe_customer_id・逆引き・trial_start_at)、
161(トライアル終了判定グループ)、162(解約/昇格グループ)、本フェーズ164(削除候補系
グループ)により、`FleetOperatorStoreProtocol`が持つ全メソッドの実Firestore接続アダプタ
机上設計が完了した。いずれも「単純なフィールドupdate」「`firestore.Increment()`による
アトミック加算」「呼び出し順序の規約による排他制御」「`null`書き込みによる論理削除」の
4パターンのいずれかに分類できることを確認した。

## 4. 未検証・残課題

- 実`google-cloud-firestore`ライブラリの導入・`FORKLIFT_PASHA_FIRESTORE_ENABLED`フラグに
  よる実コード化(runtime-dependency-switching-design.md 2節)は、承認後の結合実装フェーズに
  持ち越す(本フェーズもコード変更を行わない机上設計のみ)。
- 全メソッドの机上設計が完了したため、次回候補は(a)承認待ち事項の承認後の結合実装着手、
  または(b)他venture(course-set-pasha等、firestore-composite-index-plan.md自体の新設を
  含む横展開)・アイデア領域の前進のいずれかに移る。

最終更新: 2026-10-17 07:00 UTC(フェーズ164)
