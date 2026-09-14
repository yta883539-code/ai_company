# 日次スケジューラ設計: (B)トライアル30日到達報告・決済失敗3日前リマインド(フェーズ112)

作成日: 2026-09-14(フェーズ112)

trial-end-notification-design.md 6節「今後の課題」と、payment-failure-dunning-design.md
6節「残課題」がそれぞれ独立に残していた「本venture側にまだ存在しない日次スケジューラ
本体」という同一の未着手事項に対応する。両ドキュメントとも、他venture3件
(line-reservation-ai/trial-end-scheduler-design.md・aircon-pasha/course-set-pashaの
trial-end-scheduler-design.md・payment-failure-reminder-scheduler-design.md)に相当する
設計が本venture未着手であることを認識しつつ、本venture固有の低頻度受注特性・LINE公式
アカウント接続前という理由で優先度を下げ、次の課題として持ち越していた。本フェーズでは
その机上設計(選定ロジックのみ、実クラウド接続は対象外)に着手する。

## 1. 対象とする2つの検知を1つの日次ジョブにまとめる理由

両者はいずれも「特定の時刻ちょうどではなく、日次バッチでの範囲条件抽出が必要」という
同じ形の要件であり、対象とするフィールドが異なるだけで抽出パターンが同一
(`WorkshopStoreProtocol`から対象workshopを全件走査し、`now - 基準時刻 >= 閾値`かつ
`送信済みフラグが未設定`のものを抽出)である。他venture3件も同一のCloud Scheduler
ジョブ内で複数の抽出ロジックを続けて呼び出す構成(aircon-pasha/payment-failure-
reminder-scheduler-design.md 6節が示すpayment_suspension_scheduler.pyとの関係と同様)を
採っており、本venture固有の事情(まだ日次バッチ自体が存在しない)を踏まえると、
1つのCloud Functionの中で2つの抽出関数を順に呼ぶ最小構成から始めるのが理にかなう。

## 2. 全体構成

```
Cloud Scheduler(cron、日次1回。他venture3件と同じ理由でJST 04:00を暫定案とする。
実際の時刻確定はLINE公式アカウント接続後の運用開始時に見直す)
        ↓ HTTPトリガー
Cloud Function G: run_daily_workshop_checks
        ↓
  1) WorkshopStoreProtocolから全workshop_idを走査し、各workshopについて
     WorkshopDailyCheckState(3節)を組み立てる
  2) select_due_trial_end_reports()で(B)経路対象を抽出し、
     format_trial_end_notification_message()(trial-end-notification-design.md 3節、
     「浮いた時間」行を省略する分岐)を組み立ててLINE Push送信、trial_end_notified_atを
     書き込む
  3) select_due_payment_failure_reminders()で決済失敗リマインド対象を抽出し、
     PAYMENT_FAILURE_REMINDER_MESSAGE(4節)を組み立ててLINE Push送信、
     payment_failure_reminder_sent_atを書き込む
  4) send_payment_suspension_owner_notifications()(payment-suspension-owner-notification-
     design.md、フェーズ116)を呼び出し、制限モードへ新たに移行したworkshopをオーナーへ
     LINE Push通知する
        ↓
  LINE Push Message API(subscription_cancellation_notification.pyのLinePushClient
  Protocolをそのまま再利用する。送信手段自体は既存の他通知と変わらないため、新規
  Protocolは起こさない)
```

他venture3件と異なり本venture未着手のため、2)(B)経路と3)決済失敗リマインドを
同一関数内で連続実行する形にまとめて最小構成とした(他venture3件はそれぞれ別個の
Cloud Function/スケジューラドキュメントとして独立させているが、本venture固有の
低頻度特性を踏まえ、まずは1つのドキュメント・1つのモジュールで両方を賄う)。

