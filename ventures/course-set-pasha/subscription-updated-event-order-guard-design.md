# customer.subscription.updated(plan・解約予約通知)配信順序保証ガード設計

kura-pashaフェーズ198(subscription-updated-event-order-guard-design.md)が、
`customer.subscription.deleted`/`created`/`invoice.payment_failed`/`invoice.payment_succeeded`
はいずれも`event_time`ベースの配信順序入れ替わりガードを持つ一方、`customer.subscription.
updated`だけはこのガードを一度も持っていなかったことを発見し、「他venture(aircon-pasha・
course-set-pasha・line-reservation-ai)の`customer.subscription.updated`相当ハンドラに同種の
ガード欠落が残っていないかの横断確認」を次回候補として申し送った。本フェーズ(2026-09-28
21:00 UTC台の定例更新)で、course-set-pasha自身にも同じ欠落が残っていることを確認し、是正した
記録。

## 1. 検討したシナリオ

course-set-pashaの`dispatch_stripe_event()`内、`customer.subscription.updated`分岐は
以下の3つをいずれも無条件(event_timeによる順序チェックなし)で行っていた。

- `user_profile_store.set_plan()`によるプラン変更(アップグレード/ダウングレード)の反映
- `cancel_at_period_end`の前後比較による解約予約受理・解約取り消し通知の送信
- ステータスがactive/trialingへ変化した場合の削除候補フラグクリア

Stripeカスタマーポータル経由で短期間に複数回操作(連続したプラン変更、解約予約→取り消しの
連続操作等)が行われた場合、Stripeの「at least once」配信・非同期配送により後発の
`.updated`イベントが先に、先発のイベントが後から遅延配信されるケースが理論上あり得る。
この場合、従来コードでは無条件で最新の`data_object`を反映してしまうため、既に新しい
イベントで確定済みのプラン・解約予約状態を、遅延配信された古いイベントの値で誤って
上書き・矛盾した通知を送信してしまう欠落があった(kura-pashaフェーズ198と同種)。

## 2. 対応

`PaymentFailureUsageCounterProtocol`(stripe_webhook.py)に
`get_subscription_updated_event_time()`/`set_subscription_updated_event_time()`
(user_idキー、既存の`get/set_subscription_state_event_time`・`get/set_payment_failure_
state_event_time`と同じ設計で、両者とは独立した専用の基準線)を新設した。`_is_stale_
subscription_updated_event()`/`_record_subscription_updated_event_time()`を追加し、
`dispatch_stripe_event()`の`customer.subscription.updated`分岐の先頭(user_id解決直後)で
`event.get("created")`からevent_timeを算出してstale判定を行い、staleの場合はプラン更新・
解約予約受理/取り消し通知・reactivated状態クリアのいずれも行わず即座に返す
(`StripeDispatchResult.stale_subscription_updated_user_ids`に記録)「丸ごとスキップ」方針を
採用した(kura-pashaフェーズ198・他ハンドラと同じ考え方)。正常適用時は分岐の最後で
event_timeを記録する。

`InMemoryUsageCounter`(cloud_function_webhook.py)にも`get/set_subscription_updated_
event_time()`を実装し、テストで利用できるようにした。

`event_time`がNone(`event.created`が数値でない/存在しない)の場合、`usage_counter`が
対応メソッドを持たない場合、または記録済みの時刻が未設定(本ガード導入前からの既存user等)の
場合はチェックを行わず従来通り無条件適用する(既存の他ガードと同じ後方互換方針)。

## 3. スコープ外

- `customer.subscription.updated`同士の重複配信(同一event_id)は`event_id_store`による
  `duplicate_event`判定で別途扱われており、本ガードは同一user_idに対する「複数の異なる
  `.updated`イベント」間の順序入れ替わりのみを対象とする。
- `customer.subscription.deleted`/`created`用の`subscription_state_event_time`とは
  別イベント系列のため独立フィールドとした(共有すると`.updated`同士の順序入れ替わりを
  正しく検知できないため、kura-pashaフェーズ198と同じ判断)。

## 4. テスト

`test_stripe_webhook.py`(`DispatchStripeEventTest`)に3件追加した(古い`.updated`が届いた
場合のplan書き込みスキップ・通知スキップ・usage_counter未指定時の後方互換確認)。

venture全体`python3 -m unittest discover -s prototype -p "test_*.py"`(685件、682→685)・
schema検証`python3 schema/validate_test_cases.py`(21件、変更なし)いずれもパスを確認した。

他venture(aircon-pasha・line-reservation-ai)の`customer.subscription.updated`相当ハンドラに
同種のガード欠落が残っていないかの横断確認は、次回以降の棚卸し候補として申し送る(本フェーズは
course-set-pasha自身の是正のみを対象とした)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため、
pending-approval.mdへの追記なし。

次回候補: 他venture(aircon-pasha・line-reservation-ai)の`customer.subscription.updated`
ハンドラに同種のガード欠落がないかの横断確認。または他venture・アイデア領域の前進、
launch-readiness-checklist.mdとpending-approval.mdの記載齟齬の定期棚卸し。
