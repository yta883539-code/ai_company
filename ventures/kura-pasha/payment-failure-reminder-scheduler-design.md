# 猶予期間終了直前リマインドスケジューラの命名パリティ確認(フェーズ189)

作成日: 2026-09-27(フェーズ189)

course-set-pasha(フェーズ120)・aircon-pasha(フェーズ143)がそれぞれ持つ
`payment-failure-reminder-scheduler-design.md`が本venture(kura-pasha)に存在しない
という命名上のギャップを横断確認した。結論から言うと、**機能自体は既にフェーズ112・117・120で
実装済み**であり、本venture固有の事情(1節)によりdaily-scheduler-design.mdへ統合された
形で設計・実装されている。本ドキュメントは新規の設計・実装を追加するものではなく、他venture2件
と同じファイル名を用意することで、今後の横断棚卸し(フェーズ185〜188のような
cross-document parity確認)が本venture側の実装を見落とさないようにするための参照
ドキュメントである。

## 1. なぜ同名ファイルが本ventureに存在しなかったか

daily-scheduler-design.md 1節が既に理由を明記している。本venture側では(a)トライアル30日
到達報告((B)経路、trial-end-notification-design.md)と(b)決済失敗3日前リマインド
(payment-failure-dunning-design.md 6節が残した課題)が「時刻ちょうどではなく日次バッチでの
範囲条件抽出が必要」という同じ形の要件であったため、フェーズ112で1つのドキュメント・
1つのモジュール(`prototype/daily_scheduler.py`)にまとめて設計した。他venture2件は
`trial-end-scheduler-design.md`と`payment-failure-reminder-scheduler-design.md`を
それぞれ独立したCloud Function/ドキュメントとして分離しているが、本ventureは着手時点で
どちらの日次バッチ本体も存在しなかった(低頻度受注特性・LINE公式アカウント接続前という
事情、daily-scheduler-design.md冒頭参照)ため、最小構成として最初から統合した。この結果、
「決済失敗リマインド」単体を指す同名ファイルが本ventureには生まれなかった。

## 2. 実装済みの内容(他venture2件との対応関係)

| 項目 | course-set-pasha / aircon-pasha | kura-pasha(本venture) |
|---|---|---|
| 設計ドキュメント | payment-failure-reminder-scheduler-design.md(独立) | daily-scheduler-design.md 3.2/4/5節(trial-end-notification-design.mdの(B)経路と統合) |
| 実装モジュール | `prototype/payment_failure_reminder_scheduler.py` | `prototype/daily_scheduler.py`(トライアル30日到達報告と同居) |
| 契約単位 | `user_id`(course-set-pasha)/同様 | `craftsman_workshop/{workshop_id}`(workshop単位、契約者は`contractor_user_id`1名限定) |
| 状態ストア | `UsageCounterProtocol` / `UserProfileStoreProtocol` | `WorkshopStoreProtocol`(`usage_counter_workshop.py`) |
| 選定関数 | `select_due_payment_failure_reminders(users, now, grace_period_days=7, reminder_days_before_end=3)` | `select_due_payment_failure_reminders(states, now, grace_period_days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS, reminder_days_before_end=PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END)`(同名、`daily_scheduler.py`) |
| 純関数(1件判定) | (course-set-pasha側は選定関数に内包) | `is_payment_failure_reminder_due(state, now, ...)` |
| 送信配線 | course-set-pashaは本ドキュメント時点で未実装(机上設計のみ)/aircon-pashaは`send_payment_failure_reminders()`相当 | `send_payment_failure_reminders(now, workshop_store, push_client)`(フェーズ120で送信配線まで完了済み) |
| 送信済みフラグ | `payment_failure_reminder_sent_at` | 同名。`get_payment_failure_reminder_sent_at`/`set_payment_failure_reminder_sent_at`(`WorkshopStoreProtocol`) |
| 上限側条件(既に制限モード相当まで進んでいないか) | course-set-pasha: `now - detected_at < grace_period_days`(計算方式、本venture同様)。aircon-pasha: `payment_suspended_at is None`(別立てフラグ方式) | course-set-pashaと同じ計算方式(`elapsed < grace_period_days`)。本ventureは`payment_suspended_at`相当の別フラグを持たず、`_is_payment_suspended()`と同じ「経過日数の都度算出」を全体方針として統一しているため(payment-failure-dunning-design.md 3節と同じ設計判断) |
| 決済成功時のクリア | `clear_payment_failure_reminder_sent_at()`(専用関数) | `clear_payment_failure_detected_at()`(1メソッドで`payment_failure_detected_at`・`payment_failure_reminder_sent_at`・`payment_suspension_owner_notified_at`の3フィールドをまとめてクリア。payment-failure-state-clear-on-subscription-deleted-design.md参照) |
| 通知形式 | course-set-pasha: プレーンテキスト(LIFF)。aircon-pasha: postbackボタン付きFlex Message | プレーンテキスト(`PAYMENT_FAILURE_REMINDER_MESSAGE`)。PortalLinkProvider相当(`portal_session.py`、フェーズ129)は実装済みだが`session_creator`未実装のプレースホルダのため、リマインド文言へのURL差し込みは実Stripe接続後の課題として保留中(payment-failure-dunning-design.md 6節末尾と同一の残課題) |
| Cloud Scheduler本体 | Cloud Function E/F(それぞれ独立) | Cloud Function G: `run_daily_workshop_checks()`(トライアル30日到達報告→決済失敗リマインド→制限モード移行時オーナー通知の3系統を1関数にまとめる) |

