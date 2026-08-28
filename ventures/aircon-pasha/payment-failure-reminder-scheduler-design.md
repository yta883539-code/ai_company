# 猶予期間終了直前リマインドを送信する日次スケジューラ設計

作成日: 2026-08-28(フェーズ143)

payment-failure-dunning-design.md「6. 残課題」に残っていた「猶予期間終了直前リマインドを
送信するスケジューラ(trial-end-scheduler-design.mdの日次バッチと同種の仕組みを流用できる
見込みだが、本ドキュメントでは未検討)」を設計する。trial-end-scheduler-design.md
(フェーズ133)の全体構成をそのまま踏襲し、対象イベント・選定条件・通知文言のみを
payment-failure-dunning-design.md 4節「猶予期間終了直前(3日前リマインド、1回のみ)」に
差し替える。

## 1. 全体構成

```
Cloud Scheduler(cron、日次1回。trial-end-scheduler-design.mdと同じ理由でJST 04:00を
暫定案とし、同一ジョブから続けて呼び出す想定)
        ↓ HTTPトリガー
Cloud Function F: send_payment_failure_reminders
        ↓
  1) user_profileストア(UserProfileStoreProtocol)から、payment_failure_detected_at
     が設定済み かつ payment_suspended_at が未設定(まだ制限モードに移行していない)
     かつ payment_failure_reminder_sent_at が未設定のユーザーを抽出
  2) 抽出結果のうち、now - payment_failure_detected_at >= 猶予期間7日 - リマインド
     日数3日 = 4日 のものを送信対象とする(design 3節)
  3) payment-failure-dunning-design.md 4節「猶予期間終了直前(3日前リマインド)」の
     通知メッセージ(postbackボタン付きFlex Message)を送信し、
     payment_failure_reminder_sent_at に送信時刻を書き込む
        ↓
  LINE Push Message API(trial_end_scheduler.pyのLinePushClient Protocolと同じ
  ものをそのまま再利用する。送信手段自体はトライアル終了通知と変わらないため、
  新規Protocolは起こさない)
```

trial-end-scheduler-design.mdと同じ理由(Cloud Schedulerの無料枠制限、ユーザー数が
増えてもジョブ数を増やさない)により、本ジョブも**全ユーザー共通の単一日次ジョブ**とする。
実際のGCPプロジェクト上でのジョブ配置(既存のCloud Function Eと同一関数にまとめるか、
別関数にするか)は、両ジョブとも「対象抽出→Flex Message送信→フラグ書き込み」という
同じ形をしているだけで対象フィールドが異なるため、実インフラ構築時にコスト・運用面から
判断すればよく、本ドキュメントの選定ロジック・スケジューラ構成には影響しない。

## 2. なぜ新規フィールドが必要か

payment-failure-dunning-design.md 6節でフェーズ140までに追加済みだった状態フィールドは
`payment_failure_detected_at`(猶予期間開始)・`payment_suspended_at`(制限モード移行、
フェーズ144以降の別スケジューラが書き込む想定)の2つのみで、「リマインドを送信済みか」を
区別する手段がなかった。trial-end-notification-design.mdの`trial_end_notified_at`と
同じ役割の`payment_failure_reminder_sent_at`フィールドを新設し(user_id_linking.py・
フェーズ143)、これを送信済みフラグとして使う。

`payment_failure.py`の`clear_payment_failure_on_success()`(`invoice.payment_succeeded`
受信時)は、`payment_failure_detected_at`・`payment_suspended_at`に加えて本フィールドも
あわせてクリアするよう拡張した(フェーズ143)。クリアしないと、1回目の決済失敗でリマインド
送信済みのユーザーが、決済成功で通常運用に復帰した後、再度決済に失敗した際にリマインドが
二度と送信されなくなってしまうため。

## 3. 選定ロジック(`prototype/payment_failure_reminder_scheduler.py`想定)

