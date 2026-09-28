# invoice.payment_failed/succeededへのStripe Webhook配信順序入れ替わりガード
(payment-failure-event-order-guard-design.md、フェーズ264)

## 1. 背景

subscription-event-out-of-order-guard-design.md(フェーズ263)は、Stripeが配信順序を
保証しないことに起因する、`subscription_canceled_at`という専用フィールドへのstale
event(配信順序入れ替わり)ガードを実装し、あわせてaircon-pasha・kura-pasha・
line-reservation-aiの3venture横断でこの種のガードの対応状況を確認した。しかしその際、
dunning側(`invoice.payment_failed`/`invoice.payment_succeeded`、`payment_failure_
detected_at`)の配信順序入れ替わりについてはcourse-set-pasha自身では未検討のまま
残っていたことが、aircon-pashaフェーズ281(payment-failure-event-order-guard-design.md、
同名の設計ドキュメント)の「スコープ外」節の棚卸しで判明した(同ドキュメントは
kura-pashaフェーズ194・line-reservation-aiフェーズ続き284が対応済みであることには
言及していたが、course-set-pashaには触れていなかった)。実際に`stripe_webhook.py`の
`invoice.payment_failed`/`invoice.payment_succeeded`分岐を確認したところ、いずれも
event.createdを一切参照せず、届いた順に無条件で状態を書き換えていることを確認した。

## 2. 具体的にどう壊れるか

aircon-pashaフェーズ281と同じ2ケースが course-set-pasha 側にもそのまま当てはまる。

- ケースA(決済失敗→即成功): 一時的な決済失敗の直後にカード情報更新等で即座に決済が
  成功した際、`invoice.payment_failed`の配信がリトライで遅延し`invoice.payment_
  succeeded`より後に届くと、既に決済済みの利用者を誤って`payment_failure_detected_at`
  設定済み(督促対象)へ書き換えてしまう。`push_client`指定時はさらに「お支払いの確認を
  お願いします」という、実際の決済状態と矛盾する通知まで送ってしまう。
- ケースB(ケースAと対称): 決済失敗が確定した後、それより前に発生していた(が遅延
  配信された)決済成功イベントが届くと、既に決済失敗検知済み(督促対象)の状態を誤って
  クリアしてしまい、`payment_failure_reminder_scheduler.py`によるリマインド送信・
  制限モードへの移行判定が行われなくなる。

## 3. 修正方針

フェーズ263が採用した「専用フィールドの新旧比較」パターン
(`_is_stale_subscription_state_event()`/`_record_subscription_state_event_time()`)を
dunning側にも同じ形でもう1系列追加する。subscription側とdunning側は別々のイベント
系列のため、同一の時系列比較に混在させず独立した基準線として持つ(aircon-pasha
フェーズ281と同じ設計判断)。

- `UsageCounterProtocol`(cloud_function_webhook.py)・`PaymentFailureUsageCounter
  Protocol`(stripe_webhook.py)に`get_payment_failure_state_event_time()`/
  `set_payment_failure_state_event_time()`を追加、`InMemoryUsageCounter`に対応する
  dict実装を追加した。
- `stripe_webhook.py`に`_is_stale_payment_failure_event()`/`_record_payment_failure_
  event_time()`を新設した(`_is_stale_subscription_state_event()`/`_record_
  subscription_state_event_time()`と同じ実装パターン、`hasattr`による後方互換方針も
  踏襲)。
- `invoice.payment_failed`分岐: `event.created`から`event_time`を算出した直後にstale
  判定を行う。staleなら`set_payment_failure_detected_at()`/`handle_payment_failure_
  detected()`のいずれも呼ばず(push_client指定時も通知送信を試みない)、`result.stale_
  payment_failed_user_ids`に記録して即return。適用成功時(push_client未指定、または
  通知送信成功時)のみ`_record_payment_failure_event_time()`で新しいevent_timeを記録
  する。
- `invoice.payment_succeeded`分岐: 従来`event.created`を読んでいなかったため、
  `customer.subscription.created`分岐と同じ方式(欠落・非数値の場合はNone、invalid_
  eventsにはしない)で`event_time`を新規に算出する。stale判定でスキップする場合は
  `clear_payment_failure_detected_at()`/`handle_payment_succeeded()`のいずれも呼ばず、
  `result.stale_payment_succeeded_user_ids`に記録して即return。push_client指定時は
  送信失敗(`OUTCOME_SEND_FAILED`)以外の結果で、push_client未指定時は常に(dunning
  状態の有無によらず)`_record_payment_failure_event_time()`を呼ぶ(通常の決済成功
  イベントもdunning状態がなくてもevent_timeの基準線として記録し続けることで、以降の
  `invoice.payment_failed`/`succeeded`の新旧比較が常に最新のイベントを基準にできる
  ようにするため、aircon-pashaフェーズ281と同じ方針)。

## 4. スコープ外

- 本ガードは`payment_failure_detected_at`等のdunning系フィールド(`payment_failure_
  state_event_time`という単一の基準線)に対してのみ適用する。`subscription_canceled_
  at`(フェーズ263、`subscription_state_event_time`)とは別系列のため、相互の順序関係
  は対象外。
- `customer.subscription.deleted`分岐は引き続き決済失敗検知の有無によらず無条件で
  `payment_failure_detected_at`等をクリアする既存方針(フェーズ263で確認済みの
  「stale全体スキップ」方針は解約確定イベント自体のstale判定に限定され、解約確定時の
  決済失敗フィールドクリア自体は対象外)を維持する。

## 5. テスト

`test_stripe_webhook.py`に`PaymentFailureEventOrderGuardTest`クラスを新設し5件の
テストメソッドを追加した(`test_stale_payment_failed_event_skipped_when_older_than_
already_applied_succeeded`〈ケースA〉・`test_notification_not_sent_when_payment_
failed_event_is_stale`〈push_client指定時の通知未送信確認〉・`test_stale_payment_
succeeded_event_skipped_when_older_than_already_applied_failed`〈ケースB〉・
`test_recovery_notification_not_sent_when_payment_succeeded_event_is_stale`
〈push_client指定時の通知未送信確認〉・`test_existing_events_without_created_are_
not_treated_as_stale`〈created省略時の後方互換確認〉)。既存の`invoice.payment_
succeeded`系テストは`created`を含まないイベントのみを使っており、`event_time`が
`None`となりstale判定は常にFalse(後方互換)となることを既存テストの無改変での成功
をもって確認した。venture全体`python3 -m unittest discover -s prototype -p
"test_*.py"`677件(672→677)・schema検証21件(`python3 schema/validate_test_
cases.py`)いずれもパスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない。
