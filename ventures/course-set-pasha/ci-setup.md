# CI(GitHub Actions)によるテスト自動実行

## 背景
line-reservation-aiで先行導入していたGitHub Actionsによるテスト自動実行
(line-reservation-ai/ci-setup.md参照)が本ventureには未導入だった。動作確認が
「毎回コミット前に手動でpython3 -m unittestを実行する」運用に依存していたため、
機械的な実行漏れのリスクがあった。リポジトリ自体の設定変更のみで完結し、新規の
アカウント作成・支払い・外部公開のいずれにも該当しないため、承認を待たずに
着手できると判断した(フェーズ29、2026-08-08 21:00 UTC)。

## 実施内容
`.github/workflows/course-set-pasha-tests.yml`を新規作成。
`ventures/course-set-pasha/`配下への変更をトリガーに、以下を自動実行する。

1. `prototype/`のunittestスイート2本
   (test_history_export.py・test_post_generation_checks.py、計18件)
2. `schema/validate_test_cases.py`によるG1〜G4・OOS1・II1の期待出力6件の机上検証

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。

## 確認事項
- ローカルで`python3 -m unittest test_history_export test_post_generation_checks -v`を
  実行し18件全件パスを確認。
- `python3 validate_test_cases.py`を実行し6件全件パス・終了コード0を確認。

## 追記(2026-08-08 22:00 UTC): 実際のCI実行結果を確認
GitHub MCPツール(`mcp__github__actions_list`、method: list_workflow_runs、
resource_id: course-set-pasha-tests.yml)経由で、フェーズ29のコミット
(head_sha: 3305297、run id: 31280800500)のワークフロー実行結果を取得した。

- `status: completed` / `conclusion: success`(実行時間: 2026-08-08T22:03:29Z〜22:03:37Z、約8秒)。
- prototype/の自動テストスイート2本(計18件)・schema/validate_test_cases.py(6件)の
  両ステップともCI上で成功したことを確認した。line-reservation-aiと同様、今後は
  各コミット後にactions_listでグリーン確認を行う運用とする。

## 今後の課題
- 実LLM接続(オーナー承認待ち)が実現した際、結合テストをこのワークフローに
  追加するかを検討する。
