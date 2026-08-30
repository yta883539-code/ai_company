# トライアル期間到達判定用の日次スケジューラ設計(条件B)

作成日: 2026-08-28(フェーズ133)

trial-end-notification-design.md「6. 今後の課題」に残っていた、条件(B)「トライアル開始
(初回生成成功時)から14日経過」を検知するための日次スケジューラ本体を設計する。
course-set-pashaのtrial-end-scheduler-design.md(フェーズ102〜104)・
line-reservation-aiのreminder-scheduler-design.mdの構成を踏襲しつつ、本venture固有の
差分(postbackボタン方式のCTA、LIFF不要)を反映する。

## 1. 全体構成

```
Cloud Scheduler(cron、日次1回。course-set-pashaと同様に厳密な時刻一致は不要なため
深夜帯、JST 04:00を暫定案とする)
        ↓ HTTPトリガー
Cloud Function E: send_trial_end_notifications
        ↓
  1) user_profileストア(user_id_linking.pyのUserProfileStoreProtocol)から、
     trial_start_at が設定済み かつ trial_end_notified_at が未設定 かつ
     upgraded_at も未設定のユーザーを抽出
  2) 抽出結果のうち、now - trial_start_at >= 14日 のものを送信対象とする
  3) trial-end-notification-design.md 3節の通知メッセージ(postbackボタン付きFlex
     Message)を送信し、trial_end_notified_at に送信時刻を書き込む
        ↓
  LINE Push Message API(course-set-pashaのtrial_end_scheduler.pyと同じ
  LinePushClientプロトコルの流用を想定。本venture側にはまだ同プロトコルの実装が
  無いため、prototype/checkout_session.pyのCheckoutSessionClient Protocolと同じ
  「最小限のProtocol定義+InMemoryスタブ」方式で新設する)
```

course-set-pashaと同じ理由(Cloud Schedulerの無料枠制限、ユーザー数が増えてもジョブ数を
増やさない)により、本ventureも**全ユーザー共通の単一日次ジョブ**とする。

## 2. course-set-pashaとの差分

- **CTAの実現方式が異なる**: course-set-pashaはLIFF IDトークン検証が必要だが、
  本ventureはcheckout-initiation-flow-design.md(フェーズ131)で確定した通り
  postbackアクションボタン方式(`data="action=start_checkout"`)のため、日次送信
  メッセージ自体もFlex Messageのボタン込みで組み立てる必要がある(プレーンテキスト
  リンクではない)。3節の`select_due_trial_end_notifications()`が返す対象ユーザー
  一覧を、`process_postback_event()`(フェーズ132)が使うのと同じ
  `build_checkout_session_params()`関連の組み立てロジックには依存させず、
  あくまで「通知メッセージの文面組み立て」のみを担う関数として独立させる
  (postbackボタンのdata自体は固定文字列のため、Checkout Session作成はボタン押下時の
  process_postback_event()側で行う、という既存の役割分担を維持する)。
- **`upgraded_at`の書き込み配線が本venture側でも未実装**: course-set-pashaの2節と
  同じギャップ(checkout-session-completed-handling-design.mdの
  `handle_checkout_session_completed()`は`stripe_customer_id`の書き込みのみで
  `upgraded_at`は未書き込み、trial-end-notification-design.md 4節で既知の課題として
  記録済み)がそのまま残っている。本設計でも、選定ロジック(3節)は
  `upgraded_at is not None`のユーザーを除外する形で先に書き、実際の書き込み配線は
  次回以降の課題として残す(course-set-pashaと同じ安全策: `trial_end_notified_at`が
  未設定であることも独立した必要条件とし、`upgraded_at`未配線のまま(B)が先に稼働しても
  二重送信は起きない設計とする)。

## 3. 選定ロジック(`prototype/trial_end_scheduler.py`想定)

- `select_due_trial_end_notifications(users, now, trial_period_days=14)`:
  以下すべてを満たすユーザーを抽出する純粋関数として実装する(course-set-pashaと
  同じ「時刻の一致ではなく範囲条件」を採用し、スケジューラの実行遅延・欠落に自然に
  耐える設計とする)。
  - `trial_start_at is not None`
  - `trial_end_notified_at is None`
  - `upgraded_at is None`
  - `now - trial_start_at >= timedelta(days=trial_period_days)`
