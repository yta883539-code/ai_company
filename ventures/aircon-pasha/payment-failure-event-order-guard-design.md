# invoice.payment_failed/succeededへのStripe Webhook配信順序入れ替わりガード
(payment-failure-event-order-guard-design.md、フェーズ281)

## 1. 背景

subscription-event-out-of-order-guard-design.md(フェーズ280)は、Stripeが配信順序を
保証しないことに起因する、`subscription_canceled_at`・`deletion_candidate_at`という
専用フィールドへのstale event(配信順序入れ替わり)ガードを実装した。同フェーズは
「次回候補」として、`invoice.payment_failed`/`invoice.payment_succeeded`(dunning側、
`payment_failure_detected_at`等)の配信順序入れ替わりは未検討のまま残していた。
kura-pashaフェーズ194(subscription-status-event-order-guard-design.md「ケースB」)・
line-reservation-ai側(subscription-event-order-guard-design.md 4節「スコープ外」)でも
同種の指摘があり、本フェーズでaircon-pasha側の対応を行った。

## 2. 具体的にどう壊れるか

`stripe_dispatch.dispatch_stripe_event()`の`_INVOICE_PAYMENT_FAILED`/
`_INVOICE_PAYMENT_SUCCEEDED`分岐は、いずれも「今受け取ったイベントが最新の真実」という
前提で`payment_failure.mark_payment_failure_detected()`/`clear_payment_failure_on_
success()`等を無条件に呼んでいた。

- ケースA(決済失敗→即成功): 一時的な決済失敗の直後にカード情報更新等で即座に決済が
  成功した際、`invoice.payment_failed`の配信がリトライで遅延し`invoice.payment_
  succeeded`より後に届くと、既に決済済みの利用者を誤って`payment_failure_detected_at`
  設定済み(督促対象)へ書き換えてしまう。`push_client`指定時はさらに「お支払いの確認を
  お願いします」という、実際の決済状態と矛盾する通知まで送ってしまう。
- ケースB(ケースAと対称): 決済失敗が確定した後、それより前に発生していた(が遅延
  配信された)決済成功イベントが届くと、既に決済失敗検知済み(督促対象)の状態を誤って
  クリアしてしまい、`payment_suspension_scheduler.py`による制限モードへの自動移行が
  行われなくなる。

kura-pashaの発見(ケースB、決済失敗→即成功)と同種だが、本ventureは
`payment_failure_detected_at`・`payment_suspended_at`等の複数の個別タイムスタンプ
フィールド(フェーズ280が対応した`subscription_canceled_at`と同じ方式)を扱うため、
フェーズ280と同じ「専用フィールドの新旧比較」パターンをそのまま適用できる。

## 3. 修正方針

`UserProfile`に`payment_failure_state_event_time: Optional[datetime] = None`を追加
(`UserProfileStoreProtocol`の`get_payment_failure_state_event_time`/`set_payment_
failure_state_event_time`、`InMemoryUserProfileStore`実装、`resolve_linking_code()`の
再連携時引き継ぎも対応)。`payment_failure_detected_at`等のdunning系フィールドを最後に
実際に反映した(検知・復旧を問わない)イベントの`event.created`を記録する専用フィールド
とし、`subscription_state_event_time`とは独立に管理する(dunning側とsubscription側は
別々のイベント系列のため、同一の時系列比較に混在させない)。

`stripe_dispatch.py`に`_is_stale_payment_failure_event()`/`_record_payment_failure_
event_time()`を新設した(`_is_stale_subscription_state_event()`/`_record_subscription_
state_event_time()`と同じ実装パターン、`hasattr`による後方互換方針も踏襲)。

- `_INVOICE_PAYMENT_FAILED`分岐: `event.created`から`event_time`を算出した直後にstale
  判定を行う。staleなら`mark_payment_failure_detected()`/`handle_payment_failure_
  detected()`のいずれも呼ばず(push_client指定時も通知送信を試みない)、`result.stale_
  payment_failed_user_ids`に記録して即return。stale判定でなければ従来通り適用し、
  適用成功時(push_client未指定、または通知送信成功時)のみ`_record_payment_failure_
  event_time()`で新しい`event_time`を記録する(通知送信失敗時は状態変更なしのため記録
  しない、フェーズ280が`_record_subscription_state_event_time()`を状態変更成功時のみ
  呼ぶのと同じ方針)。
- `_INVOICE_PAYMENT_SUCCEEDED`分岐: 従来`event.created`を読んでいなかったため、
  `_SUBSCRIPTION_CREATED`分岐と同じ方式(欠落・非数値の場合は`None`、`invalid_events`には
  しない)で`succeeded_event_time`を新規に算出する。stale判定でスキップする場合は
  `clear_payment_failure_on_success()`/`handle_payment_succeeded()`のいずれも呼ばず、
  `result.stale_payment_succeeded_user_ids`に記録して即return。stale判定でなければ
  従来通り適用し、`recovery_push_client`未指定時は常に(冪等なno-opの場合も含む)、
  指定時は送信失敗(`OUTCOME_SEND_FAILED`)以外の結果で`_record_payment_failure_event_
  time()`を呼ぶ(通常の決済成功イベントもdunning状態がなくても`event_time`の基準線と
  して記録し続けることで、以降の`invoice.payment_failed`/`succeeded`の新旧比較が常に
  最新のイベントを基準にできるようにするため)。

