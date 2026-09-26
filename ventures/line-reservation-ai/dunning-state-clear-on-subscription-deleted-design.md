# `customer.subscription.deleted`受信時のdunning state クリア対応(フェーズ続き275)

2026-09-26 07:00〜15:00 UTCの一連の横断確認(line-reservation-aiフェーズ続き273が発端、
aircon-pashaフェーズ272・kura-pashaフェーズ187・course-set-pashaフェーズ256で順次対応)で
繰り返し見つかったバグクラス「解約(`customer.subscription.deleted`)確定後も、それより前に
書き込まれた決済失敗系のstateが別系統のまま残ってしまう」について、発端となった本venture
自身の`customer.subscription.deleted`経路(`stripe_webhook_entry_point.
receive_stripe_webhook()`の`EVENT_CUSTOMER_SUBSCRIPTION_DELETED`分岐)を再点検したところ、
同種の欠落が残っていたため対応する。

## 1. 見つかったギャップ

`receive_stripe_webhook()`は`customer.subscription.deleted`受信時、`cancellation_store`
(`StoreCancellationState`)側の`blocked_but_billing_owner_notified_at`クリアと
`store_profile_store`側の`suspension_reason`書き込みは行っていたが、`dunning_store`
(`StoreDunningState`、`payment_failure_detected_at`・`sent_event_keys`・自身の
`suspension_reason`を保持)側は一切参照していなかった。

理論上のシーケンス:

1. `invoice.payment_failed`受信で`payment_failure_detected_at`が設定される(猶予期間開始、
   まだ`suspension_reason`は`"payment_failed"`になっていない)。
2. 猶予期間中に顧客が契約そのものを終了し`customer.subscription.deleted`が発火する。
   `classify_subscription_deleted()`は`suspension_reason`が`"payment_failed"`のときだけ
   `OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED`として処理をスキップするが、猶予期間中(まだ
   `"payment_failed"`に至っていない)はこの分岐に入らず通常の解約処理が進む。
3. `cancellation_store`側は`suspension_reason = "cancelled"`になり解約完了案内が届くが、
   `dunning_store`側の`payment_failure_detected_at`・`sent_event_keys`はクリアされない
   まま残る。
4. 後日`cloud_function_send_dunning_notifications.py`の日次バッチが
   `select_due_dunning_events()`相当のロジックでこの店舗を候補として再選出し、既に
   「ご契約が終了しました」と案内済みのオーナーに矛盾したリマインド・制限モード移行通知が
   届いてしまう。

aircon-pasha/course-set-pasha/kura-pashaで見つかった構造(解約確定というイベントを受けても
別系統のstateが後続のバッチ判定にそのまま生き残る)と同じクラスのバグである。

## 2. 対応方針

`stripe_webhook_entry_point.py`に`clear_dunning_state_on_subscription_deleted(state)`を
新設し、`EVENT_CUSTOMER_SUBSCRIPTION_DELETED`分岐から`store_profile_store`の書き込みと
同じ「`cancellation_store`/`push_client`の要否・通知成否とは独立」の位置で呼ぶ。

- `payment_failure_detected_at`を`None`に、`sent_event_keys`を空集合にクリアする。
- `dunning_store`側の`suspension_reason`も`"cancelled"`に統一する(実運用では
  `cancellation_store`・`store_profile_store`と同一Firestoreドキュメントの同一フィールドに
  収束する想定、既存の`store_profile_store.set_suspension_reason()`呼び出しと同じ考え方)。
- `dunning_store`が渡されない、または当該`store_id`のstateが存在しない場合は何もしない
  (安全側フォールバック、他の分岐と同じ方針)。

新規のストアProtocolは追加せず、既存の`dunning_store`引数(`invoice.payment_failed`/
`invoice.payment_succeeded`分岐で既に受け取っている)をそのまま再利用する。

## 3. 対応しなかった項目

- `subscription_store`(`checkout.session.completed`用、トライアル後の初回プラン選択)は
  対象外。同stateは`payment_failure_detected_at`等を保持しないため本バグの対象外。
- 実LINE Push Message API・実Stripeアカウント接続はいずれもオーナー承認待ち
  (pending-approval.md参照)、本フェーズでは新たに発生していない。

## 4. テスト

`test_stripe_webhook_entry_point.py`の`ReceiveStripeWebhookSubscriptionDeletedTest`に3件
追加。

- `test_dunning_state_is_cleared_independently_of_notification`: 猶予期間中の店舗状態から
  `customer.subscription.deleted`を受信すると、`dunning_store`側の3フィールド
  (`payment_failure_detected_at`・`sent_event_keys`・`suspension_reason`)がすべて
  期待通りに更新されることを、`cancellation_store`/`push_client`を渡さない状態で確認する。
- `test_omitted_dunning_store_skips_clear_without_error`: `dunning_store`未指定時も
  既存の`cancellation_store`/`push_client`経由の処理(`outcome == "cancelled"`)が
  従来通り動くことを確認する(後方互換)。
- `test_dunning_store_with_no_known_state_for_store_id_is_left_untouched`: 当該
  `store_id`のstateが`dunning_store`に存在しない場合、例外を出さずに何もしないことを
  確認する。

venture全体866件(`python3 -m unittest discover -s prototype -p "test_*.py"`、変更前863件+
新規3件)・schema検証28件(`python3 schema/validate_test_cases.py`、変更前と同じ結果)
いずれもパスを確認した。
