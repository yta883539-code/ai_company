# 猶予期間終了直前リマインドを送信する日次スケジューラ設計

作成日: 2026-08-28(フェーズ120)

payment-failure-dunning-design.md「6. 残課題」に残っていた「猶予期間終了直前リマインドを
送信するスケジューラ(trial-end-scheduler-design.mdの日次バッチと同種の仕組みを流用できる
見込みだが、本ドキュメントでは未検討)」を設計する。aircon-pashaの
payment-failure-reminder-scheduler-design.md(フェーズ143)と同じ全体構成を踏襲しつつ、
本venture固有の2点(状態管理が`UsageCounterProtocol`への注入依存であること、CTAが
postbackボタンではなくLIFF経由のプレーンテキストリンクであること)に合わせて翻案する。

## 1. 全体構成

```
Cloud Scheduler(cron、日次1回。trial-end-scheduler-design.mdと同じくJST 04:00を暫定案とし、
同一ジョブから続けて呼び出す想定)
        ↓ HTTPトリガー
Cloud Function E: send_payment_failure_reminders
        ↓
  1) usage_counter(UsageCounterProtocol)から、payment_failure_detected_atが設定済み
     かつ payment_failure_reminder_sent_at が未設定のユーザーを抽出
  2) 抽出結果のうち、now - payment_failure_detected_at が
     [grace_period_days - reminder_days_before_end, grace_period_days) の範囲
     (デフォルト値では[4日, 7日))にあるものを送信対象とする(2節)
  3) payment-failure-dunning-design.md 4節「猶予期間終了直前(3日前リマインド)」の
     プレーンテキストメッセージを組み立てて送信し、
     payment_failure_reminder_sent_at に送信時刻を書き込む
        ↓
  LINE Push Message API(trial_end_scheduler.pyのLinePushClient Protocolをそのまま
  再利用する。送信手段自体はトライアル終了通知と変わらないため新規Protocolは起こさない)
```

trial-end-scheduler-design.mdと同じ理由(Cloud Schedulerの無料枠制限、ユーザー数が増えても
ジョブ数を増やさない)により、本ジョブも**全ユーザー共通の単一日次ジョブ**とする。実際の
GCPプロジェクト上でのジョブ配置(Cloud Function Dと同一関数にまとめるか別関数にするか)は
実インフラ構築時にコスト・運用面から判断すればよく、本ドキュメントの選定ロジック・
スケジューラ構成には影響しない。

## 2. 上限側の条件が必要な理由(aircon-pashaとの違い)

aircon-pashaは`payment_suspended_at`という別立ての状態フィールドを持ち、これが未設定
(=まだ制限モードに入っていない)であることをリマインド対象の条件にできた。本ventureは
フェーズ118の設計判断により制限モードを別フィールドではなく`_is_payment_suspended()`
(検知時刻から`PAYMENT_FAILURE_GRACE_PERIOD_DAYS`日以上経過したかを都度算出)で表現する
ため、同じ判定を`select_due_payment_failure_reminders()`側でも計算する必要がある。

具体的には、経過日数が「7日以上」になった時点で既に制限モードへ移行済みのユーザーへ
リマインドを送っても無意味(既にPAYMENT_SUSPENDED_MESSAGEを受け取っている)であるだけでなく、
猶予期間経過を検知して制限モードへ移行させる別スケジューラ(payment-failure-dunning-design.md
6節に残る別の残課題、本ドキュメントの対象外)が導入されるまでの間、本スケジューラが
「制限モードに入るべきなのに入らず、代わりに何度もリマインドを送り続ける」誤動作を防ぐ
安全策も兼ねる。そのため`select_due_payment_failure_reminders()`の抽出条件には
`now - payment_failure_detected_at < grace_period_days`という上限側の条件を明示的に含める
(aircon-pasha側は`payment_suspended_at is None`という状態フラグの不在で同じ効果を得ていたが、
本ventureは計算のみで同等の安全性を確保する)。

## 3. なぜ新規フィールドが必要か

payment-failure-dunning-design.md 6節でフェーズ119までに追加済みだった状態フィールドは
`payment_failure_detected_at`のみで、「リマインドを送信済みか」を区別する手段がなかった。
trial-end-notification-design.mdの`trial_end_notified_at`と同じ役割の
`payment_failure_reminder_sent_at`フィールドを`UsageCounterProtocol`(cloud_function_webhook.py)
に新設し(get/set)、これを送信済みフラグとして使う。

