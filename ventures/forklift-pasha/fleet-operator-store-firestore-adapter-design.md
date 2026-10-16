# FleetOperatorStoreProtocolの実Firestore接続アダプタ設計(フェーズ160・基盤グループ)

## 1. 背景

access-token-store-firestore-adapter-design.md(フェーズ159)「3. 未検証・残課題」に残っていた
次回候補(2)「`FleetOperatorStoreProtocol`自体の実Firestore接続アダプタの設計」に着手する。

`FleetOperatorStoreProtocol`(`prototype/trial_management.py`)は本venture最大のProtocolで、
15メソッドを持つ(trial系4・upgraded_at系2・plan_id系2・email系2・stripe_customer_id順引き
2+逆引き1・canceled_at系2・deletion_confirmation系6)。kura-pasha/workshop-store-firestore-
adapter-design.mdが`WorkshopStoreProtocol`(30件超)に対して採った「一度に全メソッドを設計すると
検討事項が発散するため、関連性の高い最小グループから着手する」方針を踏襲し、本フェーズは
以下の**基盤グループ**(事業者の新規登録〜初回利用時に書き込まれるフィールド、計9メソッド)
に限定する。

- `get_email`/`set_email`: Webフォーム送信時に取得するメールアドレス。
- `get_plan_id`/`set_plan_id`: 契約プラン(ライト/スタンダード/複数台)。
- `get_stripe_customer_id`/`set_stripe_customer_id`/`get_internal_id_by_stripe_customer_id`:
  Checkout Session完了時に発行されるStripe Customer IDの順引き・逆引き。
- `get_trial_start_at`/`set_trial_start_at`: 無料トライアルの起算点(初回生成時に1回だけ設定)。

残りのグループ(`trial_generation_count`+`trial_end_notified_at`のトライアル終了判定系2、
`upgraded_at`、`canceled_at`、`deletion_confirmation_sent_at`+`unreachable_at`+
`unreachable_reason`の削除候補系3、`all_internal_ids`)は、それぞれ別の関心事(生成回数カウント、
解約、削除候補)に閉じているため、次回候補として個別に残す(4節)。

## 2. 前提: ドキュメント構造

firestore-data-model.md「1. `fleet_operator/{internal_id}`」の通り、`fleet_operator`は
ルートコレクションで`internal_id`をドキュメントIDとする1ドキュメント1事業者の構造。
`AccessTokenStoreProtocol`(フェーズ159)・`VehicleCountStoreProtocol`
(overage_notifications.py)も同じ`fleet_operator/{internal_id}`ドキュメントの別フィールド
(`accessToken`/`lastAccessedAt`、`vehicleCount`)を分担するが、access-token-store-
firestore-adapter-design.mdの方針(「本venture は元々複数Protocolに分かれているため、
Firestore化のタイミングで統合する必然性はない」)を本グループにも適用し、
`FleetOperatorStoreProtocol`専用のFirestoreアダプタ(`FirestoreFleetOperatorStore`)として
独立させる。

## 3. 各メソッドの実装方針

### 3.1. `get_email`/`set_email`、`get_plan_id`/`set_plan_id`

`fleet_operator/{internal_id}`ドキュメントの`email`/`planId`フィールドへの単純なget/update。
いずれも上書き可(`InMemoryFleetOperatorStore`と同じ、「初回のみ」の制約は持たない)。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"email": value})  # set_plan_idは{"planId": value}
```

### 3.2. `get_stripe_customer_id`/`set_stripe_customer_id`

`stripeCustomerId`フィールドへの単純なget/update。`InMemoryFleetOperatorStore.
set_stripe_customer_id()`は旧IDの逆引きエントリ(`_internal_ids_by_stripe_customer_id`)を
明示的に削除してから新IDを登録する実装だが、access-token-store-firestore-adapter-design.md
2.3節と同じ理由(Firestoreはライブクエリのため、`stripeCustomerId`フィールドが新IDで
上書きされた瞬間に旧IDでの照会は自動的に0件になる)により、Firestore版では逆引き専用の
インデックス構造を自前で保持・清掃する処理が不要になる。

### 3.3. `get_internal_id_by_stripe_customer_id`(逆引き)

`stripeCustomerId`フィールドへの単一フィールドクエリで実現する。Firestoreは単一フィールドに
自動でインデックスを作成するため、追加の複合インデックス設定は不要(firestore-composite-
index-plan.mdの既存2件(#1 vehicleLabel重複判定・#2 trial-end日次スケジューラ)に変更なし)。

```python
query = (
    self._client.collection("fleet_operator")
    .where("stripeCustomerId", "==", stripe_customer_id)
    .limit(1)
)
docs = list(query.stream())
return docs[0].id if docs else None
```

### 3.4. `get_trial_start_at`/`set_trial_start_at`

`trialStartAt`フィールド(Firestore Timestamp)への単純なget/update。`InMemoryFleetOperatorStore.
set_trial_start_at()`は「既に設定済みの場合は上書きしない」制約(firestore-data-model.mdの
設計通り、初回生成時に1回だけ設定・以降不変)を持つが、この制約はFirestoreアダプタ側では
素朴な`update()`では再現できないため、以下のいずれかが必要になる。

- (a) `set_trial_start_at()`呼び出し前に呼び出し側(`trial_management.py`の生成フロー)が
  `get_trial_start_at()`で既存値の有無を確認してから呼ぶ(呼び出し順序の規約として徹底)。
- (b) アダプタ内部でトランザクション(`run_transaction`)を使い、読み取り→未設定の場合のみ
  書き込みをアトミックに行う。

本フェーズでは(a)を採用する方針を仮決めする。本venture の生成フロー(`cloud_function_
send_trial_end_emails.py`等)は低頻度(事業者1人あたり月数回程度)のバッチ処理であり、
同一事業者に対する`set_trial_start_at()`の同時呼び出し(競合)が発生する実用上のシナリオが
想定しにくいため、(b)のトランザクション導入は時期尚早な最適化と判断した。ただし、
同時再発行を同様の理由で素朴な`update()`に委ねたaccess-token-store-firestore-adapter-
design.md「3. 未検証・残課題」の判断とは異なり、本フィールドは「以降不変」という不変条件
自体の正しさに関わるため、結合実装フェーズで実際のトラフィックパターンが見えた時点で
(b)への切り替えを再検討する前提を明記する(4節に残す)。

## 4. 未検証・残課題

- 残りのグループ(`trial_generation_count`+`trial_end_notified_at`、`upgraded_at`、
  `canceled_at`、`deletion_confirmation_sent_at`+`unreachable_at`+`unreachable_reason`、
  `all_internal_ids`)の実Firestore接続アダプタ設計。次回候補として残す。
- 3.4節で仮決めした「呼び出し順序の規約(a)」が、結合実装フェーズで実際に成立するかの
  検証(特に`trial_management.py`の生成フロー以外から`set_trial_start_at()`が呼ばれる
  経路が将来追加された場合、規約の徹底が難しくなる可能性がある)。
- 実`google-cloud-firestore`ライブラリの導入・`FORKLIFT_PASHA_FIRESTORE_ENABLED`フラグに
  よる実コード化(runtime-dependency-switching-design.md 2節)は、承認後の結合実装フェーズに
  持ち越す(本フェーズはコード変更を行わない机上設計のみ)。

最終更新: 2026-10-16 17:00 UTC(フェーズ160)
