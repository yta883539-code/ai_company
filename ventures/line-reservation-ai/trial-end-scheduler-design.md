# トライアル期間・件数到達判定用の日次スケジューラ設計

作成日: 2026-08-29(フェーズ続き143)

trial-start-anchor-decision.md「5. 今後の課題」で未着手のまま残っていた、
(1)期間到達判定用の日次スケジューラ本体(`trialStartAt`から14日経過した店舗の抽出)、
(2)件数条件(予約20件到達)判定ロジック、の2点を設計・実装する。
course-set-pasha/trial-end-scheduler-design.mdの構成を踏襲しつつ、本ventureの
仕組み(billing-upgrade-flow-design.md・dormant-mode-renotification-design.md)に
合わせて内容を調整する。

## 1. 本venture固有の前提(course-set-pashaとの違い)

- course-set-pashaは条件(B)(期間経過)のみの単一条件だったが、本ventureは
  pricing-plan.md「無料トライアル条件(仮)」で「初回の予約確定から14日間、または
  初回の予約確定を含め予約20件到達のいずれか早い方まで無料」と定めており、
  期間条件と件数条件のOR判定が必要。
- course-set-pashaは`upgraded_at`フィールドを新設して「有料転換済みユーザーの除外」に
  使ったが、本ventureは既にbilling-upgrade-flow-design.md/dormant-mode-renotification-
  design.mdで「トライアル終了時利用実績レポート送信 → 3日間の猶予期間 →
  未選択なら`suspensionReason: "trial_unselected"`」という別経路の状態遷移を持っている。
  本スケジューラの役割は、この一連の流れの起点である「利用実績レポート送信」を
  いつ行うかの判定のみに限定し、有料転換済みかどうかの判定はスコープ外とする
  (トライアル中に予約確定を続けている店舗が対象のため、その時点で有料転換していることは
  想定しないため。また、レポート送信後すぐに転換した場合の扱いはdormant_mode_scheduler.py
  側が「その間にプラン選択が完了していない」を確認する既存の未着手課題としてそちらに残す)。
- 冪等性は`trialEndReportSentAt`(firestore-data-model.md新規追加)が未設定であることを
  必要条件とする、course-set-pashaの`trial_end_notified_at`と同じ設計。

## 2. 全体構成

```
Cloud Scheduler(cron、日次1回。深夜帯、例: JST 04:00を暫定案とする。
course-set-pasha/aircon-pashaの日次スケジューラと同じ想定)
        ↓ HTTPトリガー
Cloud Function E: send_trial_end_reports
        ↓
  1) storesコレクション(firestore-data-model.md)から、trialStartAtが設定済み
     かつ trialEndReportSentAt が未設定の店舗を抽出
  2) 各店舗について、以下いずれかを満たせば送信対象とする(3節)
     - now - trialStartAt >= 14日(期間条件)
     - 予約確定累計数(InMemoryBookingRecordStore.count_confirmed_bookings()相当の
       Firestore集計、実接続後はbookingsコレクションのカウントクエリまたは別途
       集計フィールドの保持を検討)>= 20件(件数条件)
  3) trial_end_report_scheduler.pyのrender_trial_end_report_message()で文言を組み立てて
     LINE Push Message APIで送信し、成功時のみ trialEndReportSentAt に送信時刻を書き込む
        ↓
  以降3日間の猶予期間・休止モード遷移はdormant-mode-renotification-design.md
  (dormant_mode_scheduler.py)が引き継ぐ
```

## 3. 選定ロジック(`prototype/trial_end_scheduler.py`)

- `StoreTrialState`(frozen dataclass): `store_id`・`trial_start_at`
  (`Optional[datetime]`)・`trial_end_report_sent_at`(`Optional[datetime]`)・
  `booking_count`(`int`、`count_confirmed_bookings()`相当の集計済み値を受け取る。
  trial_end_report_scheduler.pyの`TrialUsageSummary`と同じく「集計はスコープ外、
  集計済みの値を受け取る」設計方針を踏襲)。
- `is_trial_end_report_due(state, now, trial_period_days=14, trial_booking_threshold=20)`:
  以下をすべて満たす場合に`True`を返す純粋関数。
  - `trial_start_at is not None`
  - `trial_end_report_sent_at is None`
  - `now - trial_start_at >= timedelta(days=trial_period_days)` **または**
    `booking_count >= trial_booking_threshold`
- `select_due_trial_end_reports(states, now, **kwargs)`: `states`のうち
  `is_trial_end_report_due()`が`True`のものだけを抽出するラッパー
  (course-set-pashaの`select_due_trial_end_notifications()`と同じ役割分担)。
  Firestoreクエリへの変換は、期間条件側は「trialStartAt <= (now - 14日) の範囲クエリ +
  trialEndReportSentAt == null の等価クエリ」の複合インデックスで表現できるが、件数条件側
  (`booking_count >= 20`)は現状bookingsコレクション側の集計値をどう保持するか未確定
  (都度カウントクエリを打つか、stores側にキャッシュ用の集計フィールドを持たせるか)であり、
  実装時の課題として残す(4節参照)。

## 4. InMemory版の実装状況(フェーズ続き143時点)

- `prototype/engine.py`の`ConversationFlowStateMachine`に`_trial_start_at`・
  `_trial_end_report_sent_at`を追加し、`get_trial_start_at()`/
  `get_trial_end_report_sent_at()`/`mark_trial_end_report_sent(now)`を実装した。
  `_trial_start_at`は`_first_booking_self_check_sent`と同一の`provide_details()`確定
  成功分岐で設定する(trial-start-anchor-decision.md 3節の書き込みタイミングどおり)。
