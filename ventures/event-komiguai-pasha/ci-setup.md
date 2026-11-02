# CI(GitHub Actions)によるテスト自動実行

## 背景
aircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・line-reservation-aiでは
既にGitHub Actionsによるテスト自動実行(各venture/ci-setup.md参照)が導入済みだったが、
本ventureには未導入だった(cross-venture parityのギャップ)。動作確認が「毎回コミット前に
手動で`python3 -m unittest discover`・`python3 schema/validate_test_cases.py`を実行する」
運用に依存していたため、機械的な実行漏れのリスクがあった。リポジトリ自体の設定変更のみで
完結し、新規のアカウント作成・支払い・外部公開のいずれにも該当しないため、承認を待たずに
着手できると判断した。

## 実施内容
`.github/workflows/event-komiguai-pasha-tests.yml`を新規作成。
`ventures/event-komiguai-pasha/`配下への変更をトリガーに、以下を自動実行する。

1. `prototype/`のunittest discoverスイート(test_customer_email_matching.py・
   test_form_submission_intake.py・test_inquiry_intake.py・test_mock_llm_client.py・
   test_operational_message_templates.py・test_post_generation_checks.py、計63件)
2. `schema/validate_test_cases.py`によるoutput.schema.jsonの期待出力22件の机上検証

本venture配下のprototype/test_*.pyは全て`unittest.TestCase`ベースで記述されており、
kura-pashaのような独自check()/PASS/FAILスクリプト形式(discover非対応)は存在しない
ことを確認済みのため、line-reservation-ai・aircon-pasha等と同じ
`python3 -m unittest discover -p "test_*.py" -v`方式をそのまま採用した。

いずれも標準ライブラリのみで動作するため、追加の依存関係インストールは不要。

## 確認事項
- ローカルで`python3 -m unittest discover -p "test_*.py" -v`(prototype/配下)を実行し
  63件全件パスを確認。
- `python3 schema/validate_test_cases.py`を実行し22/22件パス・終了コード0を確認。
- 実際のGitHub Actions上での実行結果(グリーンの確認)は、このコミットのpush後に
  `mcp__github__actions_list`等で確認する必要がある(次回以降の実行時か、
  オーナー自身の確認に委ねる)。

## 今後の課題
- 実LLM/実GCP(Cloud Run functions・Firestore)接続(オーナー承認待ち、
  pending-approval.md 2026-10-28 06:00 UTC記載)が実現した際、結合テスト・デプロイを
  このワークフローに追加するかを検討する。
- line-reservation-ai・course-set-pashaで過去に発生した「テストファイル個別列挙による
  新規ファイル未反映バグ」は、本ventureでは当初から`discover -p "test_*.py"`方式を
  採用しているため発生しない。
