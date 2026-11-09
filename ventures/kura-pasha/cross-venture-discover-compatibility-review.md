# cross-venture discover互換性レビュー

## 背景

フェーズ89で、本venture(kura-pasha)の`prototype/`配下9ファイルのうち6ファイル
(test_checkout_session.py・test_cloud_function_webhook.py・
test_payment_failure_notification.py・test_stripe_webhook.py・
test_subscription_cancellation_notification.py・test_usage_counter_workshop.py)が
`unittest.TestCase`を使わない独自のcheck()/PASS/FAIL形式のスクリプトであるため、
`python3 -m unittest discover -s prototype -p "test_*.py"`では収集されない
(3ファイル・44件しか拾わない)ことが判明した。フェーズ89はこの原因調査と
`run_all_tests.py`ラッパーの新規作成で解消したが、「他venture(aircon-pasha・
course-set-pasha・line-reservation-ai)にも同じdiscover非互換が存在する可能性がある」
という横展開の要否確認が次の課題として残っていた。本ドキュメントはその確認結果を記録する。

## 確認方法

各ventureの`prototype/`配下で以下を実行し、収集件数がコミット履歴で従来報告されている
テスト総数と一致するかを確認した。

```
python3 -m unittest discover -s prototype -p "test_*.py"
```

## 確認結果

| venture | discover実行結果 | 従来報告のテスト総数 | 一致 | discover非互換 |
| --- | --- | --- | --- | --- |
| line-reservation-ai | Ran 771 tests ... OK | 771件 | 一致 | なし |
| aircon-pasha | Ran 475 tests ... OK | 475件 | 一致 | なし |
| course-set-pasha | Ran 575 tests ... OK | 575件 | 一致 | なし |
| kura-pasha(参考・フェーズ89で対応済み) | 従来は3ファイル・44件のみ収集 | 649件 | 不一致(対応済み) | あり(run_all_tests.py新設で解消) |

line-reservation-ai・aircon-pasha・course-set-pashaの3ventureはいずれも
`python3 -m unittest discover`一発で全テストファイルが収集され、従来コミットメッセージが
報告してきたテスト総数とも一致することを確認した。念のため各venture内の全test_*.pyファイルが
`unittest.TestCase`を継承しているか(`grep -c "TestCase" prototype/test_*.py`)も確認し、
いずれのファイルも1件以上ヒットすることを確認した(kura-pashaの6ファイルのように
`unittest.TestCase`を一切使わない独自スクリプト形式のファイルは存在しない)。

## 結論

discover非互換はkura-pasha固有の問題であり、フェーズ89の`run_all_tests.py`新設で
既に解消済みである。line-reservation-ai・aircon-pasha・course-set-pashaへの横展開は
不要と結論する。フェーズ89の「次の課題」はこれで解消済みとする。

## 追記(2026-11-09 09:00 UTC、oshien-pashaフェーズ103による発見)

本レビューはフェーズ89時点(2026年9月頃)で存在した4venture
(line-reservation-ai・aircon-pasha・course-set-pasha・kura-pasha)のみを対象としており、
その後新設されたforklift-pasha・event-komiguai-pasha・oshien-pashaは確認対象に含まれて
いなかった。oshien-pashaフェーズ103で確認したところ、forklift-pashaは別途自力で同種の
discover非互換を発見し`prototype/run_all_tests.py`を導入済み(本文書の確認対象外だった)、
event-komiguai-pashaは全test_*.pyがTestCase形式でdiscover非互換なし、oshien-pashaは
discover非互換が未対応のまま回帰確認から5ファイルが漏れていたため、oshien-pasha
フェーズ103で`run_all_tests.py`を新設し対応した。「discover非互換はkura-pasha固有の問題」
という上記結論は、本レビュー作成時点に存在した4venture限定の結論であり、venture新設時には
改めて本チェックを行う必要がある旨をここに記録する。
