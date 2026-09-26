# `customer.subscription.deleted`受信時の決済失敗系状態クリア対応

kura-pashaのフェーズ187(aircon-pashaフェーズ272の横断確認を受けた対応)が「次回以降の
課題」として指摘していた、本ventureの同種ギャップに対応した。

## 1. 元のバグ(aircon-pasha・kura-pashaで先行対応済み)

aircon-pasha・kura-pashaはいずれも、決済失敗検知(`invoice.payment_failed`)から猶予期間中に
`customer.subscription.deleted`(契約終了)が届いた場合、解約完了案内済みの顧客に対して
決済失敗系フィールドが残ったままとなり、後日日次バッチ(`payment_failure_reminder_
scheduler.py`・`payment_suspension_owner_notification.py`等)が既に解約済みの顧客を
誤って再選出し、矛盾したPush通知(リマインド・制限モード移行案内)を送ってしまう理論上の
バグを持っていた。両venture共に`customer.subscription.deleted`受信時に決済失敗系
フィールドをあわせてクリアする対応を行っている。

## 2. 本ventureでの状況

本ventureの`stripe_webhook.dispatch_stripe_event()`の`customer.subscription.deleted`分岐は、
`mark_deletion_candidate_on_subscription_deleted()`(削除候補化)・`user_profile_store`指定時の
`blocked_but_billing_owner_notified_at`クリア(フェーズ144)・`push_client`指定時の解約完了
案内送信(フェーズ155)は行っていたが、`usage_counter`指定時に決済失敗系フィールドを
クリアする配線が欠落していた。

本ventureはaircon-pashaと異なり別立ての`payment_suspended_at`を持たない設計
(payment-failure-dunning-design.md、フェーズ118: 制限モードは検知時刻+猶予日数から
都度算出)のため、クリア対象は次の3フィールドで足りる。

- `payment_failure_detected_at`
- `payment_failure_reminder_sent_at`(フェーズ120で新設)
- `payment_suspension_owner_notified_at`(payment-suspension-owner-notification-design.md)

## 3. 対応方針

`invoice.payment_succeeded`受信時の既存クリア処理(`dispatch_stripe_event()`内、
push_client未指定時の後方互換パス。および`payment_recovery_notification.
handle_payment_succeeded()`)と同じ3フィールドを、`customer.subscription.deleted`分岐でも
`usage_counter.get_payment_failure_detected_at(user_id)`が設定済みの場合のみクリアする形で
対応した。新規のクリア関数は追加せず、既存の`clear_payment_failure_detected_at()`・
`clear_payment_failure_reminder_sent_at()`・`clear_payment_suspension_owner_notified_at()`を
呼び出す。新規引数も追加せず、`invoice.payment_failed`/`invoice.payment_succeeded`向けに
既に受け取っている`usage_counter`引数を再利用した(未指定時はこれまで通りクリアを
行わない後方互換)。

`PaymentFailureUsageCounterProtocol`に`clear_payment_suspension_owner_notified_at()`を
追加した(`InMemoryUsageCounter`は既存メソッドとして実装済み、構造的部分型付けにより
そのまま満たす)。

`StripeDispatchResult`に`payment_failure_cleared_on_deletion_user_ids`フィールドを追加し、
クリアが実際に発生したuser_idを記録する(aircon-pasha・kura-pashaの同名フィールドと同じ
呼び出し側ログ確認用途)。

`receive_stripe_webhook()`は既に`usage_counter`を`dispatch_stripe_event()`へ委譲済みのため、
本対応のみで実HTTPエントリポイント経由でも即座に有効になる(追加配線は不要)。

## 4. 対応しなかった項目

- `deletion_candidate.py`の`deletion_candidate_at`(365日後の削除候補化)は対象外
  (決済失敗系フィールドと削除候補化は独立した状態、aircon-pashaフェーズ272と同じ考え方)。
- `invoice.payment_succeeded`受信時、`push_client`未指定の後方互換パス(454-456行目)は
  `payment_suspension_owner_notified_at`をクリアしていない別の潜在ギャップに見えるが、
  本フェーズのスコープ(`customer.subscription.deleted`受信時の横展開)とは別の問題のため
  対応せず、次回以降の課題として残す。
- 実Stripeアカウント接続はオーナー承認待ち(pending-approval.md参照)、本フェーズでは
  新たに発生していない。

## 5. テスト

`test_stripe_webhook.py`に3件追加。
- `test_subscription_deleted_clears_payment_failure_state_when_usage_counter_provided`:
  3フィールドが設定済みの状態から`customer.subscription.deleted`を受信すると、すべて
  クリアされ`payment_failure_cleared_on_deletion_user_ids`に記録されることを確認する。
- `test_subscription_deleted_payment_failure_state_untouched_when_already_unset`:
  3フィールドが未設定の場合、クリア扱いにならないことを確認する。
- `test_subscription_deleted_payment_failure_state_untouched_when_usage_counter_not_provided`:
  `usage_counter`未指定時は従来通りクリアを行わないことを確認する(後方互換)。

venture全体652件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`、変更前
649件+新規3件)・schema検証21件(`python3 schema/validate_test_cases.py`、変更前と同じ
結果)いずれもパスを確認した。

## 6. 次回候補

- 4節で触れた`invoice.payment_succeeded`後方互換パスの`payment_suspension_owner_notified_at`
  クリア漏れの調査・対応。
- 実Stripeアカウント接続(オーナー承認待ち)、または他venture・アイデア領域の前進。
