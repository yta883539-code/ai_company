# 前日リマインド経路の呼び出し元設計(Cloud Function C: send_reminders)

## 位置づけ
README.mdの「次にやること(候補)」に残っていた(c)前日リマインド経路の呼び出し元を設計する。
`format_reminder_message()`(engine.py)は既に実装済みだが、これを「いつ・どの予約に対して」
呼び出すかという発火側(スケジューラ)は未設計だった。他のCloud Function(A: receive_webhook、
B: process_conversation_event)と同じく、実際のGCPプロジェクト作成・Cloud Scheduler設定
(アカウント作成に該当、オーナー承認待ち)とは切り離せる**判断ロジック自体**を先に実行可能な
コードに落とし込む。

## 全体構成

```
Cloud Scheduler(cron、例: */15 * * * *)
        ↓ HTTPトリガー
Cloud Function C: send_reminders
        ↓
  1) 全店舗の confirmed かつ archivedAt == null な予約(firestore-data-model.md
     conversations コレクション)を読み取り
  2) 初回リマインドが未送信(reminderSentAt == null)のものについて、
     compute_initial_reminder_target() で算出した目標送信時刻が現在時刻を過ぎていれば送信対象とする
  3) 初回リマインド送信済み・当日中・未返信のものについて、当日朝の再送要否を判定する
        ↓
  LINE Push Message API(cloud_function_process_event.pyのLinePushClientプロトコルを再利用)
```

1店舗1Cloud Schedulerジョブではなく、**全店舗共通の単一ジョブ**が定期的(15分間隔を暫定案とする)に
起動し、店舗ごとの目標時刻と現在時刻を突き合わせて対象を抽出する方式を採用した。
理由: Cloud Schedulerは無料枠が3ジョブまでであり、店舗数分のジョブを作るとpricing-plan.mdの
想定顧客数(将来的に数十〜百店舗規模)に対してスケールしない。単一ジョブ+Firestoreクエリで
判定する方式なら、店舗数が増えてもジョブ数は増えない。

## 冪等性の設計(スケジューラの遅延・再起動に耐える)

`reminder-timing-and-resend-rules.md`のタイミングルールは「店舗ごとの目標時刻」という
*点*を扱っているが、Cloud Schedulerは15分間隔で*離散的に*起動するため、「目標時刻ちょうど」に
一致することはまず無い。また、Cloud Functionsの一時的な障害でスケジューラの実行が
数回スキップされる可能性もある。そこで、時刻の一致判定ではなく次のシンプルな条件を採用した。

- 初回リマインド: `reminderSentAt == null AND target_datetime <= now AND 予約日 > 今日`
  (「目標時刻を過ぎていて、まだ送っておらず、予約当日をまだ迎えていない」の3条件のみ。
  厳密な時刻の一致を要求しないことで、スケジューラの遅延・欠落に対して自然に追いつける)
- 送信後は`reminderSentAt`に送信時刻を書き込み、次回以降の実行では対象から除外する
  (Firestoreの読み取り→送信→書き込みは単一予約単位のため、webhook-async-processing-design.mdの
  Cloud Tasks重複排除のような追加の仕組みは不要。ただし将来Cloud Functionsが同一予約を
  複数インスタンスで同時処理する可能性はゼロではないため、書き込みをトランザクション化する
  (firestore-transaction-design.md準拠)ことを実装時の課題として残す)
- 再送も同様に`resendSentAt`で冪等性を担保する。

## 実装したもの(`prototype/reminder_scheduler.py`)

- `compute_initial_reminder_target(booking_date, store_config)`:
  reminder-timing-and-resend-rules.mdのルール1をそのままコード化。
  - 予約日の前日を起点に、`closed_weekdays`に該当する限り前営業日へ遡る
    (無限ループ防止のため最大7日分のみ遡り、7日連続定休日という異常設定は
    `BusinessHoursConfigError`と同様の例外を送出する)。
  - 店舗が`reminder_time_minutes`を明示設定していればそれを採用、未設定時は
    その営業日の営業終了時刻(`weekday_business_hours`優先、無ければ`business_hours`。
    engine.pyの`_normalize_business_hour_ranges()`をそのまま再利用)の1時間前、
    ただし20:00を上限とする値をデフォルトとする。
