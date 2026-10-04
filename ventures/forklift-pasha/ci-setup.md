# CI(GitHub Actions)によるテスト自動実行

## 背景
aircon-pasha・course-set-pasha・kura-pasha・line-reservation-aiでは既にGitHub Actionsによる
テスト自動実行(各venture/ci-setup.md参照)が導入済みだったが、本ventureには未導入だった
(cross-venture parityのギャップ)。動作確認が「毎回コミット前に手動で
`python3 -m unittest discover -s prototype -p "test_*.py"` / `python3 schema/validate_test_cases.py`
を実行する」運用に依存していたため、機械的な実行漏れのリスクがあった。リポジトリ自体の
設定変更のみで完結し、新規のアカウント作成・支払い・外部公開のいずれにも該当しないため、
承認を待たずに着手できると判断した(フェーズ29)。

## discover非互換の発見: kura-pashaと同種の問題
aircon-pasha・course-set-pasha・line-reservation-aiのワークフローはいずれも
`python3 -m unittest discover -p "test_*.py" -v`で`prototype/`配下の全test_*.pyを収集して
いるが、本ventureにこれをそのまま流用すると、フェーズ26〜28で新規作成した
`test_due_date_logic.py`(15件)・`test_due_date_integration.py`(4件)・
`test_should_remind_integration.py`(9件)の計28件が実行されないままCIが「成功」扱いに
なる重大な問題を本フェーズで発見した。

- この3ファイルは`unittest.TestCase`を使わず、独自の`_check()`関数(PASS/FAIL判定)と
  `if __name__ == "__main__":`直接呼び出しのスクリプト形式(schema/validate_test_cases.py
  と同系統の書き方)であり、`unittest.TestCase`クラスが存在しないため`discover`の収集対象に
  ならない。
- `unittest.TestCase`ベースで書かれているのは`test_post_generation_checks.py`(フェーズ8、
  11件)のみで、discoverで実際に収集されるのはこの1ファイルだけであることを本フェーズで
  確認した(`python3 -m unittest discover -s prototype -p "test_*.py" -v`の実行結果が
  11件のみであることを確認)。
- kura-pashaが`prototype/run_all_tests.py`(各test_*.pyを個別プロセスで実行し終了コードを
  集約するラッパー)で同種の非互換を回避していたのを踏襲し、本ventureにも同名の
  `prototype/run_all_tests.py`を新規作成した。4ファイル全件(test_due_date_integration.py・
  test_due_date_logic.py・test_post_generation_checks.py・test_should_remind_integration.py)
  が個別の`python3 <file>`実行で正常終了(exit=0)することを確認済みであり、ワークフロー側は
  aircon-pasha等の`unittest discover`コマンドではなくこの`run_all_tests.py`を採用した。

## 実施内容
`.github/workflows/forklift-pasha-tests.yml`を新規作成。
`ventures/forklift-pasha/`配下への変更をトリガーに、以下を自動実行する。

1. `prototype/run_all_tests.py`による単体テスト4ファイル(計39件)一括実行
2. `schema/validate_test_cases.py`による期待出力11件の机上検証

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。

## 確認事項
- ローカルで`python3 prototype/run_all_tests.py`を実行し4ファイル全件パス
  (test_due_date_integration・test_due_date_logic・test_post_generation_checks・
  test_should_remind_integration)を確認。
- `python3 schema/validate_test_cases.py`を実行し11件全件パスを確認。

## 今後の課題
- 実際のコミット後、他venture同様`mcp__github__actions_list`でCI実行結果
  (status: completed / conclusion: success)を確認する。
- 実LLM接続(オーナー承認待ち)が実現した際、結合テストをこのワークフローに追加するかを
  検討する。
- 本venture側の`run_all_tests.py`は`HERE.glob("test_*.py")`で`prototype/`配下の
  test_*.pyを動的に収集する実装のため、今後test_*.pyファイルが追加されてもワークフロー側の
  更新は不要(発生しない、kura-pasha同様)。
- 名簿PDF本文に依存しない間接チャネル探索の再検討(フェーズ24・26から持ち越し、未着手)。
