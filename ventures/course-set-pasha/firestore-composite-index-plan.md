# Firestore複合インデックス定義の集約(フェーズ301)

## 位置づけ

kura-pashaフェーズ240(ventures/kura-pasha/deletion-candidate-query-consolidation-
horizontal-survey.md)の次回候補(2)「course-set-pasha・forklift-pashaにもaircon-pasha
の決定doc相当を新設し複合インデックス設計に反映する」のうち、forklift-pashaは既にフェーズ163
で対応済みで、本venture(course-set-pasha)側は`deletion-candidate-query-consolidation-
decision.md`(フェーズ299・300)自体は既に存在するが、同docの「残る課題」に記載の通り
`firestore-composite-index-plan.md`・`firestore.indexes.json`自体がまだ新設されていなかった。
forklift-pasha/firestore-composite-index-plan.md(フェーズ150)・kura-pasha/firestore-
composite-index-plan.md(フェーズ234)が確立した方針(venture全体に分散している複合インデックス
必要箇所を1ドキュメントに集約し、実際にデプロイ可能な`firestore.indexes.json`を先行して書き出す)
を本venture にも横展開する。GCPプロジェクト作成・Firestore有効化自体はオーナー承認待ちのため、
本フェーズではJSONの中身を確定するだけの机上作業に留まる。

## 各フィールドの所属ドキュメントの確認

本venture固有の事情として、同じ「ユーザー」に関するフィールドが2つの異なるFirestore
ドキュメントに分かれて配置される設計であることを、既存コードのdocstring・コメントから
確認した(aircon-pasha・kura-pashaはいずれか一方に統一されており、本venture特有の分岐点)。

- **`user_profile/{user_id}`**: `deletion_candidate.py`(27行目)が
  「`user_profile/{user_id}`ドキュメントのうち`deletion_candidate_at`フィールドのみを...」と
  明記している。`deletion_candidate_final_confirmation.py`が新設した
  `deletion_confirmation_sent_at`・`deletion_confirmation_unreachable_at`の2フィールドは、
  `deletion_candidate_at`と同じ`ProfileDeletionCandidateStoreProtocol`(同docが`deletion_store`
  と呼ぶもの)が保持するフィールドであり、本venture全体で確立済みの「1ユーザー1ドキュメントに
  複数のフィールドグループが同居する」構造(firestore-provider-adapter-design.md 7.2節
  「`user_profile/{user_id}`は...フィールドグループが同一ドキュメントを共有する構造」)と
  同じ位置づけのため、`deletion_confirmation_sent_at`・`deletion_confirmation_unreachable_at`も
  `user_profile/{user_id}`ドキュメントに属すると判断する。
- **`usage_counter/{user_id}`**: `cloud_function_webhook.py`の`UsageCounterProtocol.
  set_trial_start_at_if_unset()`のdocstring(305行目)が「usage_counterドキュメントの
  `trial_start_at`フィールドへの書き込み」と明記している。同Protocolが保持する
  `trial_end_notified_at`・`payment_failure_detected_at`・`payment_failure_reminder_sent_at`・
  `payment_suspension_owner_notified_at`もすべて同一Protocol(`InMemoryUsageCounter`)の
  メソッドであり、`user_profile`とは別の`usage_counter`コレクションに属する
  (本venture用の`UsageCounterProtocol`実Firestore接続アダプタ設計自体はまだ着手されておらず、
  「残る課題」に記録する)。

この2系統の切り分けは`deletion_candidate_final_confirmation.py`が`deletion_store`
(`user_profile`側)と`profile_store`(`is_following`、同じく`user_profile`側だが別Protocol)
を分けて受け取る設計と矛盾しない(両者とも最終的には同じ`user_profile/{user_id}`ドキュメントに
書き込まれる、Python側のProtocol分割に過ぎない)。

## 集約した複合インデックス一覧

