# invoice.payment_failed/succeeded(payment_failure_detected_at)配信順序入れ替わりガード
(payment-failure-event-order-guard-design.md、フェーズ216)

## 1. 背景

フェーズ214(subscription-lifecycle-event-order-guard-design.md)の「次回候補(1)」
として残っていた「`invoice.payment_failed`・`invoice.payment_succeeded`への同種ガードの
横展開の要否検討」、およびフェーズ215(stripe-event-idempotency-design.md)の
「次回候補(3)」として引き続き未着手だった同じ論点に対応した。

course-set-pashaの`prototype/stripe_webhook.py`(`_is_stale_payment_failure_event()`・
`payment_failure_state_event_time`)を横断確認したところ、本venture(forklift-pasha)に
対応する`handle_invoice_payment_failed()`(フェーズ167)・
`handle_invoice_payment_succeeded()`(同フェーズ)はいずれも`customer`から`internal_id`を
逆引きした後、`payment_failure_detected_at`の書き込み/クリアを無条件に行っており、
`customer.subscription.*`系が既に備えるevent_timeベースの配信順序入れ替わりガードが
一度も実装されていなかったことを確認した。

なお、フェーズ215で追加した`event_id_store`(`event.id`単位の重複配信対策)は本ガードとは
別軸の課題である。`event_id_store`は「同一の`event.id`を持つイベントの再配信」を防ぐが、
`invoice.payment_failed`(event A)と`invoice.payment_succeeded`(event B)のように
`event.id`が異なる2つのイベント間での配信順序の入れ替わりには無力であり、本ガードが
別途必要になる。

## 2. 具体的にどう壊れるか

Stripeの「at least once」配信・非同期配送により、`invoice.payment_failed`(決済失敗、
古いイベント)と`invoice.payment_succeeded`(決済成功による復旧、新しいイベント)の到着
順序が入れ替わるケースが理論上あり得る。従来コードでは両ハンドラとも無条件で
`payment_failure_detected_at`を書き換える/クリアするため、以下の2パターンで実害が生じる。

- ケースA(決済成功後に古い失敗が遅延配信): 決済失敗(t1)の後すぐに決済が成功して復旧
  (t2 > t1)した場合、`invoice.payment_succeeded`(t2)が先に処理されて
  `payment_failure_detected_at`がクリアされた後、遅延配信された古い`invoice.payment_
  failed`(t1)が後から届くと、既に復旧済みのdunning状態を誤って再度「決済失敗中」に
  戻してしまう(猶予期間が不要に再開され、実際には支払い済みの事業者が制限モード移行の
  対象になりうる)。
- ケースB(決済失敗後に古い成功が遅延配信、頻度は低いが対象): 決済成功(t1)の後に別の
  決済サイクルで決済失敗(t2 > t1)が発生した場合、`invoice.payment_failed`(t2)が先に
  処理されて`payment_failure_detected_at`が記録された後、t1時点の古い`invoice.payment_
  succeeded`が遅延配信されると、進行中のdunning状態(t2)を誤って解除してしまう。

(aircon-pashaフェーズ281で同種のケースA/Bが先行して整理されており、course-set-pasha側の
`payment-failure-event-order-guard-design.md`もこれを横展開したものである。本venture側は
これまでこの横展開が行われていなかった。)

## 3. 修正内容

`invoice.payment_failed`・`invoice.payment_succeeded`はどちらも`payment_failure_
detected_at`を書き換える対になるイベントのため、`customer.subscription.deleted`/
`created`と同じ考え方で1つの`payment_failure_event_time`キーを共有する設計とした
(`customer.subscription.*`系の`subscription_lifecycle_event_time`とは別系列のイベント
〈dunning系〉のため、独立したキーに記録する。course-set-pashaの
`payment_failure_state_event_time`と同一設計)。

- `trial_management.FleetOperatorStoreProtocol`に`get_payment_failure_event_time()`・
  `set_payment_failure_event_time()`を追加し、`InMemoryFleetOperatorStore`に実装した。
- `stripe_webhook.py`に`_is_stale_payment_failure_event()`・
  `_record_payment_failure_event_time()`を追加した(`_is_stale_subscription_lifecycle_
  event()`・`_record_subscription_lifecycle_event_time()`と同一の構造)。
- `handle_invoice_payment_failed()`・`handle_invoice_payment_succeeded()`の両方に
  `event_time`引数(省略時は従来通り無条件適用、後方互換)を追加し、`receive_stripe_
  webhook()`から`_event_time_from_created()`を配線した。
- stale判定(記録済みのevent_time「以下」)を通過した場合は、処理の成否にかかわらず
  event_timeを記録する(`handle_invoice_payment_succeeded()`で`payment_failure_
  detected_at`が元々未設定〈cleared=False〉の場合も記録する。以降の`payment_failed`/
  `succeeded`の新旧比較が常に最新のイベントを基準にできるようにするため、aircon-pasha・
  course-set-pashaと同じ方針)。
- stale判定は`payment_failure_detected_at`の有無チェックより先に行う
  (`handle_invoice_payment_succeeded()`で、古いイベント自体の適用を状態の有無に関わらず
  一貫して拒否するため)。

## 4. 検証

`prototype/test_stripe_webhook.py`に新規テスト10件を追加した(check()呼び出し128件→
138件)。正常順序でのstale=False、遅延配信された古いfailed/succeededのstale=True、
決済成功後の遅延failed(ケースA)・決済失敗確定後にはならないが基準線更新の検証、
event_time省略時の後方互換(無条件適用)を確認した。既存テスト100件・run_all_tests
24ファイル・schema検証11件・browser_mockup_checks.js 49件はいずれも変更なしでパス
(回帰なし)。

## 5. 残課題・次回候補

- ~~実Firestore接続後の`payment_failure_event_time`フィールドの永続化実装(実Stripe/実GCP
  プロジェクト接続後、オーナー承認待ち)。~~ → フェーズ218で解消。本アダプタ
  (`prototype/firestore_fleet_operator_adapter.py`)はgoogle-cloud-firestore SDKを直接
  importしないダックタイピング設計のため、他の15メソッド同様オーナー承認・実クラウド
  接続を要さずに実装できることが判明し、`get/set_payment_failure_event_time()`を実装
  (firestore-data-model.mdにも`paymentFailureEventTime`として追記)。
- `subscription_updated_event_time`・`checkout_session_completed_event_time`・
  `subscription_lifecycle_event_time`の3フィールドも同様に本アダプタ未対応のまま残って
  いることをフェーズ218で発見した。横展開の要否・優先度は次回候補とする。
- event-komiguai-pasha(結合実装待ち)・oshien-pasha(Webhook未実装)への横展開は各
  venture側で実装着手時に検討。
- 他venture・アイデア領域の前進。