4)は本ドキュメント作成(フェーズ112)より後のフェーズ116で新設された
`payment_suspension_owner_notification.py`が、選定ロジック(`select_due_payment_
suspension_owner_notifications()`)と送信配線(`send_payment_suspension_owner_
notifications()`)の両方を単独で完結させる形で既に実装済みだったため、2)3)のように
`daily_scheduler.py`側へ選定ロジックを複製する必要はなく、Cloud Function G本体から
そのまま呼び出す1行の追加で足りる。フェーズ116時点では本ドキュメントのCloud Function G
構成図(2節)に4)の記載が無く、制限モード移行時のオーナー通知が日次バッチのどこで
呼ばれるのか本ドキュメント上は未定義のままだったため、今回その欠落を埋めた。

## 3. 選定ロジック(`prototype/daily_scheduler.py`)

### 3.1 (B)トライアル30日到達報告

trial-end-notification-design.md 2節の(B)経路をそのままコード化する。

- `WorkshopTrialEndState`(frozen dataclass): `workshop_id`・`trial_start_at`
  (`Optional[datetime]`)・`trial_generation_used`(`bool`)・`trial_end_notified_at`
  (`Optional[datetime]`)。
- `is_trial_end_report_due(state, now, trial_period_days=TRIAL_PERIOD_DAYS)`:
  以下をすべて満たす場合に`True`を返す純粋関数。
  - `trial_start_at is not None`
  - `trial_generation_used is False`((A)経路〈生涯最初の生成完了時に便乗送信〉が
    既に発生済みなら(B)は対象外。2節「(A)が未発生のworkshopに対してのみ検知する」を
    そのまま反映)
  - `trial_end_notified_at is None`(二重送信防止。(A)(B)共通の同一フィールド)
  - `now - trial_start_at >= timedelta(days=trial_period_days)`(「ちょうど30日」ではなく
    「30日以上」の範囲条件とすることで、日次実行の遅延・欠落に自然に耐える。line-
    reservation-ai/trial_end_scheduler.pyと同じ設計判断)
- `select_due_trial_end_reports(states, now, **kwargs)`: `states`のうち
  `is_trial_end_report_due()`が`True`のものだけを抽出するラッパー。

### 3.2 決済失敗3日前リマインド

payment-failure-dunning-design.md 6節が残した課題をそのままコード化する。本venture
固有の事情(PortalLinkProvider相当が未実装、`payment_suspended_at`のような別立て
フラグを持たず経過日数の都度算出方式)を踏まえ、aircon-pasha/payment-failure-
reminder-scheduler-design.mdの`payment_suspended_at is None`条件は使えないため、
代わりに「まだ制限モード〈7日以上経過〉に達していない」ことを経過日数の上限として
明示的に課す。

- `WorkshopPaymentFailureState`(frozen dataclass): `workshop_id`・
  `payment_failure_detected_at`(`Optional[datetime]`)・
  `payment_failure_reminder_sent_at`(`Optional[datetime]`)。
- `is_payment_failure_reminder_due(state, now, grace_period_days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS, reminder_days_before_end=PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END)`:
  以下をすべて満たす場合に`True`を返す純粋関数。
  - `payment_failure_detected_at is not None`
  - `payment_failure_reminder_sent_at is None`(1回のみ送信)
  - `now - payment_failure_detected_at >= timedelta(days=grace_period_days - reminder_days_before_end)`
    (デフォルト値では7-3=4日)
  - `now - payment_failure_detected_at < timedelta(days=grace_period_days)`(既に制限モード
    〈7日以上経過〉に達しているworkshopには今更「3日前」リマインドを送らない。
    `payment_suspended_at`という別立てフラグを持たない本venture固有の代替条件で、
    aircon-pasha版の`payment_suspended_at is None`条件と同じ意図を経過日数の範囲で表現する)
- `select_due_payment_failure_reminders(states, now, **kwargs)`: 上記の抽出ラッパー。

## 4. 通知文言

決済失敗3日前リマインド(新規、他venture3件と異なりFlex Message・ボタンではなく
プレーンテキスト。payment-failure-dunning-design.md 1節の「PortalLinkProvider相当が
未実装」という前提を踏襲):

```
【鞍パシャッと】お支払いのご確認まもなく期限です

いつもご利用ありがとうございます。
お支払い手続きが完了できないまま、まもなく一時停止の期限を迎えます。
このままお支払い方法のご確認・更新がない場合、受注内容整理メモ・納品案内・
お手入れ案内の生成を一時停止させていただきます。

お手数ですが、ご利用中の決済手続き時にご案内した画面からお支払い方法をご確認
いただけますようお願いします。
```

