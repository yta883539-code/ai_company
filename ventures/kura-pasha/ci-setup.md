# CI(GitHub Actions)によるテスト自動実行

## 背景
aircon-pasha・course-set-pasha・line-reservation-aiでは既にGitHub Actionsによる
テスト自動実行(各venture/ci-setup.md参照)が導入済みだったが、本ventureには未導入
だった(cross-venture parityのギャップ)。動作確認が「毎回コミット前に手動で
`python3 prototype/run_all_tests.py` / `python3 schema/validate_test_cases.py`を
実行する」運用に依存していたため、機械的な実行漏れのリスクがあった。リポジトリ自体の
設定変更のみで完結し、新規のアカウント作成・支払い・外部公開のいずれにも該当しない
ため、承認を待たずに着手できると判断した(フェーズ112)。

## 他venture(aircon-pasha等)との相違点: discover非互換への対応
他3ventureのワークフローはいずれも`python3 -m unittest discover -p "test_*.py" -v`で
`prototype/`配下の全test_*.pyを収集しているが、本ventureにこれをそのまま流用すると
テストの大半が実行されないままCIが「成功」扱いになる重大な問題がある。

- フェーズ88〜89で判明した通り、本ventureの`prototype/test_*.py`11ファイルのうち
  `unittest.TestCase`ベースで書かれているのは3ファイルのみで、残り8ファイル
  (`test_checkout_session.py`・`test_cloud_function_webhook.py`・
  `test_daily_scheduler.py`・`test_payment_failure_notification.py`・
  `test_stripe_webhook.py`・`test_subscription_cancellation_notification.py`・
  `test_subscription_plan_sync.py`・`test_usage_counter_workshop.py`)は独自の
  check()/PASS/FAIL関数と`if __name__ == "__main__":`直接呼び出しのスクリプト形式
  であり、`unittest.TestCase`クラスが存在しないため`discover`の収集対象にならない。
- フェーズ90の横展開確認で、この非互換は本venture固有の問題であり他3ventureには
  存在しないことを確認済み(cross-venture-discover-compatibility-review.md参照)。
- そのためフェーズ89で新設された`prototype/run_all_tests.py`(各test_*.pyを
  個別プロセスで実行し終了コードを集約するラッパー)をワークフロー側でも採用し、
  他venture同様の`unittest discover`コマンドは使用しないこととした。これにより
  11ファイル全件がCI上でも確実に実行される。

## 実施内容
`.github/workflows/kura-pasha-tests.yml`を新規作成。
`ventures/kura-pasha/`配下への変更をトリガーに、以下を自動実行する。

1. `prototype/run_all_tests.py`による単体テスト11ファイル一括実行
2. `schema/validate_test_cases.py`による期待出力30件の机上検証

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。

## 確認事項
- ローカルで`python3 prototype/run_all_tests.py`を実行し11ファイル全件パス
  (test_blocked_but_billing_candidates・test_blocked_but_billing_owner_
  notification・test_checkout_session・test_cloud_function_webhook・
  test_daily_scheduler・test_payment_failure_notification・test_stripe_webhook・
  test_subscription_cancellation_notification・test_subscription_plan_sync・
  test_usage_counter_workshop・test_workshop_linking)を確認。
- `python3 schema/validate_test_cases.py`を実行し30件全件パスを確認。

## 今後の課題
- 実際のコミット後、course-set-pashaと同様`mcp__github__actions_list`でCI実行結果
  (status: completed / conclusion: success)を確認する。
- 実LLM接続(オーナー承認待ち)が実現した際、結合テストをこのワークフローに追加するかを
  検討する。
- 他3ventureのci-setup.md「今後の課題」で記録されている「新規テストファイル追加時の
  ワークフロー側更新漏れ」問題は、本ventureでは`run_all_tests.py`が
  `HERE.glob("test_*.py")`で`prototype/`配下のtest_*.pyを動的に収集する実装のため、
  今後test_*.pyファイルが追加されてもワークフロー側の更新は不要(発生しない)。
