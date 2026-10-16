# 削除候補の洗い出し・最終確認・連絡不能レポート設計

作成日: 2026-10-15 22:00 UTC(フェーズ152)

## 1. 背景

data-retention-policy.md(フェーズ100)「今後の課題」は、削除候補化トリガー・削除実行
バッチの実装を「他venture(aircon-pasha等)が先行実装した`deletion_candidate.py`等の設計を
参考にできる」次回候補として残していた。他4venture(aircon-pasha・course-set-pasha・
kura-pasha・line-reservation-ai)は既にこの機能(削除候補の洗い出し・最終確認送信・
連絡不能オーナーレビュー用レポート)を実装済みである一方、forklift-pashaのみ未着手のまま
残っていたため、本フェーズで横展開する。

## 2. 他ventureとの相違点(簡略化できる点)

- **削除候補化の起点を`canceled_at`に一本化できる。** 他venture(特にcourse-set-pasha)は
  `deletion_candidate_at`という別フィールドを設け、webhookイベント受信時の時刻
  (`event.created`)を基準に「古いイベントによる上書き」を防ぐstale-event-guardロジック
  (deletion-candidate-stale-event-guard-design.md相当)を必要としていた。forklift-pashaは
  既にフェーズ129・130で`stripe_webhook.py`の`handle_customer_subscription_deleted()`・
  `handle_customer_subscription_created()`が`canceled_at`の設定・クリアを冪等に行っており、
  このロジック自体に手を入れる必要がない。したがって本ventureでは`deletion_candidate_at`
  という別フィールドを新設せず、`canceled_at + 365日`を都度計算する関数
  (`list_deletion_candidates()`)のみを追加すれば足りる(読み出し専用、既存の書き込み経路
  には一切変更を加えない)。
- **連絡経路の分岐が不要。** data-retention-policy.md 4節のとおり、本ventureはLINEの
  フォロー/ブロック概念を持たず、メール送達可否の二択のみで足りる(他venture
  〈aircon-pasha等〉の`route_deletion_candidate_confirmation()`のような経路分岐ロジックは
  不要)。

## 3. 保存期間(再掲)

data-retention-policy.md 3節: `canceled_at`から**365日**後を削除候補化の基準とする
(他venture〈line-reservation-ai・course-set-pasha・aircon-pasha〉と揃えた暫定値)。

## 4. 実装(`prototype/deletion_candidate.py`)

- `list_deletion_candidates(store, now)`: `FleetOperatorStoreProtocol`
  (`trial_management.py`)を受け取り、`canceled_at`が設定済みかつ`now >= canceled_at +
  365日`の`internal_id`一覧をinternal_id昇順で返す(読み出し専用、既存の
  `is_subscription_canceled()`等とは独立した新規関数)。
- 最終確認送信: `trial_management.FleetOperatorStoreProtocol`に
  `get/set_deletion_confirmation_sent_at`・`get/set_deletion_confirmation_unreachable_at`の
  4メソッドを追加(`InMemoryFleetOperatorStore`にも実装)。`EmailSenderProtocol`
  (`send(internal_id, email) -> bool`、実メール送信サービスのアカウント作成がオーナー
  承認待ちのため、実装は別途のスタブのみ)を注入し、
  `send_deletion_candidate_final_confirmations()`が送信成功時は`sent_at`、失敗時(email未設定
  含む)は`unreachable_at`を設定する。送信済み・連絡不能いずれかが設定済みの候補は
  `select_due_deletion_candidate_final_confirmations()`で対象から除外する(再送しない、
  他venture同種関数と同じ冪等方針)。
- `list_unreachable_deletion_candidates(store, now)`・
  `render_unreachable_deletion_candidates_report(candidates)`: 他venture
  (line-reservation-ai等)と同じ、読み取り専用のオーナー向けレポート生成(削除実行・
  自動送信は一切行わない)。

## 5. スコープ外(承認待ちの範囲)

- 実際のメール送信サービスのアカウント作成・実送信、削除実行バッチのCloud Scheduler化は、
  既存の承認待ち事項(pending-approval.md 2026-10-06 22:00 UTC記載のStripe関連、および
  data-retention-policy.md 5節記載のCloud Scheduler化)の範囲内であり、本フェーズで新たな
  承認待ち事項は発生しない。

## 6. 次回候補

1. firestore-data-model.mdの`fleet_operator`フィールド一覧に`canceledAt`
   (フェーズ129で実装済みだが未反映だった記載漏れ)・`deletionConfirmationSentAt`・
   `deletionConfirmationUnreachableAt`を追記する(本フェーズで実施)。
2. 承認待ち事項(実Stripe/メール送信サービス等)がオーナーから承認された場合、実装着手を
   最優先。
3. 他venture・アイデア領域の前進。

## 7. Cloud Functionsエントリポイント(フェーズ153で追加)

`cloud_function_send_trial_end_emails.py`と同じ「本体は依存注入でテスト可能、`main(request)`
だけが実`functions_framework`リクエストを扱う薄い配線」構成で、
`prototype/cloud_function_send_deletion_confirmations.py`を新規実装した。
`list_deletion_candidates()` → `select_due_deletion_candidate_final_confirmations()` →
`send_deletion_candidate_final_confirmations()`の3関数を配線し、Cloud Scheduler(日次想定)の
HTTPトリガーから起動する想定とする。実メール送信手段が未確定の間は`_UnconfiguredEmailSender`
(常に送信失敗=`unreachable_at`設定)を既定の依存とし、楽観的に送信成功とみなして実際には
届いていないという状態を避ける安全側のフォールバックとした。テスト7件追加
(`test_cloud_function_send_deletion_confirmations.py`)、`run_all_tests.py`で全18ファイル
パスを確認。実デプロイ・実メール送信サービス接続は引き続き5節記載のとおり承認待ちの範囲。
