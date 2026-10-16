# Firestore複合インデックス定義の集約(フェーズ314)

## 位置づけ

forklift-pasha/firestore-composite-index-plan.md(フェーズ150)・kura-pasha/
firestore-composite-index-plan.md(フェーズ234)が確立した方針(venture全体に分散している
複合インデックス必要箇所を1ドキュメントに集約し、実際にデプロイ可能な
`firestore.indexes.json`を先行して書き出す)を、本venture(aircon-pasha)にも横展開する。
GCPプロジェクト作成・Firestore有効化自体はオーナー承認待ち(pending-approval.md参照)の
ため、本フェーズではJSONの中身を確定するだけの机上作業に留まる。

本venture固有の前提として、firestore-security-rules-draft.md(フェーズ312)が確定した
とおりルートコレクションは`user_profile`・`pending_links`・`usage_counter`の3件のみ
(`deletion_candidate`・`payment_failure`・`blocked_but_billing`等の状態をいずれも単一の
`user_profile`ドキュメントへ統合する設計のため、kura-pasha〈5コレクション〉・
line-reservation-ai〈複数コレクション、サブコレクション構造あり〉より少ない)。
`pending_links`・`usage_counter`は複合クエリが発生しないため対象外(「対象外の確認」節)。

## 集約した複合インデックス一覧

| # | 対象コレクション | クエリの用途 | フィールド(順序) | クエリスコープ | 出典 |
|---|---|---|---|---|---|
| 1 | `user_profile`(ルートコレクション) | `list_blocked_but_billing_candidates()`(`prototype/blocked_but_billing_candidates.py`): `is_following == False AND current_plan_id != null`を満たすuser_idを抽出 | `is_following` ASC, `current_plan_id` ASC | Collection | blocked-but-billing-detection-design.md(フェーズ167)2節・prototype/blocked_but_billing_candidates.py |
| 2 | `user_profile`(ルートコレクション) | `select_due_payment_suspensions()`(`prototype/payment_suspension_scheduler.py`): `payment_suspended_at == null AND payment_failure_detected_at <= (now - grace_period_days)`を満たすuser_idを抽出 | `payment_suspended_at` ASC, `payment_failure_detected_at` ASC | Collection | payment-failure-dunning-design.md 3節・prototype/payment_suspension_scheduler.py |
| 3 | `user_profile`(ルートコレクション) | `select_due_payment_failure_reminders()`(`prototype/payment_failure_reminder_scheduler.py`): `payment_suspended_at == null AND payment_failure_reminder_sent_at == null AND payment_failure_detected_at <= (now - (grace_period_days - reminder_days_before_end))`を満たすuser_idを抽出 | `payment_suspended_at` ASC, `payment_failure_reminder_sent_at` ASC, `payment_failure_detected_at` ASC | Collection | payment-failure-reminder-scheduler-design.md(フェーズ143)3節・prototype/payment_failure_reminder_scheduler.py |
| 4 | `user_profile`(ルートコレクション) | `select_due_trial_end_notifications()`(`prototype/trial_end_scheduler.py`): `trial_end_notified_at == null AND upgraded_at == null AND trial_start_at <= (now - trial_period_days)`を満たすuser_idを抽出 | `trial_end_notified_at` ASC, `upgraded_at` ASC, `trial_start_at` ASC | Collection | trial-end-scheduler-design.md・prototype/trial_end_scheduler.py |
| 5 | `user_profile`(ルートコレクション) | 統合後の`list_deletion_candidates()`相当(`prototype/deletion_candidate.py`・`deletion_candidate_final_confirmation.py`): `deletion_confirmation_sent_at == null AND deletion_confirmation_unreachable_at == null AND deletion_candidate_at <= now`を満たすuser_idを抽出(フェーズ320で起案、フェーズ321で`deletion_confirmation_unreachable_at`の等価条件を追加: deletion-candidate-query-consolidation-decision.md) | `deletion_confirmation_sent_at` ASC, `deletion_confirmation_unreachable_at` ASC, `deletion_candidate_at` ASC | Collection | deletion-candidate-query-consolidation-decision.md(フェーズ320・321)・prototype/deletion_candidate.py・deletion_candidate_final_confirmation.py |

補足:

- `user_profile`はルートコレクション(line-reservation-aiのような`stores/{storeId}/...`
  型のサブコレクション構造を持たない)のため、line-reservation-ai側の一部索引のような
  **collection group**スコープは本ventureでは不要。4件とも通常の`Collection`スコープで
  足りる(forklift-pasha版の補足と同じ結論)。
