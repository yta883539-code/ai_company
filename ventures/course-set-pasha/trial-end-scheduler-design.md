# トライアル期間到達判定用の日次スケジューラ設計(条件B)

作成日: 2026-08-23(フェーズ102)

trial-end-notification-design.md「5. 今後の課題」で未着手のまま残っていた、条件(B)
「`trial_start_at`から14日経過」を検知するための日次スケジューラ本体を設計する。
line-reservation-ai/reminder-scheduler-design.md・aircon-pasha/dormant-mode-scheduler
(便乗ではなく日次バッチで全ユーザーを走査する方式)の構成を踏襲する。

## 1. 全体構成

```
Cloud Scheduler(cron、日次1回。時刻は無料トライアル解約時の「ちょうど14日」を厳密に
守る必要はないため深夜帯、例: JST 04:00を暫定案とする)
        ↓ HTTPトリガー
Cloud Function D: send_trial_end_notifications
        ↓
  1) usage_counterストア(Firestoreコレクション、tech-stack.md想定)から、
     trial_start_at が設定済み かつ trial_end_notified_at が未設定 かつ
     upgraded_at も未設定(2節参照)のユーザーを抽出
  2) 抽出結果のうち、now - trial_start_at >= 14日 のものを送信対象とする
  3節の通知メッセージ(trial-end-notification-design.md 3節)を送信し、
     trial_end_notified_at に送信時刻を書き込む
        ↓
  LINE Push Message API(line-reservation-ai/cloud_function_send_reminders.pyと
  同じLinePushClientプロトコルの流用を想定)
```

line-reservation-ai/reminder-scheduler-design.mdの「1店舗1ジョブではなく全店舗共通の
単一ジョブ」という設計判断と同じ理由(Cloud Schedulerの無料枠3ジョブ制限、ユーザー数が
増えてもジョブ数を増やさない)で、本ventureも**全ユーザー共通の単一日次ジョブ**とする。

## 2. 「有料転換済みユーザーの除外」という残課題への対応方針

条件(B)の対象は「トライアル中で、かつ期間が到達したユーザー」に限定する必要があるが、
現時点のcourse-set-pasha prototypeには「有料転換済みかどうか」を判定するフィールドが
usage_counter・他のいずれのストアにも存在しない(stripe_webhook.pyはCheckout Session
完了イベントの受信・ディスパッチまでは実装済みだが、受信後にusage_counter側へ
「有料転換済み」を書き込む処理は本ventureで未実装のまま)。

本設計では、この既存ギャップをそのまま引き継がず、trial_start_at・trial_end_notified_at
と同じ`UsageCounterProtocol`上に`upgraded_at: Optional[datetime]`フィールドを追加する
案を採用した。Stripe Webhookの`checkout.session.completed`ディスパッチ
(stripe_webhook.py `handle_checkout_session_completed()`)完了時に、trial_start_atと
同じ「未設定なら1回だけ書き込む」冪等パターンで`upgraded_at`を設定する
(解消済み・フェーズ103: `UsageCounterProtocol`/`InMemoryUsageCounter`に
`set_upgraded_at_if_unset()`/`get_upgraded_at()`を追加し、
`handle_checkout_session_completed()`に`usage_counter`引数(省略可、後方互換)を追加して
配線した。`stripe_webhook.py`は`cloud_function_webhook.py`を直接importせず独立性を
保つ設計方針だったため、構造的部分型付け用の最小限のProtocol
(`UpgradedAtWriterProtocol`)をstripe_webhook.py側に新設して満たす形にした。
`get_stripe_runtime_dependencies()`のみ`InMemoryUsageCounter()`をimportして生成・共有する
(store・user_profile_storeと同じくプロセス起動ごとの初期化のため、実Firestore接続までは
LINE側インスタンスとは別物である既知の限界が残る)。テスト5件追加、
course-set-pasha配下計268件パス)。本フェーズ時点で以下2点が固まっている。

- 選定ロジック(3節)は`upgraded_at is not None`のユーザーを対象から除外する形で
  実装する(フィールドが存在する前提でロジックを先に書き、実際の書き込み配線は
  stripe_webhook.py側の次回以降の課題として残す)。
- 万一`upgraded_at`書き込み配線が未接続のまま条件(B)が先に稼働した場合の安全策として、
  4節の送信対象判定は「trial_end_notified_atが未設定」であることも独立した必要条件とする
  (=有料転換済みでも通知自体は誤送信されうるが、二重送信は起きない)。この誤送信
  (有料転換済みユーザーへの「トライアル終了」通知)自体は、upgraded_at配線が完了する
  までの暫定的な既知の限界としてREADMEに明記する。

