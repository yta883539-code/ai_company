# 削除候補「連絡不能」ケースのオーナー対話確認フロー設計

作成日: 2026-10-13(フェーズ続き319)

## 1. 背景

data-retention-policy.mdは、削除候補化後の最終確認がLINE push(主経路)・メール
(代替経路、送信サービスのアカウント作成がオーナー承認待ちのため現状未接続)のいずれでも
行えなかった「連絡不能」ケースについて、自動削除には進まず、削除候補リストに連絡不能
フラグを付けたまま保持し、オーナー(本リポジトリの運営者)が対話セッションで個別に削除
可否を判断する運用とする方針を定めている(機械的な自動実行はしないという本リポジトリ
全体の方針に合わせたもの)。

フェーズ続き318で`storeDeletionConfirmationUnreachableAt`フィールド自体の追加・記録
(`send_store_deletion_confirmations()`が送信失敗時・owner_line_user_id未設定時に設定)
までは実装済みだが、オーナーがこのフラグ付き候補をどう参照して対話セッションで判断するか
の導線(一覧表示)が未設計のまま残っていた。本フェーズはこの欠落を埋める設計を行う。

## 2. スコープ

- 本機能は「読み取り専用のレポート生成」に限定する。削除実行・自動削除・外部への通知送信
  (メール・LINE再送信等)は一切行わない。
- オーナーへの提示は、本リポジトリの運営方式(README.md記載のとおり、オーナーが対話
  セッションでClaude Codeに直接指示する運用)に合わせ、本レポートを対話セッション内で
  表示する想定とする。Slack通知・メール送信等の自動送信は「メッセージの送信」に該当し
  承認待ち事項になるため、本機能のスコープには含めない。

## 3. 選定ロジックの設計(実装済み: `list_unreachable_store_deletion_candidates()`)

対象: `storeDeletionConfirmationUnreachableAt`が設定済みの店舗すべて。store_id昇順で
返す(list_store_deletion_candidates()と同じ、呼び出し順の非決定性を避ける方針)。
各候補には「連絡不能判定からの経過日数」(`now`との差分)を付与し、オーナーが対話で
優先度を判断しやすくする。

既知の限界として、現行の`StoreDeletionState`は連絡不能と判定された**理由**
(owner_line_user_id未設定か、LINE push送信失敗か)を永続化していない
(`send_store_deletion_confirmations()`はいずれの場合も同じフィールドに同じ値を書き込む
のみ)ため、本レポートは理由までは提示できない。理由の区別が必要になった場合は、
`storeDeletionConfirmationUnreachableReason`等の追加フィールドが次回候補となる。

## 4. レポート内容の設計(実装済み: `render_unreachable_store_deletion_candidates_report()`)

- 候補が0件の場合は「連絡不能の削除候補店舗はありません。」の1行のみを返す。
- 候補がある場合は、件数の見出し・各store_idと経過日数・判定日時の一覧・末尾に
  「本リストは自動削除の対象ではなく、オーナーが対話セッションで個別に削除可否を判断する」
  旨の注記を含める(自動削除であるかのような誤解を避けるため、注記は省略しない)。

## 5. 本フェーズのスコープ・実施内容

`prototype/store_deletion_candidate.py`に`UnreachableStoreDeletionCandidate`
データクラス・`list_unreachable_store_deletion_candidates()`・
`render_unreachable_store_deletion_candidates_report()`を実装し、
`StoreDeletionCandidateState`に`store_deletion_confirmation_unreachable_at`フィールドを
追加した(既存の`is_store_deletion_candidate()`・`list_store_deletion_candidates()`の
判定条件には影響しない追加フィールドのため、既存ロジック・既存テストへの後方互換性は
保たれる)。`test_store_deletion_candidate.py`にテスト4件を追加し、全927件パス
(`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証28件
(`python3 schema/validate_test_cases.py`)いずれもパスすることを確認した。

実Firestore接続・実際にオーナーへレポートを表示する対話セッションの運用自体は、本機能が
読み取り専用のレポート生成ロジックのみであるため新たな承認待ち事項を発生させない
(実Firestore接続自体は既存の承認待ち事項〈pending-approval.md参照〉の範囲内)。

## 6. 次回候補

1. 承認待ち事項(実Firestore/GCPプロジェクト等)がオーナーから承認された場合は本venture
   既存設計一式の実装着手を最優先。
2. 他venture(aircon-pasha・course-set-pasha・kura-pasha)の`deletion_candidate.py`にも
   同種の「連絡不能オーナーレビュー用レポート」機能が欠けていないかの横断点検・展開。
3. 他venture・アイデア領域の前進。
