# customer.subscription.updated 受信時のplan_id同期設計

README.mdフェーズ127「次回候補(2)」(`plan_id_resolution.sync_plan_id_on_subscription_
event()`が既に用意済みだが未配線)に対応する。

## 1. 位置づけ

line-reservation-ai/subscription-plan-sync-design.mdと同じ目的: Stripe Customer Portal
経由でのプラン変更(`customer.subscription.updated`)を受信した際に、`checkout.session.
completed`受信時にmetadataから書き込んだ`plan_id`が古いままにならないよう同期する。

本ventureは`customer.subscription.deleted`(解約)・決済失敗検知を処理する設計が
まだ存在しないため、本フェーズのスコープは`customer.subscription.updated`受信時の
`plan_id`同期のみに限定する(`stripe_webhook.py`冒頭のdocstring参照)。それ以外の
イベント種別(`customer.subscription.deleted`を含む)は従来どおり200(受理・無視)。

## 2. `internal_id`の逆引き

`customer.subscription.updated`イベントの`data.object.customer`は`stripe_customer_id`
であり、`internal_id`を直接含まない。`checkout.session.completed`受信時に
`handle_checkout_session_completed()`が`store.set_stripe_customer_id()`で書き込んだ
逆引きインデックス(`InMemoryFleetOperatorStore.get_internal_id_by_stripe_customer_id()`)
に依存して解決する。

逆引きできない場合(本venture未着手の経路で作成された`customer`、またはテスト上の
未知の値)は`error="unknown_customer"`として同期をスキップする。実運用では
`checkout.session.completed`を一度も受信していない`customer`からの`subscription.updated`
は想定しにくいが、安全側に倒して例外を発生させず常に200で受理する(Stripe側の再送
ループを避ける、design方針は他venture共通)。

## 3. plan_idの解決・書き込み

`plan_id_resolution.sync_plan_id_on_subscription_event()`にそのまま委譲する。
同関数は`items.data[0].price.lookup_key`を`LOOKUP_KEY_TO_PLAN_ID`で解決し、未知の
lookup_key・欠落時は常に`None`(書き込みなし)、既存値と同一の場合も書き込みなし
(差分チェック)という既存の安全側方針をそのまま使う。

実際にStripe Price作成時に`lookup_key`(`forklift_pasha_light`/`_standard`/`_fleet`)を
設定する作業自体は、実Stripeアカウント接続(オーナー承認待ち、pending-approval.md
2026-10-06 22:00 UTC記載)の範囲内であり、本フェーズでは新たな承認待ち事項を追加しない。

## 4. 残課題

- `customer.subscription.deleted`(解約)の受信・処理は本venture未着手のまま
  (解約時の`generation_paused`相当のフラグ設計自体が無い、次回以降の課題)。
- 実HTTPエンドポイントとしての動作確認・実Stripe Webhook登録自体はオーナー承認待ち。
- Webフォームのプラン選択UI自体(Checkout Session発行の起点)は本venture未着手のまま。

最終更新: 2026-10-11 15:00 UTC(フェーズ128: 本設計に基づき`prototype/stripe_webhook.py`に
`handle_customer_subscription_updated()`を追加し、`receive_stripe_webhook()`から
`customer.subscription.updated`をディスパッチするよう配線した)