- `should_send_initial_reminder(target_datetime, confirmed_at)`:
  ルール2(確定時点で目標送信時刻を過ぎている場合は前日リマインドを送らず確定メッセージで代用)
  の判定。予約確定処理(Cloud Function B)側で確定直後に呼び出して`reminderSkipped`を
  立てる用途と、スケジューラ側で二重チェックする用途の両方を想定した共通関数にした。
- `select_due_initial_reminders(bookings, now)`:
  上記「冪等性の設計」の3条件で対象を抽出する。
- `select_due_resends(bookings, now, business_open_minutes=9*60)`:
  ルール3(再送は当日朝1回のみ、返信なしの場合、当日午前9時より前の予約は対象外)の判定。
  `customer_replied_at`が設定されている(=返信あり)予約は対象から除外する。

## 未解決のまま残る課題

- ~~**顧客からの返信検知の配線**~~ (解消済み 2026-08-02 15:00 UTC:
  customer-reply-detection-design.md参照。confirmed状態の会話へメッセージが届いた事実を、
  内容を問わずCloud Function B(process_conversation_event)の`process()`冒頭で
  `ConfirmedReplyRecorder`プロトコル経由で記録する設計とし、
  prototype/cloud_function_process_event.pyに実装した。confirmed状態からのnew_booking
  intentは引き続き新規予約フローとして扱う既存仕様のままとし、cancel/change intentの
  実処理は別課題として残した)
- ~~Firestoreの`conversations`ドキュメントに`reminderSentAt`/`reminderSkipped`/
  `resendSentAt`/`customerRepliedAt`の4フィールドを追加する必要がある
  (firestore-data-model.mdに反映済み、実装は未着手)。~~
  (訂正 2026-08-21 23:00 UTC: 「実装は未着手」は誤り。4フィールドは`prototype/
  reminder_scheduler.py`の`ReminderBooking`データクラス(`reminder_sent_at`/
  `reminder_skipped`/`resend_sent_at`/`customer_replied_at`)として本ドキュメント作成と
  同じフェーズ(続き40、2026-08-01頃)で既に実装済みで、`prototype/
  cloud_function_send_reminders.py`が`reminder_sent_at`/`resend_sent_at`への書き込みを
  行っている(コード確認済み)。未着手のまま残るのは、この4フィールドを実際のFirestore
  ドキュメントとして読み書きする接続自体(GCPプロジェクト作成・オーナー承認待ち)のみ。
  webhook-function-a-implementation.md・owner-settings-wireframe.md等の過去の同種の
  訂正に倣い、以後この項目を「実装は未着手」として再掲しないこと)
- ~~選定ロジック(reminder_scheduler.py)とメッセージ整形(engine.pyのformat_reminder_message()/
  format_reminder_resend_message())・LinePushClientでの実送信を実際につなぐ配線~~
  (解消済み 2026-08-08 10:00 UTC: `prototype/cloud_function_send_reminders.py`
  新規作成。`send_reminders(bookings, now, stores, push_client)`が
  select_due_initial_reminders()/select_due_resends()の抽出結果に対して候補ラベルを
  組み立て(前日リマインドは日付+曜日+時刻、当日再送は時刻のみ)、店舗設定の
  `message_tone`でトーンを適用したメッセージを送信する。送信失敗
  (`LinePushDeliveryError`)時は`reminder_sent_at`/`resend_sent_at`を更新せず、
  次回起動時に自然に再送対象として拾われる冪等設計を維持した。
  `StoreReminderConfig`に`message_tone`、`ReminderBooking`に`line_user_id`/`menu`を
  新規フィールドとして追加(テスト8件新規・全181件パス)。
  Firestore連携・実LINE API接続は引き続き未着手)
- LINE Push Message APIの実送信、Cloud Schedulerジョブの実作成は「アカウント作成」
  「支払い」に該当するため、着手時に改めてオーナー承認が必要(pending-approval.md参照)。
- ~~Cloud Scheduler起動間隔(暫定15分)が、pricing-plan.mdの想定トラフィックにおける
  Cloud Functions実行回数課金(hosting-platform-selection.md参照)に与える影響の試算は未着手。~~
  (解消済み 2026-08-04 05:00 UTC: cloud-scheduler-invocation-cost-estimate.md参照。
  Function Cの呼び出しは店舗数に依存せず月2,880回程度で無料枠200万回の0.15%程度、
  起動間隔の選定は課金額でなくリマインド遅延許容度を基準にしてよいと結論)
