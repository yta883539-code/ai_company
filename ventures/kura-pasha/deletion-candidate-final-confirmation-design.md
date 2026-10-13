# 削除候補化後の最終確認・「連絡不能」オーナーレビュー用レポート設計

フェーズ232(stripe-cancellation-deletion-candidate-trigger-design.md)の次回候補(2)
「`list_deletion_candidates()`を日次バッチへ配線し、aircon-pasha・course-set-pasha型の
削除候補化後の最終確認送信・『連絡不能』オーナーレビュー用レポート(line-reservation-ai
フェーズ318・319相当)を本ventureにも実装する」に対応する設計。

## 1. 前提・参照元

- data-retention-policy.md「削除候補化後の最終確認」節(フェーズ20): 主経路はLINE公式
  アカウントからのpush送信、ブロック済みで送達できない場合は代替のメール経路(実装は
  メール送信基盤整備後、他venture共通の未着手課題)、いずれの経路でも応答が得られない
  場合は自動削除せずオーナーが個別判断、という方針のみが整理されていた。
- aircon-pasha/prototype/deletion_candidate_final_confirmation.py(フェーズ167・307)・
  deletion-candidate-unreachable-owner-review-design.mdと同じ考え方を踏襲する。
- 本ventureは契約単位が`craftsman_workshop/{workshop_id}`で、支払い名義人
  (最終確認の送信対象)は`contractor_user_id`1名に限定される構造
  (craftsman-account-linking-design.md)。aircon-pasha・course-set-pashaの
  `user_id`単位の構造とはこの点が異なるため、本venture既存の
  subscription_cancellation_notification.py・payment_suspension_owner_notification.py
  と同じ「送信対象はworkshop_idから`contractor_user_id`を解決する」方式を踏襲する。
- 送信形式は本venture既存の各通知モジュールと同じプレーンテキスト
  (`LinePushClient.send_message(user_id, text)`)とし、aircon-pasha版のFlex Message形式は
  採用しない(本venture既存の全通知がプレーンテキストに統一されているため)。

## 2. 対象・判定ロジック

- 対象は`deletion_candidate.list_deletion_candidates()`が返すworkshop_id一覧
  (`deletion_candidate_at <= now`)。
- 各workshop_idについて、`workshop_store.get_contractor_user_id(workshop_id)`で送信先
  user_idを解決し、`user_profile_store.get_is_following(user_id)`でLINE pushが送達可能かを
  判定する(aircon-pasha版の`route_deletion_candidate_confirmation()`と同一ロジック)。
  - `is_following=True` → LINE push送信を試みる。成功時のみ
    `deletion_confirmation_sent_at`を書き込む。
  - `is_following=False`(ブロック済み。代替のメール経路はdata-retention-policy.md記載の
    とおり他venture共通の未着手課題のため本設計でも実装しない) →
    送信を試みず`deletion_confirmation_unreachable_at`のみ書き込む。
- `deletion_confirmation_sent_at`が設定済みのworkshop_idは再送対象から除外する
  (一度送達済みなら再送しない)。`MARK_UNREACHABLE`に倒れたworkshop_idは
  `deletion_confirmation_sent_at`が設定されないため、毎回の実行で対象に残り続け、
  ブロック解除(再フォロー)後に自動的にLINE push経路へ切り替わる
  (aircon-pasha版と同じ、安全側の挙動)。

## 3. 文言

具体的な削除予定日には言及せず、保存期間ポリシーに基づく取り扱いを案内するに留める
(aircon-pasha版と同じ理由: 実際の削除実行バッチがまだ存在しないため)。

```
【鞍パシャッと】データ保有についてのご案内

ご契約終了から一定期間が経過したため、プライバシーポリシーに基づき、お預かりしている
情報(工房名・メールアドレス等)の保有継続について確認のご連絡です。

引き続き保有をご希望の場合や、サービスの再開をご希望の場合は、このメッセージへの
ご返信、または改めてのお申し込みにてご連絡ください。
特にご連絡がない場合、当社の定めるデータ保存期間ポリシーに従って取り扱います。
```

## 4. 「連絡不能」オーナーレビュー用レポート

aircon-pasha版と同一の設計を踏襲する。

- `deletion_confirmation_unreachable_at`が設定済みのworkshop_id全件をworkshop_id昇順で
  一覧化する、読み取り専用の関数(削除実行・外部への自動送信は一切行わない)。
- オーナーへの提示は本リポジトリの運営方式(対話セッション内での表示)に合わせる。
- 候補が0件の場合は「連絡不能の削除候補工房はいません。」の1行のみ。候補がある場合は、
  件数の見出し・各workshop_idと経過日数・判定日時の一覧・末尾に「本リストは自動削除の
  対象ではなく、オーナーが対話セッションで個別に削除可否を判断する」旨の注記を含める。

## 5. データモデルへの追加

`WorkshopStoreProtocol`(usage_counter_workshop.py)に以下2フィールドのget/set
(計4メソッド)を追加する。`deletion_candidate_at`等と同じ、workshop単位のフィールド。

- `deletion_confirmation_sent_at: Optional[datetime]`
- `deletion_confirmation_unreachable_at: Optional[datetime]`

## 6. 実施内容

`prototype/deletion_candidate_final_confirmation.py`を新設し、以下を実装する。

- `render_deletion_candidate_final_confirmation_message()` / 3節の文言定数
- `DeletionCandidateConfirmationRoute`(Enum: `LINE_PUSH` / `MARK_UNREACHABLE`)・
  `route_deletion_candidate_confirmation(is_following)`
- `DeletionCandidateConfirmationWorkshopState`(workshop_id・contractor_user_id・
  is_following・deletion_confirmation_sent_at)
- `select_due_deletion_candidate_final_confirmations()`
- `build_deletion_candidate_confirmation_states()`(workshop_store・user_profile_store
  両方から状態を組み立てる)
- `send_deletion_candidate_final_confirmations()` / `SendDeletionCandidateFinalConfirmationsResult`
- `run_due_deletion_candidate_final_confirmations()`(store wiring込みの1本の関数、
  `deletion_candidate.list_deletion_candidates()`を呼び出す)
- `UnreachableDeletionCandidate` / `list_unreachable_deletion_candidates()` /
  `render_unreachable_deletion_candidates_report()`(4節)

`daily_scheduler.py`の`run_daily_workshop_checks()`に`user_profile_store`引数を追加し、
既存3系統(トライアル終了報告・決済失敗リマインド・決済停止オーナー通知)に続く4番目の
処理として本機能の送信配線を呼び出す。`cloud_function_run_daily_workshop_checks.py`の
`get_daily_workshop_checks_runtime_dependencies()`にも`user_profile_store`の既定値
(`InMemoryUserProfileStore()`)を追加する。

## 7. 未検証・残課題

- 代替のメール経路(送信基盤整備後)は他venture共通の未着手課題のため本設計でも
  実装しない。
- 実際の削除実行バッチ(自動削除)自体はline-reservation-ai同様、本設計のスコープ外
  (オーナーが対話セッションで個別に削除可否を判断する運用に留める)。
- 実Firestore・実LINE Messaging API接続はオーナー承認待ち(pending-approval.md参照、
  本venture自体の稼働に必須の前提として既存記載の範囲内)。

最終更新: 2026-10-13 09:00 UTC
