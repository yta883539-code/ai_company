# CI(GitHub Actions)によるテスト自動実行

## 背景
これまでprototype/(history_export.py・post_generation_checks.py)・
schema/validate_test_cases.pyの動作確認は「コミット前に手動でpython3 -m unittest等を
実行する」運用に依存しており、line-reservation-ai(ci-setup.md参照)と同様に機械的な
実行漏れのリスクが残っていた。実LLM接続はオーナー承認待ちだが、GitHub Actionsによる
テスト自動実行はこのリポジトリ自体の設定変更のみで完結し、新規のアカウント作成・
支払い・外部公開のいずれにも該当しないため、承認を待たずに着手できると判断した。

## 実施内容
`.github/workflows/course-set-pasha-tests.yml`を新規作成。
`ventures/course-set-pasha/`配下への変更をトリガーに、以下を自動実行する。

1. `prototype/`のunittestスイート2本
   (test_history_export.py・test_post_generation_checks.py、計18件)
2. `schema/validate_test_cases.py`によるschema/output.schema.json準拠の
   期待JSON出力6件(G1〜G4・OOS1・II1)の机上検証

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。
line-reservation-ai-tests.ymlと同じ構成(venture単位でワークフローファイルを分割)を踏襲した。

## 確認事項
- ローカルで`python3 -m unittest test_history_export test_post_generation_checks -v`を
  実行し18件全件パスを確認。
- `python3 validate_test_cases.py`を実行し6件全件パス・終了コード0を確認
  (失敗件数に応じて非ゼロ終了する実装のため、CI上での失敗検知も機能する)。
- 実際のGitHub Actions上での実行結果(グリーンの確認)は、このコミットのpush後に
  GitHub MCPツール(`actions_list`等)またはオーナー自身の確認に委ねる。

## 今後の課題
- 実LLM接続(オーナー承認待ち)が実現した際、生成結果の検証をこのワークフローに
  追加するかを検討する。
- venture外(他のventureフォルダ)が増えた場合も、line-reservation-aiと同様に
  ワークフロー名・pathsフィルタをventure単位で分割する運用を維持する。
