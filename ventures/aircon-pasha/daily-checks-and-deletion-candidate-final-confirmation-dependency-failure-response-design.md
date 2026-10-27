# 日次/月次スケジューラ2エントリポイント: Firestoreランタイム依存構築失敗時の挙動確認(フェーズ349)

README.mdフェーズ348の次回候補(2)「cloud-monitoring-alert-policy-design.md 5.2節の
残り2エントリポイント(`get_daily_checks_runtime_dependencies()`・`get_deletion_
candidate_final_confirmation_runtime_dependencies()`)の同種ギャップ確認」を受け、
フェーズ347(申込フォーム)・フェーズ348(Stripe webhook)と同じ観点で、この2エント
リポイントにも「`main()`側レスポンス設計の欠落」という同種のギャップが存在するかを
確認する。

## 1. 結論: 同種のギャップは存在しない(呼び出し元がレスポンス本文を解釈しないため)

フェーズ347・348のギャップはいずれも「呼び出し元(GAS/Stripe)がレスポンス本文
(JSON/ステータスコード)を解釈し、それに基づく挙動(リトライ・エラー記録)を取る」
という前提のもとで、`main()`側がFirestoreランタイム依存構築失敗時に何を返すかが
未設計だった点にあった。

本venture固有のCloud Scheduler HTTPトリガー(`cloud_function_run_daily_checks.py`・
`cloud_function_send_deletion_candidate_final_confirmations.py`)はこの前提を欠く。

- Cloud SchedulerのHTTPターゲットは、レスポンス本文を一切解釈しない(呼び出し成否の
  判定はHTTPステータスコードのみで行い、ボディの内容はCloud Loggingに記録される以外
  の用途を持たない)。GASの`UrlFetchApp.fetch()`側コードやStripeのWebhook再送判定の
  ように、レスポンスボディのJSON形状(`{"ok", ...}`等)を業務的に解釈する呼び出し元が
  存在しない。
- したがって、フェーズ347・348が行った「401/400と同じJSON形状に揃える」「技術詳細を
  含まない`error`文言にする」といった設計上の判断は、そもそも適用対象(解釈する相手)
  が無いため本2エントリポイントには転用できない。

よって、runtime-dependency-switching-design.md 5.3節が既に整理済みの「例外伝播により
Cloud Functions実行がエラー終了し、Cloud Loggingにエラーログが記録され、cloud-
monitoring-alert-policy-design.md 5節のアラートが発火する」という挙動で言及として足り、
`main()`側に追加のレスポンス設計(JSON形状の決定等)を新設する必要はないと判断する。

## 2. 一方で存在する別種の論点: Cloud Scheduler自体のジョブ内リトライ設定

フェーズ347はGAS側に`main()`呼び出しの指数バックオフリトライ(最大3回)を設計し、
フェーズ348はStripeの自動再送に委ねる整理を行った。本2エントリポイントにも対応する
論点として、「1回の起動が失敗した場合、次に再試行されるのはいつか」を確認する。

- Cloud Schedulerジョブ自体は、ターゲットが5xxを返した場合に備えた`retry_config`
  (`retry_count`・`min_backoff_duration`・`max_backoff_duration`等)を持つことができる
  (Cloud Scheduler機能として標準で存在)。本venture側はこの設定について、trial-end-
  scheduler-design.md・payment-failure-reminder-scheduler-design.md・本2エントリ
  ポイントの設計のいずれにも記載がなく、未決定のまま残っている(本venture固有の欠落
  ではなく、Cloud Scheduler構成を持つ全 venture 共通の未決定事項である可能性が高いが、
  本フェーズでは本venture分のみを対象として確認する)。
- `retry_config`を設定しない場合(デフォルト、`retry_count`実質0相当)、1回の起動失敗は
  「次回の定期起動まで再試行されない」ことになる。この待機期間が、日次バッチ
  (`run_daily_checks`)と月次バッチ(`send_deletion_candidate_final_confirmations`)で
  2桁近く異なる点が、本フェーズで確認すべき実質的な論点である。