| # | 対象コレクション | クエリの用途 | フィールド(順序) | クエリスコープ | 出典 |
|---|---|---|---|---|---|
| 1 | `usage_counter` | `select_due_trial_end_notifications()`(`trial_end_scheduler.py`): `trial_start_at`が設定済みかつ`trial_end_notified_at == null`かつ`now - trial_start_at >= trial_period_days`のトライアル終了通知対象を抽出 | `trial_end_notified_at` ASC, `trial_start_at` ASC | Collection | trial-end-scheduler-design.md・trial_end_scheduler.py `select_due_trial_end_notifications()` |
| 2 | `usage_counter` | `select_due_payment_failure_reminders()`(`payment_failure_reminder_scheduler.py`): `payment_failure_detected_at`が設定済みかつ`payment_failure_reminder_sent_at == null`かつ猶予期間終了直前の範囲に入る決済失敗リマインド対象を抽出 | `payment_failure_reminder_sent_at` ASC, `payment_failure_detected_at` ASC | Collection | payment-failure-reminder-scheduler-design.md・payment_failure_reminder_scheduler.py `select_due_payment_failure_reminders()` |
| 3 | `usage_counter` | `select_due_payment_suspension_owner_notifications()`(`payment_suspension_owner_notification.py`): `payment_failure_detected_at`が設定済みかつ`payment_suspension_owner_notified_at == null`かつ`now - payment_failure_detected_at >= grace_period_days`(既に制限モードへ移行済み)の対象を抽出 | `payment_suspension_owner_notified_at` ASC, `payment_failure_detected_at` ASC | Collection | payment-suspension-owner-notification-design.md・payment_suspension_owner_notification.py `select_due_payment_suspension_owner_notifications()` |
| 4 | `user_profile` | `deletion_candidate_final_confirmation`の送信対象抽出(フェーズ299・300でkura-pasha/aircon-pashaと同じ統合方針を決定済み): `deletion_confirmation_sent_at == null AND deletion_confirmation_unreachable_at == null AND deletion_candidate_at <= now`に統合する。現状は`deletion_candidate.list_deletion_candidates()`(単一フィールド範囲クエリ)→`build_deletion_candidate_confirmation_states()`(インメモリフィルタ)の2段階構成だが、実Firestore接続後は本索引で1クエリに統合できる | `deletion_confirmation_sent_at` ASC, `deletion_confirmation_unreachable_at` ASC, `deletion_candidate_at` ASC | Collection | deletion-candidate-query-consolidation-decision.md(フェーズ299・300)・deletion_candidate_final_confirmation.py |

補足:

- 本venture(`user_profile`・`usage_counter`・`stripe_customer_index`・`pending_links`の
  4コレクション、firestore-provider-adapter-design.md参照)はいずれもルートコレクション構成の
  ため、forklift-pasha・kura-pashaの補足と同じ理由により、上記4索引とも`queryScope`は
  `COLLECTION`のまま(`COLLECTION_GROUP`への変更は不要)。
- #4の`deletion_candidate_at <= now`という単一フィールドの範囲クエリ自体は、Firestoreが
  単一フィールドに自動で索引を作成するため複合インデックスの対象外(kura-pashaの補足と同じ
  理由)。本表#4は、これとは別に「他2フィールドの等価条件と組み合わせて1クエリに統合する場合」
  に必要となる索引として記録している。
- #1〜#3は、現状の`prototype/*.py`(`InMemoryUsageCounter`前提)では`all_user_ids()`相当の
  全件走査+インメモリ条件分岐で代替しているため、既存テストはいずれも索引の有無に関わらず
  パスする。実Firestore接続後、`InMemoryUsageCounter`相当の`UsageCounterProtocol`Firestore
  アダプタ実装時に本索引が必要になる想定。

## 生成した`firestore.indexes.json`

上記1〜4を`gcloud firestore indexes composite create`相当の宣言的定義として
`firestore.indexes.json`(venture直下)に書き出した。実際の`gcloud firestore deploy
--only firestore:indexes`実行は、GCPプロジェクト作成・Firestore有効化(オーナー承認待ち)
の後に行う。

## deployment-runbook.mdの記載修正

ステップ2(45〜56行目)の記載が、フェーズ299時点の2フィールド構成
(`deletion_confirmation_sent_at`・`deletion_candidate_at`)のままで、フェーズ300で追加された
`deletion_confirmation_unreachable_at`が未反映だったため、本フェーズで3フィールド構成に
更新し、あわせて本ドキュメント・`firestore.indexes.json`への参照を追記した(本フェーズで実施)。

## 残る課題

- 実際のFirestoreクエリ実装・複合インデックスのデプロイはGCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち)後。
- 本venture固有の`UsageCounterProtocol`(`usage_counter`コレクション)の実Firestore接続
  アダプタ設計は、`UserProfileStoreProtocol`(firestore-provider-adapter-design.md 5〜18節)
  とは異なりまだ着手されていない。次回候補として残す(aircon-pasha・kura-pashaの単一store
  構成と異なり、本venture特有の2コレクション構成を踏まえた設計が必要)。
- 本表の各インデックスが実際にFirestoreコンソールの「クエリ実行時エラーからの自動提案」と
  一致するかは、実Firestore接続後(オーナー承認待ち)の検証課題として残る。
- 残る横展開先(line-reservation-ai)は既にkura-pashaフェーズ240の横展開調査で「単一述語設計
  のため対象外」と確認済みのため、本件に関する追加の横展開作業は不要。

最終更新: 2026-10-17 03:00 UTC(フェーズ301: kura-pashaフェーズ240・forklift-pashaフェーズ163
の方針を本ventureに横展開し、`firestore-composite-index-plan.md`・`firestore.indexes.json`を
新設。本venture固有の`user_profile`/`usage_counter`の2コレクション構成を既存コードの
docstring・コメントから確認した上で4索引を集約し、deployment-runbook.mdのステップ2記載を
フェーズ300の3フィールド構成に合わせて更新した。コード変更なし、文書・JSON作成のみのため
回帰テストの実行対象外)