## 3. 選定ロジック(`prototype/trial_end_scheduler.py`)

- `select_due_trial_end_notifications(users, now, trial_period_days=14)`:
  以下すべてを満たすユーザーを抽出する純粋関数として実装する(Firestoreクエリへの
  変換は「trial_start_at <= (now - 14日) の範囲クエリ + trial_end_notified_at ==
  null の等価クエリ」の複合インデックスで表現可能、reminder-scheduler-design.mdの
  `select_due_initial_reminders()`と同じく「時刻の一致ではなく範囲条件」を採用し
  スケジューラの実行遅延・欠落に自然に耐える設計とする)。
  - `trial_start_at is not None`
  - `trial_end_notified_at is None`
  - `upgraded_at is None`
  - `now - trial_start_at >= timedelta(days=trial_period_days)`
- 条件(A)(生成回数5回到達)側の実装(process_memo_event相当、本ventureでは
  未着手)が将来`trial_end_notified_at`を書き込むようになれば、本関数は自動的に
  そのユーザーを対象から除外する(trial-end-notification-design.md 2節「いずれか
  早い方で1回のみ送信」の設計をそのまま反映する形になる)。

## 4. 冪等性

- 送信後は`trial_end_notified_at`に送信時刻を書き込み、以降の実行では3節の抽出条件から
  自然に除外される(reminder-scheduler-design.mdと同じ「書き込み一発+次回実行時に
  自然に対象から外れる」方式。追加のロック機構は不要)。
- Cloud Functionsが同一ユーザーを複数インスタンスで同時処理する可能性への対策
  (書き込みのトランザクション化)は、reminder-scheduler-design.mdが残した同種の
  課題と同じく実装時の課題として残す(firestore-transaction-design.md準拠を想定)。

## 5. 今後の課題

- (解消済み・フェーズ130: 3節`select_due_trial_end_notifications()`が受け取る
  `TrialUserState`のリストは、これまで各テスト・`_demo()`内で手動構築されるのみで、
  実際の`UsageCounterProtocol`実装(`InMemoryUsageCounter`等)から読み取って組み立てる
  関数が存在しなかった(=2節の`upgraded_at`書き込み配線が完了していても、それを
  スケジューラ側の抽出条件へ実際に反映する経路が未接続だった)。`trial_end_scheduler.py`に
  `build_trial_user_states(usage_counter, user_ids)`を新設し、
  `stripe_webhook.handle_checkout_session_completed()`が書き込む`upgraded_at`が
  同一の`InMemoryUsageCounter`インスタンス経由で`select_due_trial_end_notifications()`の
  除外条件に実際に反映されることを確認する結線テスト
  (`StripeWebhookUpgradedAtToTrialEndSchedulerWiringTest`)を追加した。テスト4件追加。
  呼び出し元(実運用ではFirestoreクエリ結果のuser_id一覧を渡す想定)の実装は
  引き続き範囲外)
- (解消済み・フェーズ103: `upgraded_at`フィールドの実装(stripe_webhook.py
  `handle_checkout_session_completed()`への書き込み配線)。詳細は2節参照。実Firestore接続
  後にLINE側・Stripe側で同一インスタンスを共有できるようにする点のみ引き続き残る)
- (解消済み・フェーズ104: Cloud Function D(`send_trial_end_notifications`)自体の実装
  〈3節の選定ロジックとtrial-end-notification-design.md 3節のメッセージ整形・
  LinePushClient送信の配線〉を`prototype/trial_end_scheduler.py`で行った。本venture向けに
  `LinePushClient`/`InMemoryLinePushClient`/`LinePushDeliveryError`を新規定義し、送信成功時
  のみ`usage_counter.set_trial_end_notified_at()`(新設)を書き込む冪等性設計とした。通知
  文面中の「○回」「○分」は試算値自体が未作成のためプレースホルダのまま残る。テスト9件追加。
  詳細はcourse-set-pasha/README.mdフェーズ104参照)
- 実際のCloud Scheduler新規作成はGCPプロジェクトの課金設定を伴うため、
  引き続きオーナー承認待ちの範囲(pending-approval.md 2026-08-23 09:00 UTC記載分参照、
  本件も同一の承認事項でまとめて扱う想定)。
- trial-end-notification-design.md 4節で範囲外とした「トライアル終了後の生成一時停止」
  判定の実装は本ドキュメントでも引き続き範囲外。