- 条件(A)(生成回数10回到達、trial-end-notification-design.md 2節)側の実装
  (`process_memo_event()`相当、本venture未着手)が将来`trial_end_notified_at`を
  書き込むようになれば、本関数は自動的にそのユーザーを対象から除外する
  (「いずれか早い方で1回のみ送信」の設計をそのまま反映する)。

## 4. 冪等性

- 送信後は`trial_end_notified_at`に送信時刻を書き込み、以降の実行では3節の抽出条件から
  自然に除外される(追加のロック機構は不要、course-set-pashaと同じ方式)。
- Cloud Functionsが同一ユーザーを複数インスタンスで同時処理する可能性への対策
  (書き込みのトランザクション化)は、course-set-pashaが残した同種の課題と同じく
  実装時の課題として残す。

## 5. 今後の課題

- `prototype/trial_end_scheduler.py`本体の実装(3節の選定ロジックと通知メッセージ
  組み立て・LinePushClient送信の配線)は**フェーズ134で実装済み**
  (`select_due_trial_end_notifications()`・`send_trial_end_notifications()`・
  `build_trial_end_notification_flex_message()`、テスト29件)。
- `user_id_linking.py`の`UserProfile`・`UserProfileStoreProtocol`への
  `trial_start_at`・`trial_end_notified_at`・`upgraded_at`3フィールド追加
  (trial-end-notification-design.md 5節で予告済み)は**フェーズ134で実装済み**。
- `handle_checkout_session_completed()`への`upgraded_at`書き込み配線
  (2節で既知の課題として記録)は**フェーズ135で実装済み**
  (`store.get(user_id).upgraded_at is None`の場合のみ書き込む形で「1回だけ書き込む」
  不変条件を維持、テスト3件追加)。
- ~~trial-end-notification-design.md 4節の「生成一時停止」判定
  (`_is_generation_paused()`相当、course-set-pashaはフェーズ114で実装済み)の
  実コード実装は本venture側でまだ未着手で、次回以降の課題として残る。~~ →
  **フェーズ138で対応済み**(本ドキュメント作成〈フェーズ133〉時点ではまだ未実装
  だったため、本節の記載が更新されないまま残っていた)。`cloud_function_webhook.py`に
  `_is_generation_paused(profile)`・`GENERATION_PAUSED_MESSAGE`を新設し、
  `process_memo_event()`冒頭で分岐する形で実装済み。あわせてフェーズ153で、本関数が
  読む`trial_end_notified_at`と、本モジュールの`send_trial_end_notifications()`が
  書く`trial_end_notified_at`が同一の`InMemoryUserProfileStore`経由で一気通貫で
  つながることを確認する結線テスト(`TrialEndSchedulerToGenerationPausedWiringTest`、
  `test_cloud_function_webhook.py`)を追加した。
- 1節「`user_profile`ストアから...ユーザーを抽出」に相当する、実際の
  `UserProfileStoreProtocol`実装から`TrialUserState`を組み立てる関数
  (`build_trial_user_states()`)は**フェーズ156で実装済み**(course-set-pashaの
  同名関数と同種、`store.get(user_id)`一発でTrialUserStateを組み立てる構成)。
  あわせて、`handle_checkout_session_completed()`が書き込む`upgraded_at`と
  `select_due_trial_end_notifications()`が読む`upgraded_at`が同一の
  `InMemoryUserProfileStore`経由でつながることを確認する結線テスト
  (`StripeWebhookUpgradedAtToTrialEndSchedulerWiringTest`、
  `test_trial_end_scheduler.py`)を追加した。
- 実際のCloud Scheduler実行環境の構築(GCPプロジェクトの課金設定を伴う)は
  オーナー承認待ちの範囲(pending-approval.md参照)。本ドキュメントは選定ロジック・
  スケジューラ構成の机上設計にとどめる。
