# CI(GitHub Actions)によるテスト自動実行

## 背景
aircon-pasha・course-set-pasha・event-komiguai-pasha・forklift-pasha・kura-pasha・
line-reservation-aiでは既にGitHub Actionsによるテスト自動実行(各venture/ci-setup.md参照)が
導入済みだったが、本venture(oshien-pasha)には未導入だった(cross-venture parityのギャップ)。
動作確認が「毎回コミット前に手動で`python3 -m unittest discover -s prototype`・
`python3 validate_test_cases.py`を実行する」運用に依存していたため、機械的な実行漏れの
リスクがあった。リポジトリ自体の設定変更のみで完結し、新規のアカウント作成・支払い・
外部公開のいずれにも該当しないため、承認を待たずに着手できると判断した。

## 実施内容
`.github/workflows/oshien-pasha-tests.yml`を新規作成。`ventures/oshien-pasha/`配下への
変更をトリガーに、以下を自動実行する。

1. `prototype/`のunittest discoverスイート(test_access_url_resend_handler.py・
   test_fan_pass_store.py・test_usage_counter.py、計8件)
2. `validate_test_cases.py`によるoutput.schema.jsonの期待出力(N1・N2・N3・N4_skip・
   N4_join・E1・E2・E3・E4、計9件)の机上検証

他venture(event-komiguai-pasha等)はschema検証スクリプトを`schema/validate_test_cases.py`に
配置しているが、本ventureでは`validate_test_cases.py`がventure直下(`ventures/oshien-pasha/`)に
配置されている構成の違いを確認済みのため、`working-directory`をその分変えて対応した。

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。

## 確認事項
- ローカルで`python3 -m unittest discover -s prototype -p "test_*.py" -v`を実行し8件全件
  パスを確認。
- `python3 validate_test_cases.py`を実行し9/9件パス・終了コード0を確認。
- 実際のGitHub Actions上での実行結果(グリーンの確認)は、このコミットのpush後に
  `mcp__github__actions_list`等で確認する必要がある(次回以降の実行時か、オーナー自身の
  確認に委ねる)。

## 今後の課題
- 自由文メッセージ(`out_of_scope_message`等)をprototype側にコード化する際は、他venture
  相当の絵文字不使用機械チェックをテストに追加し、本ワークフローでそのまま拾われるように
  する(フェーズ62次回候補(2)より)。
- 実LLM/実GCP(Cloud Run functions・Firestore)接続がオーナー承認後に実現した際、結合テスト・
  デプロイをこのワークフローに追加するかを検討する。
