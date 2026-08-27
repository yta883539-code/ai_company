# CI(GitHub Actions)によるテスト自動実行

## 背景
line-reservation-ai・course-set-pashaで先行導入していたGitHub Actionsによる
テスト自動実行(各venture/ci-setup.md参照)が本ventureには未導入だった。動作確認が
「毎回コミット前に手動でpython3 -m unittest / validate_test_cases.pyを実行する」運用に
依存していたため、機械的な実行漏れのリスクがあった。リポジトリ自体の設定変更のみで
完結し、新規のアカウント作成・支払い・外部公開のいずれにも該当しないため、承認を
待たずに着手できると判断した(フェーズ26、2026-08-14 00:59 UTC)。

## 実施内容
`.github/workflows/aircon-pasha-tests.yml`を新規作成。
`ventures/aircon-pasha/`配下への変更をトリガーに、以下を自動実行する。

1. `prototype/`のunittestスイート2本
   (test_cloud_function_webhook.py・test_post_generation_checks.py、計28件)
2. `schema/validate_test_cases.py`によるG1〜G3・OOS1・II1の期待出力5件の机上検証

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。

## 確認事項
- ローカルで`python3 -m unittest test_cloud_function_webhook test_post_generation_checks -v`を
  実行し28件全件パスを確認。
- `python3 validate_test_cases.py`を実行し5件全件パス・終了コード0を確認。

## 今後の課題
- 実際のコミット後、course-set-pashaと同様`mcp__github__actions_list`でCI実行結果
  (status: completed / conclusion: success)を確認する。
- 実LLM接続(オーナー承認待ち)が実現した際、結合テストをこのワークフローに追加するかを検討する。
- (解消済み 2026-08-27・フェーズ131: フェーズ26でtest_cloud_function_webhook・
  test_post_generation_checksの2本を名指しでハードコードした後、フェーズ102前後で
  test_deletion_candidate・test_stripe_dispatch・test_stripe_webhook・
  test_user_id_linkingが追加されていたにもかかわらずワークフロー側の更新が漏れており、
  これらはCI上で実行されないまま残っていたことが判明した。`python3 -m unittest
  test_cloud_function_webhook test_post_generation_checks -v`を`python3 -m unittest
  discover -p "test_*.py" -v`に変更し、`prototype/`配下の新規テストファイルが今後
  ワークフロー側の追記漏れなく自動的に対象へ加わるようにした。ローカルで
  `python3 -m unittest discover -p "test_*.py" -v`を実行し178件全件パスを確認)