## 4. スコープ外

- 本ガードは`payment_failure_detected_at`等のdunning系フィールド(`payment_failure_
  state_event_time`という単一の基準線)に対してのみ適用する。`subscription_canceled_
  at`(フェーズ280、`subscription_state_event_time`)とは別系列のため、相互の順序関係
  (例: 解約確定イベントと決済失敗検知イベントの前後関係)は対象外。
  (2026-09-28 09:00 UTC追記・フェーズ282: 本節は元々「`customer.subscription.deleted`
  分岐は`clear_payment_failure_on_success()`を無条件に呼ぶ設計を維持」と明記していたが、
  course-set-pashaフェーズ263が自venture側で発見・是正した「stale全体スキップ」方針
  〈`subscription_canceled_at`設定がstale判定でスキップされる場合、決済失敗フィールド
  クリア・解約確定案内通知も連動してスキップする〉が本venture自身には未反映のまま
  残っていたことが判明したため、本フェーズで是正した。`customer.subscription.deleted`
  分岐内で`_is_stale_subscription_state_event()`による判定を1回評価し
  〈`is_stale_deleted_event`〉、`clear_payment_failure_on_success()`呼び出しと
  `handle_subscription_cancelled()`による解約確定案内通知の両方をこの判定でガードする
  よう変更した〈`subscription_canceled_at`設定自体は従来通りガード済み〉。したがって
  上記「対象外」の記述はもはや正確ではなく、`customer.subscription.deleted`分岐内の
  3つの副作用〈決済失敗フィールドクリア・`subscription_canceled_at`設定・解約確定案内
  通知〉は全て同一のstale判定を共有する。詳細はテスト節参照。)
- `customer.subscription.updated`分岐は`payment_failure_detected_at`等を変更しない
  ため対象外。
- kura-pasha・line-reservation-aiへの本ガードの横展開状況は、kura-pashaフェーズ194・
  line-reservation-ai側で対応済み(いずれもaircon-pasha版とは異なるデータ構造〈enum型
  `subscription_status`/`suspension_reason`文字列〉に沿った独自実装)であることを
  それぞれの設計ドキュメントで確認済み。

## 5. テスト

`test_stripe_dispatch.py`に4件のテストメソッドを追加(`DispatchInvoicePaymentFailedTest`
に`test_stale_payment_failed_event_skipped_when_older_than_already_applied_succeeded`
〈ケースA〉・`test_notification_not_sent_when_payment_failed_event_is_stale`〈push_
client指定時の通知未送信確認〉、`DispatchInvoicePaymentSucceededTest`に`test_stale_
payment_succeeded_event_skipped_when_older_than_already_applied_failed`〈ケースB〉・
`test_recovery_notification_not_sent_when_payment_succeeded_event_is_stale`
〈recovery_push_client指定時の通知未送信確認〉)。既存の`invoice.payment_succeeded`系
テストは`created`を含まないイベントのみを使っており、`succeeded_event_time`が`None`と
なりstale判定は常にFalse(後方互換)となることを既存テストの無改変での成功をもって
確認した。venture全体642件(`python3 -m unittest discover -s prototype -p
"test_*.py"`、変更前638件+新規4件)・schema検証25件(`python3 schema/validate_test_
cases.py`)いずれもパスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: 他venture・アイデア領域の前進。

## 6. 追記(2026-09-28 09:00 UTC定例更新・フェーズ282)

4節「スコープ外」で発見した非対称(`customer.subscription.deleted`受信時、
`subscription_canceled_at`設定はstale判定でガードされる一方、決済失敗フィールド
クリア・解約確定案内通知は無条件に実行される)を是正した。`stripe_dispatch.py`の
`customer.subscription.deleted`分岐で`is_stale_deleted_event = _is_stale_
subscription_state_event(payment_store, user_id, event_time)`を先頭で1回だけ評価し、
`clear_payment_failure_on_success()`呼び出し・`handle_subscription_cancelled()`
通知の両方をこの判定でガードするよう変更した(`subscription_canceled_at`設定自体は
既存のガードのまま)。`test_stripe_dispatch.py`に`test_stale_deleted_event_does_not_
clear_payment_failure_state`・`test_stale_deleted_event_sends_no_cancellation_
notice`の2件を追加(course-set-pashaフェーズ263の同種テストの横展開)、venture全体
644件(`python3 -m unittest discover -s prototype -p "test_*.py"`、変更前642件+
新規2件)・schema検証25件(`python3 schema/validate_test_cases.py`、変更なし)
いずれもパスを確認した。なお`clear_current_plan_on_subscription_deleted()`
(plan_store)・`clear_blocked_but_billing_owner_notified_at()`(blocked_but_billing_
store)の2つの副作用は、course-set-pashaに対応する副作用自体が存在せず横展開元の
判断基準がないため、本フェーズでは対象外のまま残す(次回候補として持ち越す)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: `clear_current_plan_on_subscription_deleted()`・`clear_blocked_but_billing_
owner_notified_at()`へのstale全体スキップ適用の要否検討、または他venture・アイデア
領域の前進。
