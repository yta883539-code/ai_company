# customer.subscription.updated(current_period_end・plan_id)配信順序保証ガード設計

フェーズ197(checkout-session-completed-plan-event-order-guard-design.md)でplan書き込みの
配信順序入れ替わりガードを整備した際、`stripe_webhook.py`の他イベントハンドラを横断確認した
ところ、`handle_customer_subscription_updated()`だけがevent_time引数自体を持たず、
`current_period_end`(`set_current_period_end`)・`plan_id`
(`subscription_plan_sync.sync_plan_on_subscription_event()`)の書き込みが常に無条件で
行われていたことが判明した。フェーズ198(2026-09-28 21:00 UTC台の定例更新)で是正した記録。

## 1. 検討したシナリオ

`handle_checkout_session_completed()`・`handle_customer_subscription_deleted()`・
`handle_invoice_payment_failed()`・`handle_invoice_payment_succeeded()`はいずれも
`event_time`ベースの配信順序入れ替わりガード(stale-eventガード)を持つ一方、
`handle_customer_subscription_updated()`にはこのガードが一度も実装されていなかった。

Stripeカスタマーポータル経由で短期間に複数回プラン変更(例: standard→multi_craftsman→
standardのように連続変更)が行われた場合、または`current_period_end`が更新される
`customer.subscription.updated`が複数回連続で発生した場合、Stripeの「at least once」
配信・非同期配送により後発のイベントが先に、先発のイベントが後から遅延配信される
ケースが理論上あり得る。この場合、従来コードでは無条件で最新の`data_object`を反映して
しまうため、既に新しいイベントで確定済みの`current_period_end`・`plan_id`を、遅延配信
された古いイベントの値で誤って上書きしてしまう欠落があった
(subscription-status-event-order-guard-design.mdの「ケースA/B」と同種)。

さらに、`cancel_at_period_end`の前後比較による解約予約受理・解約取り消し通知
(`handle_subscription_cancellation_update()`)も同じ関数内で無条件に行われており、
遅延配信された古いイベントの`previous_attributes`と現在の状態を比較してしまうと、
既に解約取り消し済み(または解約予約確定済み)の契約者へ矛盾した通知を誤って送信する
おそれがあった。

## 2. 対応

`WorkshopStoreProtocol`(usage_counter_workshop.py)に
`get_subscription_updated_event_time()`/`set_subscription_updated_event_time()`
(workshop_idキー、既存の`get/set_checkout_session_completed_event_time`と同じ設計)を
新設した。`stripe_webhook.py`に`_is_stale_subscription_updated_event()`/
`_record_subscription_updated_event_time()`を追加し、`handle_customer_subscription_
updated()`の先頭(workshop_id解決直後)でstale判定を行い、staleの場合は
`current_period_end`書き込み・`plan_id`同期・解約予約受理/取り消し通知のいずれも行わず
`stale=True`を返す「丸ごとスキップ」方針を採用した(他ハンドラと同じ考え方)。

`receive_stripe_webhook()`から`handle_customer_subscription_updated()`へは、既に
`_event_time_from_created()`で算出済みの`event_time`を新たに渡すよう配線した(従来は
そもそも引数として渡す経路自体が存在しなかった)。

`event_time`省略時、`store`が対応メソッドを持たない場合(hasattr未対応の簡易スタブ等)、
または記録済みの時刻が未設定(本ガード導入前からの既存workshop等)の場合はチェックを
行わず従来通り無条件適用する(既存の他ガードと同じ後方互換方針)。

## 3. スコープ外

- `customer.subscription.updated`同士の重複配信(同一event_id)は既に`event_id_store`
  による`duplicate_event`判定で別途扱われており、本ガードは同一workshop_idに対する
  「複数の異なる`.updated`イベント」間の順序入れ替わりのみを対象とする。
- `subscription_status`自体は本イベントで変更されないため
  (design docstring既述の通り)、既存の`subscription_status_event_time`とは独立した
  専用フィールドとした(共有した場合、`.updated`同士の順序入れ替わりを正しく検知
  できないため)。

## 4. テスト

`test_stripe_webhook.py`に4件追加した(先行`.updated`より古い`.updated`が届いた場合の
`current_period_end`保護・stale時のplan_id同期/通知抑止・正常順序での適用確認・store
未対応時の無条件適用)。

venture全体`python3 prototype/run_all_tests.py`(16ファイルOK、`test_stripe_webhook.py`
単体は178→182件)・schema検証`python3 schema/validate_test_cases.py`(32件、変更なし)
いずれもパスを確認した。

他venture(aircon-pasha・course-set-pasha・line-reservation-ai)の`customer.subscription.
updated`相当ハンドラに同種のガード欠落が残っていないかの横断確認は、次回以降の棚卸し
候補として申し送る(本フェーズはkura-pasha自身の是正のみを対象とした)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: 他venture(aircon-pasha・course-set-pasha・line-reservation-ai)の
`customer.subscription.updated`ハンドラに同種のガード欠落がないかの横断確認。または
他venture・アイデア領域の前進、launch-readiness-checklist.mdとpending-approval.mdの
記載齟齬の定期棚卸し。
