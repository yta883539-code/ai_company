# `customer.subscription.deleted`(解約確定)受信処理設計

作成日: 2026-09-09(フェーズ53)

stripe-webhook-checkout-completed-design.md(フェーズ51)「4. 未検証・残課題」に
残っていた、course-set-pasha/aircon-pashaが実装済みの`customer.subscription.deleted`
(解約確定)への対応を、本ventureへ横展開する。`invoice.payment_failed`/
`invoice.payment_succeeded`(決済失敗ダニング)は本フェーズの対象外とし、引き続き
次の課題として残す(スコープを1イベント種別に絞る)。

## 1. `client_reference_id`を持たないイベントのworkshop_id解決

`checkout.session.completed`は`client_reference_id`にworkshop_idが直接設定されている
ため解決が容易だったが、`customer.subscription.deleted`の`data.object`は
Stripeサブスクリプションオブジェクトそのもので`client_reference_id`を持たない。
`customer`(Stripe顧客ID)は必ず含まれるため、これを起点にworkshop_idへ逆引きする
必要がある(aircon-pasha/course-set-pashaの`get_user_id_by_stripe_customer_id`と
同じ位置づけ)。

`WorkshopStoreProtocol`に`get_workshop_id_by_stripe_customer_id(stripe_customer_id)
-> Optional[str]`を追加した。`InMemoryWorkshopStore`は`set_stripe_customer_id()`実行時に
`workshop_id -> stripe_customer_id`(既存)と`stripe_customer_id -> workshop_id`(新設の
逆引き用辞書)の両方を同時に更新する(実Firestoreでは、この逆引き自体は
`craftsman_workshop`コレクションに対する`stripe_customer_id`フィールドの等値クエリで
代替する想定で、専用の逆引きコレクションを別途持つ必要はない)。

## 2. `handle_customer_subscription_deleted()`

```python
def handle_customer_subscription_deleted(
    data_object: dict, workshop_store: WorkshopStoreProtocol,
) -> CustomerSubscriptionDeletedResult:
```

処理内容:

1. `data_object["customer"]`が空・欠落の場合は`invalid=True`を返し、以降の処理を
   行わない(`handle_checkout_session_completed`のclient_reference_id欠落時と同じ
   「不正なイベントで例外を外に漏らさない」方針)。
2. `workshop_store.get_workshop_id_by_stripe_customer_id(stripe_customer_id)`で
   workshop_idを逆引きする。解決できない場合(紐付け前にイベントが届いた、または
   本サービス外の顧客のイベントが誤って届いた等)は`unresolved=True`を返し、
   `set_subscription_status`は呼ばない。
3. 解決できた場合、`workshop_store.set_subscription_status(workshop_id, "canceled")`を
   呼ぶ。

`CustomerSubscriptionDeletedResult`(dataclass): `workshop_id`(成功時のみ)・
`invalid`・`unresolved`の3フィールド。

## 3. `receive_stripe_webhook()`への配線

`event["type"]`の判定対象を`{"checkout.session.completed", "customer.subscription.
deleted"}`の2種類に拡張し、後者は`handle_customer_subscription_deleted()`へ委譲する。

- `invalid`時は`status_code=400`(`error="missing_customer"`)。
- `unresolved`時は`status_code=200`(`unresolved_customer=True`)を返す
  (Stripe側への無限リトライを避ける、course-set-pasha/aircon-pashaの
  `unresolved_customers`と同じ扱い。紐付け前の解約イベントは実運用上ほぼ起こらない
  想定だが、起きても実害なく無視できる設計とする)。
- 成功時は`status_code=200`・`workshop_id`を返す。

`StripeWebhookReceiverResult`に`unresolved_customer: bool = False`フィールドを追加した
(既存呼び出し元への後方互換、デフォルトFalse)。

## 4. 未検証・残課題

- 実Stripeアカウント接続は引き続きオーナー承認待ちのため未着手のまま残る
  (pending-approval.md参照)。
- `invoice.payment_failed`/`invoice.payment_succeeded`(決済失敗ダニング)への対応は
  本フェーズの対象外。対応後、フェーズ52が`"past_due"`を一律ブロック対象とした簡易実装を、
  ダニング固有の猶予期間つき扱いへ見直す必要がある(README「次にやること」参照)。
- `customer.subscription.deleted`受信時、当該workshopの契約者(LINEトーク)への
  解約完了案内送信は未設計(course-set-pasha/aircon-pashaのsubscription-cancellation-
  notification-design.md相当)。本フェーズは`subscription_status`の状態更新のみに範囲を
  絞った。
- イベントID(`event.id`)によるべき等性チェックは、`set_subscription_status`の
  上書きに実害が無いため`checkout.session.completed`と同様に当面省略した
  (stripe-webhook-checkout-completed-design.md 4節と同じ判断)。