- #1〜#4のいずれも、現状の各モジュールは`InMemoryUserProfileStore.all_user_ids()`に
  よる線形走査+インメモリ条件判定で代替しており(各モジュールのdocstring「MVPでは
  `all_user_ids()`による線形走査で代替する」に明記済み)、既存テスト684件はいずれも
  索引の有無に関わらずパスする。実Firestore接続後、`FirestoreUserProfileStore`
  (firestore-provider-adapter-design.md)側にクエリベースの実装を追加する際に本索引が
  必要になる想定。
- #4(trial_end_scheduler.py)は本venture内に専用のCloud Functionsエントリポイント
  (`cloud_function_send_deletion_candidate_final_confirmations.py`相当の薄い配線)が
  まだ存在せず、`build_trial_user_states(store, user_ids)`が受け取る`user_ids`の
  組み立て元(=本来この索引を使うはずのクエリ発行元)自体が未着手のまま残っている
  (次回候補(2))。本フェーズでは将来の配線を見据えた索引の事前設計のみを行う。
- #1〜#3はいずれも`current_plan_id != null`・`payment_failure_detected_at <= X`のような
  不等号条件を含むが、Firestoreの複合インデックス定義上は等号・不等号を区別せず
  フィールド順序のみを指定する形式であるため、forklift-pasha/kura-pasha版の表記方式
  (ASC指定のみ)にそのまま揃えた。
- #2と#3は同じ`payment_suspended_at`を含むが、#3のインデックス(`payment_suspended_at`,
  `payment_failure_reminder_sent_at`, `payment_failure_detected_at`)は#2のクエリ
  (`payment_failure_reminder_sent_at`を条件に含まない)を代替できない。Firestoreの
  複合インデックスは「クエリの等号条件の集合」がインデックスの先頭からの連続部分列と
  一致する必要があり、#2のクエリは`payment_failure_reminder_sent_at`を等号条件に含まない
  ため#3索引の2番目のフィールドの位置で食い違う。したがって#2・#3は別々の索引として
  維持する。

## 対象外の確認

- `pending_links`: `save`/`get`/`delete`はドキュメント単位の読み書きのみ、`items()`
  (期限切れパージ用の全件走査)も複合条件を伴わない単純な全件`stream()`
  (firestore-provider-adapter-design.md 3節が「本venture想定トラフィックでは全件
  `stream()`でも無料枠に収まる前提のためクエリ最適化は過剰設計として見送る」と既に
  決定済み)のため対象外。
- `usage_counter`: `user_id`単一キーでのドキュメント取得のみ(複合クエリは発生しない)
  のため対象外。

## 生成した`firestore.indexes.json`

上記1〜4を`gcloud firestore indexes composite create`相当の宣言的定義として
`firestore.indexes.json`(venture直下)に書き出した。実際の`gcloud firestore deploy
--only firestore:indexes`実行は、GCPプロジェクト作成・Firestore有効化(オーナー承認待ち)
の後に行う。

## 残る課題

- 本表の各インデックスが実際にFirestoreコンソールの「クエリ実行時エラーからの自動提案」と
  一致するかは、実Firestore接続後(オーナー承認待ち)の検証課題として残る。
- #4(trial_end_scheduler.py)の実際のCloud Functionsエントリポイント(日次Cloud
  Scheduler配線)自体がまだ存在しない点は次回候補として残す。
- インメモリ全件走査から索引付きクエリへの切り替えタイミング(ユーザー数の閾値等)は
  forklift-pasha版と同様、未確定のまま次回以降の課題とする。
- #5は当初(フェーズ320)`route_deletion_candidate_confirmation()`が`MARK_UNREACHABLE`
  判定した候補(`deletion_confirmation_sent_at`が設定されないため統合後もクエリに残り続ける)
  の扱いが未確定だったが、フェーズ321で「クリア配線」(再フォロー時に`deletion_
  confirmation_unreachable_at`をクリア)を追加し、索引も3フィールド構成に更新して解消した
  (deletion-candidate-query-consolidation-decision.md参照)。

最終更新: 2026-10-16 21:00 UTC(フェーズ321: deletion-candidate-query-consolidation-
decision.mdのフェーズ320残課題〈MARK_UNREACHABLE候補の扱い〉解消に伴い、複合インデックス#5
を(`deletion_confirmation_sent_at` ASC, `deletion_confirmation_unreachable_at` ASC,
`deletion_candidate_at` ASC)の3フィールド構成に更新し、firestore.indexes.jsonに追記した
〈フェーズ320時点ではJSON未反映だった〉。コード変更は`deletion_candidate_final_
confirmation.py`・`cloud_function_webhook.py`側で実施済み〈クリア配線〉、本ファイル自体の
変更は文書・JSON更新のみ)
