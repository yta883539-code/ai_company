# 削除候補データ最終確認用の月次スケジューラ設計

作成日: 2026-10-11(フェーズ308)

フェーズ307の次回候補(2)を受け、`deletion_candidate_final_confirmation.py`の
`run_due_deletion_candidate_final_confirmations()`(フェーズ307で実装済み)を実際に
起動するCloud Scheduler構成を、trial-end-scheduler-design.md・payment-failure-reminder-
scheduler-design.mdと同じ型式で設計する。

## 1. 全体構成

```
Cloud Scheduler(cron、月次1回。日次バッチ群〈trial_end_scheduler等〉と異なり、
削除候補化(data-retention-policy.md)自体が月単位の粒度で進む事象のため、
厳密な時刻一致は不要。暫定案: 毎月1日 JST 05:00、他venture日次バッチ〈04:00台〉と
重ならない時間帯をずらす)
        ↓ HTTPトリガー
Cloud Function H: send_deletion_candidate_final_confirmations
        ↓
  run_due_deletion_candidate_final_confirmations(store, now, push_client)
  (deletion_candidate_final_confirmation.py、フェーズ307で実装済み)
        ↓
  1) deletion_candidate.list_deletion_candidates(store, now)で削除候補user_id一覧を取得
  2) build_deletion_candidate_confirmation_states()でis_following・
     deletion_confirmation_sent_atを読み取り状態を組み立て
  3) 未送信の候補のみ、is_followingに応じてLINE_PUSH/MARK_UNREACHABLEに振り分け
  4) LINE_PUSH: 最終確認メッセージをLINE Push Message APIで送信し成功時のみ
     deletion_confirmation_sent_atを書き込む。MARK_UNREACHABLE: 送信せず
     deletion_confirmation_unreachable_atのみ更新
        ↓
  LINE Push Message API(trial_end_scheduler.pyのLinePushClient Protocolを
  再利用、新規Protocol定義は不要)
```

他の日次バッチ(trial_end_scheduler・payment_suspension_scheduler・
payment_failure_reminder_scheduler)が「ユーザー数が増えてもジョブ数を増やさない
全ユーザー共通の単一ジョブ」方針を採っているのと同じ理由により、本スケジューラも
**全ユーザー共通の単一月次ジョブ**とする。

## 2. 他スケジューラとの差分

- **実行頻度が月次**: 削除候補化(`deletion_candidate_at`)自体が
  data-retention-policy.mdの保存期間ポリシーに基づき数ヶ月単位で発生する事象であり、
  日次実行する必要性が薄い。一方、`select_due_deletion_candidate_final_confirmations()`
  (deletion_candidate_final_confirmation.py)は「時刻の一致ではなく`deletion_
  confirmation_sent_at`未設定」という状態条件のみで判定するため、月次実行でも
  日次実行でも選定ロジック自体に変更は不要(他スケジューラと同じ「実行間隔に
  依存しない冪等な抽出条件」設計を踏襲)。
- **MARK_UNREACHABLE経路は書き込みのみで送信を伴わない**: 他スケジューラは
  送信成功/失敗の2値だが、本スケジューラは`route_deletion_candidate_confirmation()`
  (フェーズ307)によりLINE_PUSH/MARK_UNREACHABLEの2経路に分岐し、後者は送信を
  試みずに状態更新のみを行う。Cloud Function側はこの3分岐(sent/marked_unreachable/
  failed)をそのまま`SendDeletionCandidateFinalConfirmationsResult`から受け取り、
  ログ出力のみを行う(オーナー通知は本スケジューラの対象外。連絡不能〈ブロック中〉
  候補への対応はdeletion_candidate_final_confirmation.pyのモジュールdocstring記載の
  とおり「オーナーが対話セッションで個別に削除可否を判断する」運用のため、自動の
  オーナーLINE通知は設けない。必要であれば次回以降の課題として、連絡不能件数が
  一定数を超えた場合のみオーナーへダイジェスト通知する設計を検討できる)。

## 3. 冪等性

- 送信成功時は`deletion_confirmation_sent_at`を書き込み、以降の実行では
  `select_due_deletion_candidate_final_confirmations()`の抽出条件から自然に除外される
  (追加のロック機構は不要、他スケジューラと同じ方式)。
- MARK_UNREACHABLE経路は`deletion_confirmation_unreachable_at`のみを更新し
  `deletion_confirmation_sent_at`は設定しないため、ブロック解除(再フォロー)後の
  月次実行で自動的にLINE_PUSH経路へ切り替わり再試行される(deletion_candidate_
  final_confirmation.pyのコメントに明記済みの意図的挙動)。

## 4. 今後の課題

- `prototype/cloud_function_send_deletion_candidate_final_confirmations.py`相当の
  薄いエントリポイント(Cloud Scheduler HTTPトリガーを受け、実Firestore接続の
  `user_profile_store`・実LINE Push Clientを組み立てて`run_due_deletion_candidate_
  final_confirmations()`に渡す配線)の実装は次回以降の課題として残る
  (`stripe_webhook.get_stripe_runtime_dependencies()`と同じ「依存組み立てを1箇所に
  集約する」ファクトリ関数の追加が必要になる見込み)。
- 実際のCloud Scheduler実行環境の構築(GCPプロジェクトの課金設定を伴う)は
  オーナー承認待ちの範囲(pending-approval.md参照、2026-09-27 10:00 UTC記載の
  「trial_end_scheduler.py・payment_suspension_scheduler.py・payment_failure_
  reminder_scheduler.py等の日次バッチ用Cloud Scheduler」に、本月次バッチも
  同種の追加ジョブとして含まれる想定。本ドキュメント作成自体は新たな承認待ち事項を
  発生させない)。本ドキュメントは選定ロジック・スケジューラ構成の机上設計にとどめる。