## 3. 追加の設計・実装が不要と判断した理由

上表の通り、他venture2件が`payment-failure-reminder-scheduler-design.md`で定義している
選定ロジック・送信配線・冪等性(送信済みフラグによる自然な除外、追加ロック機構は将来課題として
両者共通で保留)は、本ventureでは`daily-scheduler-design.md`3.2/4/5節および
`prototype/daily_scheduler.py`の`is_payment_failure_reminder_due()`/
`select_due_payment_failure_reminders()`/`send_payment_failure_reminders()`として
フェーズ112(選定ロジック)・フェーズ120(送信配線)で既に実装・テスト済みである。
`test_daily_scheduler.py`には決済失敗リマインド関連だけで6件(境界値・未検知・送信済み・
順序維持・送信配線の成功時/失敗時)のテストが既に存在する。したがって本フェーズでは
新規のプロトタイプコード・テストを追加しない。他venture2件との差分は名称・ファイル分割の
粒度のみであり、機能的なパリティは既に成立している。

## 4. 本フェーズで行った変更

- 本ドキュメントを新規作成し、他venture2件と同じファイル名を用意した(今後の横断棚卸しで
  本venture側の実装が見落とされないようにするため)。
- `prototype/daily_scheduler.py`冒頭の「設計の参照元」コメントへ本ドキュメントへの相互参照を
  追記した(コード変更ではなくコメントのみ)。
- `daily-scheduler-design.md`末尾へ、本ドキュメントへの参照を追記した。

## 5. 今後の課題(既存ドキュメントに記載済みのものを再掲)

- PortalLinkProvider経由のURLをリマインド文言へ実際に差し込む対応は、実Stripe接続後の課題
  として`payment-failure-dunning-design.md` 6節に残っている。
- 送信のトランザクション化(Cloud Functionsの複数インスタンス同時実行対策)は、他venture2件と
  同じく実装時の課題として`daily-scheduler-design.md`側にも明記されていない暗黙の前提であり、
  今回新たに指摘する事項ではない。
- 猶予期間7日・リマインド3日前という値は他venture共通の実測データ無き暫定値のままであり、
  本フェーズでは再検証していない(daily-scheduler-design.md 6節と同じ)。
- 実際のCloud Scheduler実行環境の構築・LINE公式アカウント接続は、他venture2件と同じく
  オーナー承認待ちの範囲(pending-approval.md参照)。
