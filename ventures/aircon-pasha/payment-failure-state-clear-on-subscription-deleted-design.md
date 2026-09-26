# `customer.subscription.deleted`受信時の決済失敗系状態クリア対応(フェーズ272)

line-reservation-aiのフェーズ続き273(2026-09-26 09:00 UTC)横断確認で見つかったバグ
クラス「解約(cancelled)確定後も、旧stateを根拠にスケジューラが誤って移行イベントを
発行してしまう」を本ventureにも当てはまるか点検し、実際に同種の欠落が存在したため対応した。

## 1. line-reservation-aiで見つかった元のバグ

line-reservation-aiの`dormant_mode_scheduler.select_due_dormant_events()`は、
`suspension_reason == "cancelled"`のユーザーを明示的に除外するガードを持っていなかった。
`stripe_customer_id`・`dormant_transitioned_at`の組み合わせで大半のcancelledケースは
間接的に除外できていたが、両方が未設定のままcancelledになる理論上のケース(Webhook到達
順序次第であり得る)では、`trial_unselected`起点の休止モード移行イベントを誤って発行して
しまう欠落があった。

## 2. 本ventureでの横断確認結果

本ventureは`dormant_mode`という概念自体を持たないため、上記ガードそのものの移植対象は
ない(subscription_cancellation_notification.classify_cancel_at_period_end_change()の
docstringが既に明記しているとおり、本ventureは`suspension_reason`相当の別立て状態を持たない)。

一方、本ventureには構造的に類似した別のギャップが存在した。`stripe_dispatch.
dispatch_stripe_event()`の`_SUBSCRIPTION_DELETED`(`customer.subscription.deleted`)
分岐は、`plan_store`指定時の`current_plan_id`クリア(フェーズ161)・
`blocked_but_billing_store`指定時の`blocked_but_billing_owner_notified_at`クリア
(フェーズ175)・`cancellation_push_client`指定時の解約完了案内送信(フェーズ184)を
行っていたが、`payment_store`(payment_failure.PaymentFailureStoreProtocol)指定時に
`payment_failure_detected_at`・`payment_suspended_at`・`payment_failure_reminder_sent_at`・
`payment_suspension_owner_notified_at`の4フィールドをクリアする配線が抜けていた。

この結果、次の理論上のシーケンスが起こり得た。

1. 顧客の決済が失敗し、`invoice.payment_failed`受信で`payment_failure_detected_at`が
   設定される(猶予期間開始)。
2. 猶予期間中(`payment_suspended_at`がまだ未設定)に、顧客がStripe側で契約そのものを
   終了する、またはStripeが猶予期間の設定と無関係に契約を終了させる等の事情で
   `customer.subscription.deleted`が発火する。この時点で`handle_subscription_
   cancelled()`が呼ばれ、顧客には「ご契約が終了しました」という解約完了案内が届く。
3. しかし`payment_failure_detected_at`はクリアされないまま残るため、後日
   `payment_suspension_scheduler.send_payment_suspensions()`・
   `payment_failure_reminder_scheduler.send_payment_failure_reminders()`が日次バッチで
   `select_due_payment_suspensions()`/`select_due_payment_failure_reminders()`を
   実行した際、既に契約が終了している顧客が候補として再度選出されてしまう。
4. 結果、既に「ご契約が終了しました」と案内された顧客に、後日「生成を一時停止しました」・
   「お支払い確認のお願い(再送)です」という矛盾したPush通知が届いてしまう。

line-reservation-aiの元バグが「休止モード移行イベントの誤発火」だったのに対し、本ventureの
今回のギャップは「決済失敗系スケジューラの誤選出・矛盾通知」という形で現れる点は異なるが、
「解約確定というイベントを受けても、それより前に書き込まれた別系統のstateが後続の
スケジューラ判定にそのまま生き残ってしまう」という構造は同種である。

## 3. 対応方針

新規のクリア関数は追加せず、既存の`payment_failure.clear_payment_failure_on_success()`
(`invoice.payment_succeeded`受信時に同じ4フィールドをクリアするために既に存在する関数)を
`_SUBSCRIPTION_DELETED`分岐からも呼ぶ。`plan_store`・`blocked_but_billing_store`と同じく
新規引数は追加せず、既存の`payment_store`引数(`invoice.payment_failed`/
`invoice.payment_succeeded`向けに既に受け取っている)を再利用する。

`payment_store`未指定(`None`)の場合はこれまで通りクリアを行わない(既存呼び出し経路への
後方互換措置。`stripe_webhook.receive_stripe_webhook()`は既に`payment_store`を
`dispatch_stripe_event()`へ委譲済みのため、本フェーズの変更のみで実HTTPエントリポイント
経由でも即座に有効になる)。

`StripeDispatchResult`に`payment_failure_cleared_on_deletion_user_ids`フィールドを追加し、
クリア前に4フィールドのいずれか1つでも設定済みだった(=クリアが実際に発生した)user_idを
記録する(`blocked_but_billing_owner_notified_cleared_user_ids`と同じ、呼び出し側がログ
確認できる冪等設計)。

## 4. 対応しなかった項目

- `deletion_candidate.py`の`deletion_candidate_at`(365日後の削除候補化)自体は本フェーズの
  対象外。決済失敗系4フィールドと削除候補化は独立した状態のため、意図的にクリア対象へ
  含めなかった(`blocked_but_billing_owner_notified_at`が意図的にクリア対象外とされた
  フェーズ255の判断と同じ考え方)。
- 実LINE Push Message API・実Stripeアカウント接続はいずれもオーナー承認待ち
  (pending-approval.md参照)、本フェーズでは新たに発生していない。

## 5. テスト

`test_stripe_dispatch.py`に3件追加。
- `test_clears_payment_failure_state_when_payment_store_provided`: 4フィールドすべてが
  設定済みの状態から`customer.subscription.deleted`を受信すると、すべてクリアされ
  `payment_failure_cleared_on_deletion_user_ids`に記録されることを確認する。
- `test_payment_failure_state_untouched_when_already_unset`: 4フィールドがいずれも未設定の
  場合、クリア扱いにならない(`clear_payment_failure_on_success()`が`False`を返す)ことを
  確認する。
- `test_payment_failure_state_untouched_when_payment_store_not_provided`: `payment_store`
  未指定時は従来通りクリアを行わないことを確認する(後方互換)。

venture全体585件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`、変更前
582件+新規3件)・schema検証25件(`python3 schema/validate_test_cases.py`、変更前と同じ
結果)いずれもパスを確認した。
