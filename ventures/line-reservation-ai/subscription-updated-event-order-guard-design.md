# customer.subscription.updated(cancel_at_period_end通知・plan同期)配信順序保証ガード設計

kura-pashaフェーズ198(subscription-updated-event-order-guard-design.md)・course-set-pasha
横展開時に「他venture(aircon-pasha・course-set-pasha・line-reservation-ai)の
`customer.subscription.updated`相当ハンドラに同種のガード欠落が残っていないかの横断確認」
が申し送られていた件について、line-reservation-aiを確認した記録。aircon-pasha(フェーズ286)・
course-set-pashaは既にこの横展開が完了済みだったが、line-reservation-aiには未反映のまま
残っていたため是正した。

## 1. 発見した欠落

line-reservation-aiの`customer.subscription.updated`処理は2つの独立した副作用を持つ。

1. `handle_subscription_updated()`(cloud_function_subscription_cancelled_webhook.py):
   `cancel_at_period_end`の前後比較による解約予約受理/取り消し通知。
2. `sync_plan_on_subscription_event()`(subscription_plan_sync.py):
   `stores/{storeId}.plan`のプラン同期。

いずれも`event_time`(Stripeイベントの`event.created`)を受け取らず、常に無条件で
最新の`data_object`を反映していた。`handle_subscription_deleted()`・
`handle_subscription_activated()`など他の`customer.subscription.*`ハンドラは既に
`event_time`ベースの配信順序入れ替わりガードを持つ中、`.updated`だけが未対応のまま
残っていた(kura-pashaフェーズ198・course-set-pashaで発見されたのと同じ非対称)。

Stripeカスタマーポータル経由で短期間に複数回の解約予約/取り消し操作、またはプラン変更
(アップグレード/ダウングレード)が行われた場合、Stripeの「at least once」配信・非同期
配送により後発のイベントが先に、先発のイベントが後から遅延配信されるケースが理論上
あり得る。この場合、従来コードでは無条件で最新の`data_object`を反映してしまうため、
既に新しいイベントで確定済みの`plan`・解約予約状態を、遅延配信された古いイベントの値で
誤って上書きしてしまう欠落があった。

## 2. 対応

`StoreSubscriptionState`(cloud_function_subscription_cancelled_webhook.py、
cancellation_store側)に`last_subscription_updated_event_time`を新設した。`.deleted`用の
`last_subscription_event_time`とは独立した専用フィールドとした(`.updated`は
`suspension_reason`自体を変更しないため、kura-pashaフェーズ198と同じ理由)。

`handle_subscription_updated()`に`event_time: Optional[datetime] = None`引数を追加し、
先頭で`state.last_subscription_updated_event_time`と比較するstale判定を行う。staleの
場合は通知送信を一切行わず`stale=True`(`SubscriptionCancellationUpdateResult.stale`、
新設)を返す「丸ごとスキップ」方針とした。staleでない場合は、outcome
(OUTCOME_NO_CHANGE・送信失敗を含む)にかかわらず`event_time`を記録する
(course-set-pashaの`_record_subscription_updated_event_time()`と同じ「結果に
かかわらず記録」方針)。

`stripe_webhook_entry_point.py`の`EVENT_CUSTOMER_SUBSCRIPTION_UPDATED`分岐では、
`sync_plan_on_subscription_event()`(plan同期)は`handle_subscription_updated()`とは
別の書き込み先(`store_profile_store`)を持つため、DELETED分岐(`customer.subscription.
deleted`)で既に採用されている「cancellation_store側の記録済み時刻を先に1回だけ参照し、
stale判定を他の副作用にも及ぼす」パターンをそのまま横展開した。`cancellation_store`が
`None`、または該当`store_id`の状態が見つからない、または`event_time`が無い場合は
判定不能として従来通り無条件適用する(後方互換)。

`handle_subscription_updated()`呼び出し後は、`last_subscription_updated_event_time`の
記録を永続化するため`cancellation_store.set_cancellation_state()`で書き戻すよう変更した
(customer-subscription-updated-event-routing-design.md 3節の「書き戻しは不要」という
記述を更新、追記を残した)。

## 3. スコープ外

- `customer.subscription.updated`同士の重複配信(同一event_id)は既に`event_id_store`
  による`duplicate`判定で別途扱われており、本ガードは同一store_idに対する「複数の異なる
  `.updated`イベント」間の順序入れ替わりのみを対象とする。
- `subscription_plan_sync.sync_plan_on_subscription_event()`自体は変更しない(差分が
  無ければ`set_plan`を呼ばない既存の冪等性はそのまま活きる)。ガードは「呼ぶかどうか」の
  判定のみを担う。

## 4. テスト

`test_cloud_function_subscription_cancelled_webhook.py`に`HandleSubscriptionUpdatedTests`へ
4件追加(正常順序での適用・stale時のスキップ・event_time省略時の無条件適用・
last_subscription_updated_event_time未設定時の無条件適用)。

`test_stripe_webhook_entry_point.py`に`ReceiveStripeWebhookSubscriptionUpdatedTest`へ
stale時にplan同期・通知の両方がスキップされることを確認するテストを追加。

venture全体`python3 prototype/run_all_tests.py`・`python3 schema/validate_test_cases.py`
いずれもパスを確認した(件数は本フェーズのコミットメッセージ参照)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: kura-pashaフェーズ198の申し送り(他venture横断確認)は本フェーズで
aircon-pasha・course-set-pasha・line-reservation-aiの3件とも対応済みと確認できたため
完了。他venture・アイデア領域の前進、またはlaunch-readiness-checklist.md/
pending-approval.mdの記載齟齬の定期棚卸し。