(B)トライアル30日到達報告は、trial-end-notification-design.md 3節の通知文言をそのまま
使う(「浮いた事務作業時間の目安」行を省略する分岐、同ドキュメント3節に既記載のため
本ドキュメントでは再掲しない)。

## 5. 実装状況(本フェーズ)

- `WorkshopStoreProtocol`(prototype/usage_counter_workshop.py)へ
  `get_payment_failure_reminder_sent_at`/`set_payment_failure_reminder_sent_at`の2メソッドを
  新設した(命名は既存の`get_trial_end_notified_at`と同スタイル)。`InMemoryWorkshopStore`
  にも実装した。
- `clear_payment_failure_detected_at()`実行時(決済成功による復旧、payment_failure_
  notification.pyの`handle_payment_succeeded()`)にあわせて`payment_failure_reminder_sent_at`
  もクリアするよう拡張した。aircon-pasha版と同じ理由(1回目の決済失敗でリマインド送信済みの
  workshopが、決済成功で復旧した後に再度決済失敗した際、リマインドが二度と送信されなく
  なることを防ぐ)。
- `prototype/daily_scheduler.py`(新規)に3節の`WorkshopTrialEndState`/
  `is_trial_end_report_due()`/`select_due_trial_end_reports()`・
  `WorkshopPaymentFailureState`/`is_payment_failure_reminder_due()`/
  `select_due_payment_failure_reminders()`を実装した。`PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END = 3`
  定数、4節のリマインド文言(`PAYMENT_FAILURE_REMINDER_MESSAGE`)を定義した。
- 実際のCloud Function本体(`run_daily_workshop_checks`、2節)・LINE Push送信配線・
  `WorkshopStoreProtocol`からのworkshop全件走査(Firestore相当の集計クエリ)は、
  実LINE公式アカウント接続・Cloud Scheduler実行環境の構築がオーナー承認待ちのため、
  本フェーズでは選定ロジック(純粋関数)の実装・テストにとどめる。

## 6. 残る課題

- 2節のCloud Function本体・LINE Push送信配線・全workshop走査ロジックの実装は、
  実LINE公式アカウント接続・Cloud Scheduler実行環境の構築がオーナー承認待ちのため
  次回以降の課題として残す(pending-approval.md参照)。4)の
  `send_payment_suspension_owner_notifications()`呼び出しも同じ理由で未配線。
- JST 04:00という実行時刻は他venture3件からの暫定踏襲であり、本venture固有の
  最適な実行時刻(受注が発生しやすい時間帯を避ける等)は実運用データを見てから
  再検討する。
- 猶予期間7日・リマインド3日前という値は、他venture共通で実測データの無い暫定値の
  ままであり、trial_period_days=30日についても同様(既存の暫定値をそのまま踏襲した
  だけで、本フェーズでは再検証していない)。

最終更新: 2026-09-14 14:00 UTC(フェーズ117: フェーズ116で新設された
`payment_suspension_owner_notification.py`〈制限モード移行時のオーナー通知〉を、
2節のCloud Function G構成へ4)として組み込んだ。選定ロジック・送信配線とも当該
モジュール側で完結済みのため`daily_scheduler.py`への複製は不要、design docの統合
記述のみで対応。実クラウド配線は引き続き次の課題)

- フェーズ112(2026-09-14 00:00 UTC): trial-end-notification-design.md 6節・
  payment-failure-dunning-design.md 6節がそれぞれ残していた日次スケジューラ本体の
  机上設計に着手。(B)トライアル30日到達報告・決済失敗3日前リマインドの選定ロジックを
  `prototype/daily_scheduler.py`として実装、`payment_failure_reminder_sent_at`フィールドを
  新設。実際のCloud Function配線・Push送信は引き続き次の課題
- フェーズ117(2026-09-14 14:00 UTC): 上記の通り、フェーズ116のオーナー通知モジュールを
  2節の構成図へ統合