- `select_due_payment_failure_reminders(users, now, grace_period_days=7, reminder_days_before_end=3)`:
  以下すべてを満たすユーザーを抽出する純粋関数として実装する(trial_end_scheduler.pyの
  `select_due_trial_end_notifications()`と同じ「時刻の一致ではなく範囲条件」を採用)。
  - `payment_failure_detected_at is not None`
  - `payment_suspended_at is None`(既に制限モードへ移行済みならリマインドは不要、
    PAYMENT_SUSPENDED_MESSAGEが既に案内済みのため)
  - `payment_failure_reminder_sent_at is None`(1回のみ送信、design 2節)
  - `now - payment_failure_detected_at >= timedelta(days=grace_period_days - reminder_days_before_end)`
    (デフォルト値では7-3=4日。「ちょうど4日」ではなく「4日以上」の範囲条件とすることで、
    日次実行の遅延・欠落に自然に耐える設計とする)
- `payment_suspended_at`を書き込む猶予期間経過検知スケジューラ(制限モードへの自動移行、
  payment-failure-dunning-design.md 6節に残る別の残課題)が将来実装されても、本関数は
  `payment_suspended_at is None`条件により自動的にそのユーザーを対象から除外する
  (「制限モードに入ったユーザーへは今更リマインドを送らない」という設計をそのまま反映)。

## 4. 通知文言・メッセージ形式

trial_end_scheduler.pyのbuild_trial_end_notification_flex_message()と同じく、本venture
固有のpostbackボタン方式(checkout-initiation-flow-design.md、design 5節)のため、
プレーンテキストではなくボタン付きのFlex Messageとして組み立てる
(`build_payment_failure_reminder_flex_message()`)。

- 本文はpayment-failure-dunning-design.md 4節「猶予期間終了直前(3日前リマインド)」の
  文言をベースに、`GENERATION_PAUSED_MESSAGE`・`PAYMENT_SUSPENDED_MESSAGE`
  (cloud_function_webhook.py)と同じく、本文中に生URLを埋め込まずボタン(postback)を
  別途添付する短縮形に揃える。
- ボタンのlabel・postbackデータは、既存の`UPDATE_PAYMENT_METHOD_BUTTON_LABEL`・
  `UPDATE_PAYMENT_METHOD_POSTBACK_DATA`(cloud_function_webhook.py、フェーズ141〜142で
  制限モード案内向けに導入済み)をそのまま再利用する。同じボタンから遷移した
  `process_postback_event()`側のStripe Customer Portal遷移ロジック
  (`portal_link_provider.get_portal_url()`、フェーズ142)は変更不要。

## 5. 冪等性

- 送信後は`payment_failure_reminder_sent_at`に送信時刻を書き込み、以降の実行では3節の
  抽出条件から自然に除外される(追加のロック機構は不要、trial_end_scheduler.pyと同じ方式)。
- Cloud Functionsが同一ユーザーを複数インスタンスで同時処理する可能性への対策
  (書き込みのトランザクション化)は、trial-end-scheduler-design.md 4節が残した同種の
  課題と同じく実装時の課題として残す。

## 6. 今後の課題

- ~~猶予期間(7日)経過後に制限モードへ自動移行させるスケジューラ本体
  (`payment_suspended_at`への書き込み配線、payment-failure-dunning-design.md 6節に
  残る別の残課題)は本ドキュメントの対象外。実装時は本モジュールと同じ抽出パターン
  (`now - payment_failure_detected_at >= timedelta(days=7)`かつ`payment_suspended_at
  is None`)を使い、同じ日次ジョブ内で本モジュールの後に実行する構成を想定する。~~ →
  フェーズ145で対応済み。`prototype/payment_suspension_scheduler.py`に
  `select_due_payment_suspensions()`(本モジュールと同じ抽出パターン)・
  `build_payment_suspension_flex_message()`(本文はcloud_function_webhook.pyの
  `PAYMENT_SUSPENDED_MESSAGE`をそのまま再利用し、Push通知とリプライ時の案内文言を
  一致させた)・`send_payment_suspensions()`を実装した。テスト12件追加、venture全体
  275件全件パス・schema検証9件パスを確認した。
- design 4節末尾で触れた「猶予期間中に決済が成功した場合の復旧通知の3分岐」の文言出し分けは
  引き続き次回以降の課題として残る。
- 実際のCloud Scheduler実行環境の構築・LINE Push Message API接続は、trial-end-
  scheduler-design.mdと同じくオーナー承認待ちの範囲(pending-approval.md参照)。
  本ドキュメントは選定ロジック・スケジューラ構成の机上設計にとどめる。
