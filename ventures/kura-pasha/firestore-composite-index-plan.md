# Firestore複合インデックス定義の集約(フェーズ234)

## 位置づけ

workshop-store-firestore-adapter-design.md 28節「次回候補」に残っていた「承認後の結合実装
フェーズに備えた準備作業」のうち、forklift-pasha/firestore-composite-index-plan.md
(フェーズ150)が確立した方針(venture全体に分散している複合インデックス必要箇所を1ドキュメント
に集約し、実際にデプロイ可能な`firestore.indexes.json`を先行して書き出す)を、本venture
(kura-pasha)にも横展開する。GCPプロジェクト作成・Firestore有効化自体はオーナー承認待ちの
ため、本フェーズではJSONの中身を確定するだけの机上作業に留まる。

`prototype/daily_scheduler.py`・`prototype/deletion_candidate_final_confirmation.py`・
`prototype/payment_suspension_owner_notification.py`はいずれも現状
`all_workshop_ids()`による全件走査(インメモリ線形フィルタ)で抽出条件を代替しており、
実Firestore接続後にこれを索引付きクエリへ置き換える際に必要となる複合インデックスを
本ドキュメントで棚卸しする。

## 集約した複合インデックス一覧

| # | 対象コレクション | クエリの用途 | フィールド(順序) | クエリスコープ | 出典 |
|---|---|---|---|---|---|
| 1 | `craftsman_workshop`(ルートコレクション) | `select_due_trial_end_reports()`(`daily_scheduler.py`、design 3.1節): `trial_generation_used == false AND trial_end_notified_at == null AND trial_start_at <= (now - trial_period_days)`でトライアル30日到達報告の対象を抽出 | `trial_generation_used` ASC, `trial_end_notified_at` ASC, `trial_start_at` ASC | Collection(本ventureは`craftsman_workshop`をルートコレクションとする設計〈firestore-provider-adapter-design.md〉のため、line-reservation-aiのようなcollection groupスコープは不要) | daily-scheduler-design.md 3.1節・daily_scheduler.py `is_trial_end_report_due()` |
| 2 | `craftsman_workshop`(ルートコレクション) | `select_due_payment_failure_reminders()`(`daily_scheduler.py`、design 3.2節): `payment_failure_reminder_sent_at == null AND payment_failure_detected_at`が「猶予期間−事前日数」以上かつ猶予期間未満の範囲に入る決済失敗リマインド対象を抽出 | `payment_failure_reminder_sent_at` ASC, `payment_failure_detected_at` ASC | Collection | daily-scheduler-design.md 3.2節・daily_scheduler.py `is_payment_failure_reminder_due()` |
| 3 | `craftsman_workshop`(ルートコレクション) | `select_due_payment_suspension_owner_notifications()`(`payment_suspension_owner_notification.py`): `payment_suspension_owner_notified_at == null AND payment_failure_detected_at <= (now - grace_period_days)`(=既に制限モードへ移行済み)の対象を抽出 | `payment_suspension_owner_notified_at` ASC, `payment_failure_detected_at` ASC | Collection | payment-suspension-owner-notification-design.md・payment_suspension_owner_notification.py `is_payment_suspended()` |
| 4 | `craftsman_workshop`(ルートコレクション) | `select_due_deletion_candidate_final_confirmations()`相当(`deletion_candidate_final_confirmation.py`): `deletion_confirmation_sent_at == null AND deletion_candidate_at <= now`の対象を抽出。現状は`deletion_candidate.list_deletion_candidates()`(単一フィールド範囲クエリ)で候補を絞った後、`build_deletion_candidate_confirmation_states()`が`deletion_confirmation_sent_at`をインメモリで追加フィルタする2段階構成だが、実Firestore接続後は本索引で1クエリに統合できる | `deletion_confirmation_sent_at` ASC, `deletion_candidate_at` ASC | Collection | deletion-candidate-final-confirmation-design.md・stripe-cancellation-deletion-candidate-trigger-design.md |

補足:

- 本venture(`craftsman_workshop`・`stripe_customer_index`・`user_profile`・
  `pending_workshop_invites`・`pending_links`・`usage_counter`の6コレクション、
  firestore-security-rules-draft.md 2節参照)はいずれもルートコレクション構成のため、
  forklift-pashaの補足と同じ理由により、上記4索引とも`queryScope`は`COLLECTION`のまま
  (`COLLECTION_GROUP`への変更は不要)。
- `deletion_candidate.list_deletion_candidates()`自体が使う`deletion_candidate_at <= now`
  という単一フィールドの範囲クエリは、Firestoreが単一フィールドに自動で索引を作成するため
  複合インデックスの対象外(forklift-pashaの`usage_counter`と同じ理由)。本ドキュメント#4は、
  これとは別に「`deletion_confirmation_sent_at`との組み合わせで1クエリに統合する場合」に
  必要となる索引として記録している。
- `blocked_but_billing_candidates.list_blocked_but_billing_candidates()`
  (`subscription_status != "canceled" AND contractor_user_idの`is_following`が`false`)は、
  `subscription_status`は`craftsman_workshop`ドキュメントのフィールドである一方
  `is_following`は`user_profile`ドキュメント(別コレクション、キーは`contractor_user_id`)の
  フィールドであり、2つの異なるコレクションをまたぐ条件はFirestoreの複合インデックス単体では
  解決できない(ドキュメント参照によるJOINに相当する操作がFirestoreクエリでは不可能なため)。
  このクエリは実Firestore接続後も、`subscription_status != "canceled"`の単一フィールド
  範囲クエリで候補を絞り込んだ後、各候補の`contractor_user_id`について`user_profile`を
  個別に`get()`する(現状のインメモリ実装と同じ二段構え)方式を維持する想定とし、本表には
  含めない。
- 上記1〜3はいずれも、現状の`prototype/*.py`(`InMemoryWorkshopStore`前提)では
  `all_workshop_ids()`による線形走査+インメモリ条件分岐で代替しているため、既存テストは
  いずれも索引の有無に関わらずパスする。実Firestore接続後、`InMemoryWorkshopStore`相当の
  Firestoreアダプタ実装時に本索引が必要になる想定。

## 生成した`firestore.indexes.json`

上記1〜4を`gcloud firestore indexes composite create`相当の宣言的定義として
`firestore.indexes.json`(venture直下)に書き出した。実際の`gcloud firestore deploy
--only firestore:indexes`実行は、GCPプロジェクト作成・Firestore有効化(オーナー承認待ち)
の後に行う。

## 残る課題

- 本表の各インデックスが実際にFirestoreコンソールの「クエリ実行時エラーからの自動提案」と
  一致するかは、実Firestore接続後(オーナー承認待ち)の検証課題として残る。
- #4について、現状の2段階構成(`list_deletion_candidates()`→インメモリフィルタ)を実
  Firestore接続後に1クエリへ統合するかどうかは、結合実装フェーズでの判断課題として残す
  (統合せず2段階のままでも機能上は問題ないため、必須の変更ではない)。
- `blocked_but_billing_candidates`のコレクションをまたぐ条件は、将来的に`user_profile`側
  の`is_following`を`craftsman_workshop`ドキュメントへの非正規化(冗長コピー)で解決する案も
  考えられるが、フォロー状態の二重管理による不整合リスクを避けるため、本フェーズでは見送りと
  し次回候補として記録するに留める。

最終更新: 2026-10-13 17:00 UTC(フェーズ234: workshop-store-firestore-adapter-design.md
28節に残っていた準備作業課題に対応し、forklift-pasha/firestore-composite-index-plan.md
〈フェーズ150〉の方針を横展開。本venture全体で必要な複合インデックス4件〈`craftsman_workshop`
コレクションのトライアル終了報告・決済失敗リマインド・支払い停止オーナー通知・削除候補最終
確認の各抽出クエリ〉を集約・`firestore.indexes.json`として書き出した。コード変更なし、
文書・JSON作成のみのため回帰テストの実行対象外)