`clear_payment_failure_detected_at()`呼び出し時(`invoice.payment_succeeded`受信、
stripe_webhook.pyの`dispatch_stripe_event()`)にあわせて本フィールドもクリアするよう
`clear_payment_failure_reminder_sent_at()`を新設し呼び出す。クリアしないと、1回目の決済失敗で
リマインド送信済みのユーザーが決済成功で通常運用に復帰した後、再度決済に失敗した際に
リマインドが二度と送信されなくなってしまうため(aircon-pashaと同じ理由)。

## 4. 選定ロジック(`prototype/payment_failure_reminder_scheduler.py`想定)

`select_due_payment_failure_reminders(users, now, grace_period_days=7, reminder_days_before_end=3)`:
以下すべてを満たすユーザーを抽出する純粋関数として実装する
(trial_end_scheduler.pyの`select_due_trial_end_notifications()`と同じ「時刻の一致ではなく
範囲条件」を採用)。

- `payment_failure_detected_at is not None`
- `payment_failure_reminder_sent_at is None`(1回のみ送信、design 4節)
- `now - payment_failure_detected_at >= timedelta(days=grace_period_days - reminder_days_before_end)`
  (デフォルト値では7-3=4日。「ちょうど4日」ではなく「4日以上」の範囲条件とすることで、
  日次実行の遅延・欠落に自然に耐える設計とする)
- `now - payment_failure_detected_at < timedelta(days=grace_period_days)`
  (2節で述べた上限側の安全策。デフォルト値では7日未満)

## 5. 通知文言・メッセージ形式

trial_end_scheduler.pyの`format_trial_end_notification_message()`と同じくプレーンテキスト
(本ventureはmessage-tone-variants.md相当の複数トーン切り替えを導入しておらず、CTAも
postbackボタンではなくLIFF経由のプレーンテキストリンクを一貫して採用しているため)。

payment-failure-dunning-design.md 4節「猶予期間終了直前(3日前リマインド)」の文言をそのまま
`format_payment_failure_reminder_message(liff_url=LIFF_URL_PLACEHOLDER)`として実装する
(ユーザーごとに変化する値がないため、trial_end_scheduler.pyの通知文言と異なり
引数はliff_urlのみでよい)。`LIFF_URL_PLACEHOLDER`はtrial_end_scheduler.pyで既に定義済みの
定数をそのまま再利用し、本モジュールで重複定義しない。

## 6. 冪等性

- 送信後は`payment_failure_reminder_sent_at`に送信時刻を書き込み、以降の実行では4節の
  抽出条件から自然に除外される(追加のロック機構は不要、trial_end_scheduler.pyと同じ方式)。
- Cloud Functionsが同一ユーザーを複数インスタンスで同時処理する可能性への対策
  (書き込みのトランザクション化)は、trial-end-scheduler-design.md 4節が残した同種の課題と
  同じく実装時の課題として残す。

## 7. 今後の課題

- 猶予期間(7日)経過後に制限モードへ移行させる仕組みは、本ventureは別立てのフィールドを
  持たず`_is_payment_suspended()`の都度算出のみで実現済み(フェーズ118)であり、
  aircon-pashaのような専用スケジューラ(payment_suspension_scheduler.py)は本venture
  では不要と判断する。ただしその場合、制限モードへの移行を検知してオーナーへ知らせる
  能動通知(顧客からのメッセージが届いた際にPAYMENT_SUSPENDED_MESSAGEを返信する受動的な
  経路のみが現状存在)は無いままであり、これは別の残課題として残る。
- 5節で触れたStripe Customer Portal(`PortalLinkProvider`、cloud_function_webhook.py
  501行目)は既にProtocol定義自体は存在するが、決済失敗リマインドの文中リンクを
  「新規Checkout Session(LIFF)」と「既存契約の支払い方法更新(Customer Portal)」の
  どちらにすべきかは、payment-failure-dunning-design.md 5節が指摘したとおり未決着のまま
  次回以降の課題として残す(本ドキュメントは暫定でLIFF_URL_PLACEHOLDERをそのまま使う)。
- 実際のCloud Scheduler実行環境の構築・LINE Push Message API接続は、
  trial-end-scheduler-design.mdと同じくオーナー承認待ちの範囲(pending-approval.md参照)。
  本ドキュメントは選定ロジック・スケジューラ構成の机上設計にとどめる。
