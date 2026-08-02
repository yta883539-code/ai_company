# CI(GitHub Actions)によるテスト自動実行

## 背景
automated-test-suite.mdでprototype/engine.py等をunittest化して以降、動作確認は
「毎回コミット前に手動でpython3 -m unittestを実行する」運用に依存しており、
機械的な実行漏れのリスクがあった。GCPホスティング基盤(Cloud Functions等)の
実接続はオーナー承認待ちだが、GitHub Actionsによるテスト自動実行はこのリポジトリ
自体の設定変更のみで完結し、新規のアカウント作成・支払い・外部公開のいずれにも
該当しないため、承認を待たずに着手できると判断した。

## 実施内容
`.github/workflows/line-reservation-ai-tests.yml`を新規作成。
`ventures/line-reservation-ai/`配下への変更をトリガーに、以下を自動実行する。

1. `prototype/`のunittestスイート4本
   (test_engine.py・test_cloud_function_webhook.py・test_cloud_function_process_event.py・
   test_reminder_scheduler.py、計125件)
2. `schema/validate_test_cases.py`によるconversation-samples-test-cases.mdの
   期待JSON出力22件の机上検証

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。

## 確認事項
- ローカルで`python3 -m unittest test_engine test_cloud_function_webhook
  test_cloud_function_process_event test_reminder_scheduler -v`を実行し125件全件パスを確認。
- `python3 validate_test_cases.py`を実行し22件全件パス・終了コード0を確認
  (`main()`が失敗件数に応じて非ゼロを返す実装のため、CI上での失敗検知も機能する)。
- 実際のGitHub Actions上での実行結果(グリーンの確認)は、このコミットのpush後に
  リポジトリのActionsタブで確認する必要がある(本エージェントはCI実行結果の閲覧手段を
  持たないため、次回以降の実行時か、オーナー自身の確認に委ねる)。

## 今後の課題
- 実LLM/実LINE API/実Cloud Scheduler接続(オーナー承認待ち)が実現した際、
  結合テスト・デプロイをこのワークフローに追加するかを検討する。
- venture外(他のventureフォルダ)が増えた場合、ワークフロー名・pathsフィルタを
  venture単位で分割する運用を維持する。
