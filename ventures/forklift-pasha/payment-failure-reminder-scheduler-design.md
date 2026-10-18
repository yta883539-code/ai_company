# 決済失敗リマインド送信・運営者向け通知 設計(フェーズ169)

payment-failure-dunning-design.md(フェーズ167)6節「残課題」のうち、本モジュールの対象外と
明記していた「リマインド送信スケジューラ・運営者向け通知」に対応する。他venture4件の
`payment_failure_reminder_scheduler.py`と同じ役割だが、本venture固有の2点を反映する。

- 本ventureは`subscription_status`列挙値や`payment_suspended_at`フィールドを持たず、
  `is_payment_suspended()`(payment_failure.py)による都度計算方式のため、「既に制限モードに
  移行済みか」の判定も同関数の呼び出しで行う(他venture4件は`payment_suspended_at`の
  有無で判定)。
- 顧客接点がLINEではなくメールのため、送信クライアントは`trial_end_email_scheduler.py`の
  `EmailSenderClient`/`InMemoryEmailSenderClient`/`EmailDeliveryError`をそのまま再利用する
  (他venture4件のように`LinePushClient`を新規モジュールごとに再定義しない。送信手段は
  venture内で1つしかないため、重複定義は不要と判断)。

## 1. 顧客向けリマインド(猶予期間3日前)

対象: 以下すべてを満たす`internal_id`。

- `upgraded_at`が設定済み(有料転換後)
- `canceled_at`が未設定
- `payment_failure_detected_at`が設定済み
- `is_payment_suspended(internal_id, now, store)`がFalse(既に制限モードへ移行済みなら
  リマインドは不要、是正ではなく`PAYMENT_SUSPENDED_NOTICE`側の役割)
- `payment_failure_reminder_sent_at`が未設定(1回のみ送信)
- `now - payment_failure_detected_at >= grace_period_days(7) - reminder_days_before_end(3)`
  日(=4日以上経過。「ちょうど」ではなく「以上」とし日次実行の遅延・欠落に耐える、
  `trial_end_email_scheduler.is_trial_end_email_due()`と同じ考え方)

送信成功時のみ`payment_failure_reminder_sent_at`を設定する(失敗時は次回実行時に自然に
再試行対象として残る、既存の全送信バッチと同じ冪等性方針)。

## 2. 運営者向け通知(制限モード移行時)

対象: `is_payment_suspended()`がTrueかつ`payment_suspension_owner_notified_at`が未設定の
`internal_id`。送信先は運営者(本AI Companyのオーナー)固定の通知用メールアドレスで、
`blocked-but-billing-owner-notification-design.md`(aircon-pasha)と同じく実際の宛先決定は
実メール送信接続時のオーナー承認待ちの範囲に含まれるため、新たな承認待ち事項としては
扱わない(pending-approval.mdへの追記は不要)。本モジュールでは
`OWNER_NOTIFICATION_EMAIL_PLACEHOLDER`として独立した定数で表す。

送信成功時のみ`payment_suspension_owner_notified_at`を設定する(同上の冪等性方針)。
`payment_failure_detected_at`がクリアされ再度決済失敗が発生した場合は、呼び出し側
(本モジュール未実装の次回課題)で両フラグをクリアし次サイクルで再送信できるようにする
想定(フィールド自体は`None`書き込みに対応済み)。

## 3. 残課題

- 決済失敗解消時(`clear_payment_failure_on_success()`)に本モジュールの2フラグを
  クリアする呼び出し配線は、フェーズ170で実装済み(`payment_failure.py`
  `clear_payment_failure_on_success()`参照)。
- Cloud Function/Cloud Scheduler呼び出し元は、フェーズ171で
  `payment_failure_reminder_scheduler.run_due_payment_failure_reminders()`/
  `run_due_payment_suspension_owner_notifications()`(`store.all_internal_ids()`による
  全事業者列挙込みのwrapper)、およびそれらを1回のHTTPトリガーでまとめて起動する
  `cloud_function_send_payment_failure_reminders.py`(`cloud_function_send_trial_end_emails.py`
  と対称の依存注入構成)として実装済み。
- 実際のCloud Scheduler設定(日次トリガーの登録)・実メール送信接続はオーナー承認待ち
  (pending-approval.md 2026-10-10 18:00 UTC記載の範囲に含まれる)。承認・実接続までは
  `get_payment_failure_reminder_runtime_dependencies()`がInMemory実装を返す(本番運用は
  未開始)。