- `InMemoryBookingRecordStore`に`count_confirmed_bookings(store_id)`を追加した
  (キャンセル・変更済みレコードも含めた累計確定回数。2節参照の「予約20件到達」は
  利用実績の指標であり、その時点で来店予定が20件残っているという意味ではないため)。
- `prototype/trial_end_scheduler.py`に3節の`StoreTrialState`/
  `is_trial_end_report_due()`/`select_due_trial_end_reports()`を実装した。
  `ConversationFlowStateMachine`・`InMemoryBookingRecordStore`から`StoreTrialState`を
  組み立てる処理(Firestore実接続後の本番配線に相当)は、呼び出し側
  (Cloud Function E相当)の役割として本モジュールのスコープ外とする
  (trial_end_report_scheduler.pyが集計値の取得をスコープ外としているのと同じ方針)。

## 5. 今後の課題

- bookingsコレクション側の「予約確定累計数」をFirestoreでどう効率よく取得するか
  (都度集計クエリ vs storesドキュメントへのカウンタフィールド追加)は、実Firestore
  接続時に別途設計する。
- (解消済み 2026-08-29フェーズ続き144: Cloud Function E本体の配線ロジックを
  `prototype/cloud_function_send_trial_end_reports.py`の`send_trial_end_reports()`として
  実装した。3節の`select_due_trial_end_reports()`・
  trial_end_report_scheduler.py`render_trial_end_report_message()`・LinePushClient
  (cloud_function_process_event.pyで定義済み)を接続し、送信成功時のみ
  `TrialEndReportCandidate.report_sent_writer.mark_trial_end_report_sent(now)`
  (engine.py`ConversationFlowStateMachine`が満たすProtocol)を呼ぶ冪等性配線とした。
  `auto_handled_inquiry_count`(自動対応お問い合わせ件数)の実集計・
  店舗オーナーLINE user_idの解決は、booking_count同様「呼び出し元が集計済みの値を渡す」
  想定でスコープ外のまま残した。実Cloud Function本体〈functions_framework配線〉・
  実Firestoreからの候補読み取りクエリ組み立ては、実ホスティング基盤接続時の課題として残る)
- (解消済み 2026-08-29フェーズ続き148: `auto_handled_inquiry_count`の実集計元を
  `NotificationLogAggregator`に結線する設計・実装に着手した。`faq_segments[].resolved:true`
  ―厳守事項9a(店舗登録済み静的情報)に基づきLLMがエスカレーションなしで自己完結して
  回答できたFAQ項目―を「自動対応できたお問い合わせ」の定義として採用し、
  `NotificationLogAggregator.auto_handled_faq_count`を新設した。`resolved:false`の
  未登録FAQ相談集計(`topic_counts`/`unique_unresolved_topic_count()`)とは異なり、
  オーナー通知の重複抑止が目的ではないため、同一日・同一userId・同一topicの再送でも
  実際に自動応答した回数分をそのままカウントする(値引きの目的が無いため)。
  テスト1件追加(`test_resolved_faq_segments_counted_as_auto_handled_without_dedup`)、
  venture全体393件全件パス・schema検証25件パスを確認した。残る課題は、
  `NotificationLogAggregator`自体が現状「30日分の読み取り専用画面」用にその都度
  構築される想定である点(トライアル期間14日分を跨いで永続集計する仕組みではない)を
  踏まえた、Firestore上での実際の集計クエリ・永続化方法の設計と、
  `cloud_function_send_trial_end_reports.py`の候補組み立て処理(呼び出し元)への
  実配線。いずれも実Firestore接続後(オーナー承認待ち)の課題として残る)
- (解消済み 2026-08-29フェーズ続き149: 前項で残っていた「Firestore上での実際の
  集計クエリ・永続化方法の設計」に着手した。`notificationLogEntries`(firestore-
  data-model.md 4節)に4区分目の`category:"auto_handled_faq"`を追加し、
  `auto_handled_faq_count`はオーナー向け画面と同じ`notificationLogEntries`への
  追記(`resolved:false`の`unresolved_faq`と異なりユニーク化の重複排除書き込みは
  不要、実際に自動応答した回数分だけ追記すればそのまま件数になる)で永続化する
  設計とした。トライアル終了レポート側は店舗ごとに起点が異なる「trialStartAtから
  14日間」を集計する必要があるため、オーナー画面側の`category`等値フィルタとは別に
  `category`等値+`createdAt`範囲の複合条件`count()`集約クエリを新設し、
  `(category ASC, createdAt ASC)`の複合インデックスが必要になる点を明記した。
  詳細はfirestore-data-model.md 4節「トライアル期間(14日)を跨いだ集計クエリ」
  参照。コード変更は無し(机上設計のみ)、venture全体393件全件パス・schema検証
  25件パスを確認した(変更前と同数、差分なしの再確認)。承認不要な設計のみで、
  外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。残る課題は`cloud_function_send_trial_end_
  reports.py`の候補組み立て処理への実配線と、実際の複合インデックス作成で、
  いずれも実Firestore接続後(オーナー承認待ち)の課題として残る)
- 実際のCloud Scheduler新規作成・LINE公式アカウント開設は
  オーナー承認待ち・次回以降の課題として残る(pending-approval.md参照)。
- ~~レポート送信後、3日間の猶予期間中にプラン選択が完了した場合の
  `trialEndReportSentAt`と`suspensionReason`の整合(dormant_mode_scheduler.py側の
  「その間にプラン選択が完了していない」判定の実装)は、1節で述べた通り
  dormant-mode-renotification-design.md側の既存の未着手課題として引き続き残す。~~ →
  2026-08-29(フェーズ続き145)、dormant-mode-renotification-design.md側で対応済み。
  詳細は同ドキュメント「5. 送信要否の判定」参照。
