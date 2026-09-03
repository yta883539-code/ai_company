# customer.subscription.deleted のroute_stripe_event()/receive_stripe_webhook()への配線設計

stripe-webhook-http-entry-point-design.md 7節「今後の課題」に残っていた
「`customer.subscription.updated`/`customer.subscription.deleted`
(`cloud_function_subscription_cancelled_webhook.py`)は`route_stripe_event()`が
扱う3種に含まれていないため、本エントリポイントの対象外のまま残る」という残課題のうち、
`customer.subscription.deleted`(契約の実終了)のみを今回対応する。

## 1. スコープを`customer.subscription.deleted`のみに絞った理由

`cloud_function_subscription_cancelled_webhook.py`は2種類のイベントを扱う設計になっている
(同モジュールdocstring参照)。

1. `customer.subscription.updated`(`cancel_at_period_end`の変化) →
   `handle_subscription_updated(state, cancel_at_period_end_before, cancel_at_period_end_after, push_client)`
2. `customer.subscription.deleted`(実際の契約終了) →
   `handle_subscription_deleted(state, push_client)`

(1)は`cancel_at_period_end_before`(直前の値)を呼び出し側が別途保持していないと
呼び出せない。Stripeの`customer.subscription.updated`イベント自体は
`data.object.cancel_at_period_end`(更新後の値)しか含まず、「直前の値」は
呼び出し側(Firestore等)に保存された前回状態と比較する必要がある。この「前回値の
保持・比較」の実装方針は本設計のスコープを超えるため、次回以降の課題として残す。

(2)`customer.subscription.deleted`は「直前の値」を必要とせず、受信した時点で
無条件に契約終了処理を行えばよい(`classify_subscription_deleted()`が見るのは
`state.suspension_reason`の現在値のみ)。route_stripe_event()の既存の
「customerから店舗を解決するだけの薄いルーティング」という設計とそのまま整合するため、
今回はこちらのみを対応する。

## 2. `route_stripe_event()`側の変更

`stripe_webhook.py`に`EVENT_CUSTOMER_SUBSCRIPTION_DELETED = "customer.subscription.deleted"`
を追加し、`_ROUTABLE_EVENT_TYPES`へ含める。ルーティングロジック自体の分岐追加は不要
(`EVENT_CHECKOUT_SESSION_COMPLETED`以外は全て`data.object.customer`から
`resolve_store_id_by_customer()`で解決する既存のelse分岐にそのまま乗る)。

## 3. `receive_stripe_webhook()`側の変更: 専用ストアが必要な理由

`checkout.session.completed`は既存の`subscription_store`
(`StoreSubscriptionStateStoreProtocol`、状態型は
`cloud_function_subscription_activated_webhook.StoreSubscriptionState`)を使って
`handle_subscription_activated()`を呼んでいる。この既存ストアをそのまま
`handle_subscription_deleted()`にも使い回せないか検討したが、以下の理由で
**専用の`cancellation_store`(新設)を追加する**設計とした。

`cloud_function_subscription_activated_webhook.py`と
`cloud_function_subscription_cancelled_webhook.py`は、docstring上は「同型」と
説明されているが、実際には同名(`StoreSubscriptionState`)の**別クラス**であり、
フィールド構成が異なる:

| フィールド | activated側 | cancelled側 |
|---|---|---|
| `store_id` / `owner_line_user_id` / `plan_name` / `portal_url` / `message_tone` / `suspension_reason` | ○ | ○ |
| `next_billing_date` | ○ | (無し) |
| `period_end_date` | (無し) | ○ |
| `blocked_but_billing_owner_notified_at` | (無し) | ○ |

`handle_subscription_deleted()`は`state.blocked_but_billing_owner_notified_at`を
参照する(blocked-but-billing-owner-email-notification-design.md 5節のクリア配線)。
activated側の`StoreSubscriptionState`インスタンスをそのまま渡すと
このフィールドが存在せず`AttributeError`になる。両クラスを無理に統合すると
`next_billing_date`↔`period_end_date`という意味の異なるフィールド名の扱い
(統合するなら値の意味を確認した上でどちらかへ寄せる必要があり、
activated側の呼び出し元・既存テスト群への影響範囲確認が必要)が発生し、
本設計のスコープを超えて既存の安定した経路(`checkout.session.completed`の
アクティベーション処理)を壊すリスクがある。

そのため、`dunning_store`/`subscription_store`が既に別Protocolとして分離されている
本ファイルの既存方針をそのまま踏襲し、`cancellation_store`
(`StoreCancellationStateStoreProtocol`、状態型は
`cloud_function_subscription_cancelled_webhook.StoreSubscriptionState`)を
**新設の第3のストア**として追加する。Firestore実装時にも、活性化直後の
`suspension_reason`初期化(activated側)と契約終了時の書き戻し(cancelled側)を
同一ドキュメントの異なるフィールド射影として扱うか統合するかは、実Firestore接続後の
設計課題として改めて検討する(次回以降の課題)。

## 4. `receive_stripe_webhook()`のディスパッチ(design 2節への追加)

`EVENT_CUSTOMER_SUBSCRIPTION_DELETED`受信時:

1. `cancellation_store`が`None`、または該当`store_id`の状態が見つからない場合は
   何もせず200を返す(既存の他イベントと同じ安全側方針)。
   `push_client`が`None`の場合も同様にスキップする
   (`handle_subscription_deleted()`は`push_client`を必須引数として取るため)。
2. `handle_subscription_deleted(state, push_client)`を呼び出す。
3. `outcome`が`send_failed`でなければ、更新後の状態を
   `cancellation_store.set_cancellation_state()`で書き戻す。

## 5. テスト

- `test_stripe_webhook.py`: `EVENT_CUSTOMER_SUBSCRIPTION_DELETED`が
  customerベースで解決されること(invoice系と同じ観点、`_ROUTABLE_EVENT_TYPES`
  経由で対象イベントに含まれること)を確認するテストを追加。
- `test_stripe_webhook_entry_point.py`: `ReceiveStripeWebhookSubscriptionActivatedTest`
  と同型の観点(ハンドラ呼び出し・状態書き戻し・各種未接続時のスキップ・送信失敗時に
  状態が変わらないこと)を確認する`ReceiveStripeWebhookSubscriptionDeletedTest`を追加。

## 6. 今後の課題

- `customer.subscription.updated`(解約予約・取り消し)の配線は、
  「直前の`cancel_at_period_end`をどう保持・比較するか」の設計が別途必要なため、
  引き続き次回以降の課題として残す。
- activated側・cancelled側の`StoreSubscriptionState`の統合要否(Firestore上で
  同一ドキュメントを指すのであれば、どちらかに寄せるか共通化する方が実装時の
  混乱が少ない)は、実Firestore接続後にデータモデルを固める段階で改めて検討する。
- 実際のCloud Functions HTTPエントリポイント(`main(request)`相当)は
  stripe-webhook-http-entry-point-design.md 7節の既存の残課題のまま、
  デプロイ環境確定後の課題として残る。