### 2.1. `run_daily_checks`(日次): 待機期間は最大約24時間

日次バッチが1回失敗しても、次の起動は約24時間後であり、かつ選定ロジック自体が
「状態条件のみで判定する冪等な抽出」(1節で参照したdeletion-candidate-final-
confirmation-scheduler-design.md 2節と同じ設計思想。日次チェック群も同様に実行間隔に
依存しない抽出条件を採用済み)であるため、1回分の遅延は翌日の起動で自然に解消される。
他の日次バッチ(trial_end_scheduler等)も同じ前提で運用されており、本バッチのみ特別な
`retry_config`を要する理由はない。

### 2.2. `send_deletion_candidate_final_confirmations`(月次): 待機期間は最大約1ヶ月

月次バッチが1回失敗すると、次の起動は約1ヶ月後になる。deletion-candidate-final-
confirmation-scheduler-design.md 3節の冪等性設計(`deletion_confirmation_sent_at`
未設定の候補を毎回抽出)により、1ヶ月遅れても対象候補を取り逃すことはなく、データの
不整合(二重送信・取り逃し)は生じない。

ただし、data-retention-policy.mdが定める削除候補化(`deletion_candidate_at`)から実際の
削除実行までの猶予期間の中で、本最終確認通知の送信自体が最大1ヶ月遅延すると、利用者
(店舗オーナー)が削除前に異議を申し立てられる実質的な期間がその分短縮される可能性が
ある。これは1回限りのHTTP応答設計(フェーズ347・348の対象)とは異なる、猶予期間の
実効性に関わる論点であり、本フェーズの範囲(Firestoreランタイム依存構築失敗時の
レスポンス設計)を超える。

## 3. 本フェーズの結論

- `main()`側のレスポンス設計という意味での、フェーズ347・348と同種のギャップは
  本2エントリポイントには存在しない(1節)。
- `retry_config`(Cloud Schedulerジョブ自体のリトライ設定)という、構造が異なる関連論点
  が未決定のまま存在することを確認した(2節)。日次バッチは現状のまま(`retry_config`
  未設定、翌日起動での自然な再試行に委ねる)で問題ないと判断するが、月次バッチは
  猶予期間の実効性という観点から、`retry_config`を設定する(例: 同日中に数回まで
  再試行する)価値があるかを次回候補として検討する。
- いずれも設計文書の確認・記述のみであり、コード変更は行わない。

## 4. 残課題(次回候補)

1. `send_deletion_candidate_final_confirmations`用の`retry_config`(具体的な
   `retry_count`・バックオフ値)を設計するかどうかの検討、および設計する場合の
   deletion-candidate-final-confirmation-scheduler-design.mdへの反映。
2. 本2節で確認した「Cloud Schedulerの`retry_config`が全venture共通で未決定」という
   事項が、他venture(kura-pasha・course-set-pasha・forklift-pasha・line-reservation-ai)
   のCloud Schedulerジョブにも共通する欠落かどうかの横断確認(本venture側からの
   直接着手は行わず、各venture側の次回候補として申し送るに留める)。
3. 承認待ち事項(実GCPプロジェクト・Cloud Scheduler実行環境の構築)がオーナーから
   承認された場合はその着手を最優先、その次に他venture・アイデア領域の前進。

最終更新: 2026-10-27 20:00 UTC(フェーズ349: 詳細は上記。日次/月次スケジューラ
2エントリポイントには、フェーズ347・348と同種の「`main()`側レスポンス設計の欠落」は
存在しないと判断した一方、Cloud Scheduler自体の`retry_config`未決定という別種の論点を
新たに発見した。コード変更なし〈設計文書新規作成のみ〉、回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(789件、変更なし)・
`python3 schema/validate_test_cases.py`(25件、変更なし)を実行しいずれも変更なしで
パスすることを確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。)
