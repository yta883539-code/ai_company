# FleetOperatorStoreProtocolの実Firestore接続アダプタ設計(フェーズ161・トライアル終了判定グループ)

## 1. 背景

fleet-operator-store-firestore-adapter-design.md(フェーズ160)「4. 未検証・残課題」に残って
いた次回候補の先頭グループ、`get_trial_generation_count`/`increment_trial_generation_count`/
`get_trial_end_notified_at`/`set_trial_end_notified_at`の4メソッド(トライアル終了判定系)に
着手する。この4メソッドはいずれも`trial-end-condition-design.md`・`trial-end-notification-
design.md`で定義された「生成5回到達、または初回生成から30日のいずれか早い方で1回だけ通知」の
判定ロジック(`is_trial_period_over`/`should_notify_trial_end`、trial_management.py)が参照・
更新する2フィールド(`trialGenerationCount`・`trialEndNotifiedAt`)に対応する。ドキュメント
構造はフェーズ160と同じ`fleet_operator/{internal_id}`(firestore-data-model.md)。

## 2. `trial_generation_count`: 単純なupdateではなくFirestoreのAtomic Increment

`InMemoryFleetOperatorStore.increment_trial_generation_count()`はメモリ上の辞書を
`before = count; after = before + 1; count = after`という読み取り→計算→書き込みの3手順で
実装しているが、Firestoreアダプタでこれをそのまま「読み取り→加算→`update()`」で素朴に
実装すると、同一`internal_id`に対する同時呼び出し(例: 同じ事業者が別タブで連続生成した場合)
で片方の加算が失われるLost Update問題が起こり得る。

Firestoreは`firestore.Increment(1)`というサーバー側アトミック演算をフィールド値として
`update()`に渡すことができ、これを使えば読み取りを介さずにサーバー側で安全に1加算できる。

```python
from google.cloud import firestore

doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"trialGenerationCount": firestore.Increment(1)})
```

### 2.1. 戻り値`(before, after)`の扱い

`increment_trial_generation_count()`のシグネチャは`tuple[int, int]`(加算前・加算後の値)を
返す契約だが、`firestore.Increment()`を使った`update()`の戻り値(`WriteResult`)は
`update_time`のみを持ちフィールドの実値を含まないため、このままでは`(before, after)`を
返せない。呼び出し元を確認したところ、本番コードの唯一の呼び出し元
`record_generation_for_trial()`(trial_management.py:279)は戻り値を破棄しており、
テスト(trial_end_email_scheduler.pyのdocstring例)以外に実際に`(before, after)`を消費する
呼び出し元は現時点で存在しない。そのため本フェーズでは、

- 書き込みは`firestore.Increment(1)`によるアトミック加算を正とする(Lost Updateを避ける)。
- `(before, after)`は加算の前後で`get_trial_generation_count()`相当の読み取りを挟む
  素朴な実装で近似するに留め、戻り値の`before`/`after`はアトミック書き込みと
  厳密には同期しない(2つの読み取りの間に他の呼び出しが割り込めば値がずれ得る)ことを
  既知の制約として残す。

この近似で問題にならない理由は、現在の唯一の呼び出し元が戻り値を使っていないため、
不整合が実害を生むパスが存在しないこと。将来`(before, after)`を実際に消費する呼び出し元
(例: 「ちょうど上限に達した瞬間」をこの戻り値で検出するような設計変更)が追加される場合は、
`run_transaction`でget→加算値計算→`update()`(Incrementではなく計算済みの値を直接書く)を
1トランザクションにまとめ、`(before, after)`を厳密に同期させる実装に切り替える必要がある
(この場合はアトミック性をIncrementではなくトランザクションの楽観的ロックで担保する形になる)。

## 3. `trial_end_notified_at`: フェーズ160 3.4節と同じ「呼び出し順序の規約」方式

`get_trial_end_notified_at`/`set_trial_end_notified_at`は`trialEndNotifiedAt`フィールド
(Firestore Timestamp)への単純なget/updateだが、`InMemoryFleetOperatorStore.
set_trial_end_notified_at()`は`trialStartAt`と同じ「既に設定済みの場合は上書きしない」
制約を持つ(trial-end-notification-design.md「いずれか早い方で1回のみ送信」を担保するため、
二重送信防止の要)。

フェーズ160 3.4節で`trialStartAt`について下した判断(呼び出し元が事前に`get_*()`で未設定を
確認してから`set_*()`を呼ぶ「呼び出し順序の規約」方式(a)を採用し、トランザクション方式(b)は
結合実装フェーズの実トラフィックパターンを見てから再検討)を、本フィールドにも同じ理由で
適用する。実際、本番コードの唯一の呼び出し経路`should_notify_trial_end()`→
`record_generation_and_get_trial_end_notice()`(trial_management.py:318-320)は、まさに
`get_trial_end_notified_at()`で未設定を確認した直後にのみ`set_trial_end_notified_at()`を
呼ぶ構造になっており、規約(a)は既存コードの呼び出し順序とそのまま一致する。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"trialEndNotifiedAt": value})
```

ただし`trialStartAt`との違いとして、`trialEndNotifiedAt`は(A)経路(生成完了時の返却テキスト
追記、Webフォーム処理の中で同期的に発生)と(B)経路(日次スケジューラ)の2つの独立した経路から
呼ばれ得る(trial-end-notification-design.md 2節)。この2経路が同一`internal_id`に対して
ほぼ同時に実行されるタイミング(生成5回到達と期間到達が同日に重なる、かつ日次スケジューラの
実行時刻と重なる)は極めて稀だが理論上は排除できないため、フェーズ160の判断をそのまま
適用しつつ、この2経路間の競合は4節の残課題として明記する。

## 4. 未検証・残課題

- 2.1節: `increment_trial_generation_count()`の戻り値`(before, after)`を将来実際に消費する
  呼び出し元が追加された場合、トランザクションベースの実装への切り替えが必要(次回候補)。
- 3節: (A)経路・(B)経路が同一`internal_id`に対してほぼ同時実行された場合の競合
  (稀だが理論上排除できない)は、規約(a)の下では完全には防げない。結合実装フェーズで
  実際に(B)経路(日次スケジューラ)の配線が入った時点で再検討する。
- 残りのグループ(`upgraded_at`、`canceled_at`、`deletion_confirmation_sent_at`+
  `unreachable_at`+`unreachable_reason`、`all_internal_ids`)の実Firestore接続アダプタ設計。
  次回候補として残す。
- 実`google-cloud-firestore`ライブラリの導入・`FORKLIFT_PASHA_FIRESTORE_ENABLED`フラグに
  よる実コード化(runtime-dependency-switching-design.md 2節)は、承認後の結合実装フェーズに
  持ち越す(本フェーズはコード変更を行わない机上設計のみ)。

最終更新: 2026-10-16 19:00 UTC(フェーズ161)
