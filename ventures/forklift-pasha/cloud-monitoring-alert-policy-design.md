# Cloud Monitoringログベース指標・アラートポリシー設計(フェーズ192・新規作成)

runtime-dependency-switching-design.md 5.3節が「本venture未作成の
cloud-monitoring-alert-policy-design.md相当文書への横展開を次回候補とする」と
記載していた課題に対応し、本ファイルを本venture向けに新規作成する。
kura-pasha/cloud-monitoring-alert-policy-design.md 4節(フェーズ265、Firestore
ランタイム依存構築失敗アラート)と同型の設計を横展開するが、本ventureには
aircon-pasha・course-set-pasha・kura-pashaが備える「chatbot意図分類失敗」系の
既存アラート(1〜3節相当)は存在しない(1. 現状の棚卸しの通り、本ventureは
LINE非依存・Webフォーム+メール通知構成でchatbot自体が無いため)。したがって
本ファイルはFirestoreランタイム依存構築失敗アラートのみを対象として新規作成する。

実際のGCPプロジェクト上での指標・アラートポリシー作成作業自体は、既存のオーナー
承認待ち事項(実Firestoreプロジェクト・GCPアカウントの開設)の範囲内であり本フェーズ
では実行しないが、承認・プロジェクト作成後に即座に設定できるよう設定値をここで
確定しておく。

## 1. ログベース指標(Log-based Metric)

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `forklift_pasha_firestore_runtime_dependency_construction_failure_count`
  (kura-pashaの命名規則`<venture-prefix>_firestore_runtime_dependency_
  construction_failure_count`を踏襲し、将来同一GCPプロジェクト配下で複数venture分を
  運用する際の指標名衝突を避けるため`forklift_pasha_`接頭辞を付与する)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_run_revision"
  jsonPayload.event="firestore_runtime_dependency_construction_failed"
  severity="ERROR"
  ```
  `resource.type`は他venture側のcloud-functions-generation-decision.mdの確定
  (2nd gen / Cloud Run functions、Googleが新規プロジェクトでの1st gen新規作成を
  停止済みのため他venture共通で選択の余地がない)を踏襲する。本ventureには同種の
  決定文書がまだ無いため、本節の記載をもって本venture側の世代選択の確定記録とする。
  `service_name`・`revision_name`等の具体的なリソースラベル値は実プロジェクト作成後
  (4関数デプロイ後)でなければ確定できないため、引き続き要確認として残す。
- ログ出力側(runtime-dependency-switching-design.md 5.2節の擬似コード内
  `logger.exception(...)`)は現状メッセージ文字列のみで`event`キーを持たないため、
  他venture同様に結合実装フェーズで
  `logger.exception(..., extra={"json_fields": {"event": "firestore_runtime_dependency_construction_failed"}})`
  相当の構造化ログに揃える必要がある(本フェーズは設計のみ、`.py`実装への反映は
  次回候補)。
- severityをERRORとする理由: 本事象は「フラグON時に実Firestore接続が必要な場面で
  接続できていない」という設定・権限上の不具合であり、5.3節の整理の通り顧客影響
  (チェックアウト失敗・5xx応答・定期スケジューラ処理の未実行)を伴うため。

## 2. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。
  kura-pashaフェーズ265と同じく、フラグON時の構築失敗は即時表面化させる方針
  (5.1節)のため、しきい値を緩める理由がない。
- 通知チャネル: 本venture固有の対外(フリート事業者・紹介元団体)向け通知経路は
  Webフォーム+メール通知構成(tech-stack.md)であり運営者自身向けではないため、
  本アラートにはそのまま流用しない。他venture同様にCloud Monitoring標準のメール
  通知チャネル(`OWNER_ALERT_EMAIL_PLACEHOLDER`)を運営者自身向けの技術監視用途
  として新規に用いる。実際の送信先メールアドレス設定は、GCPプロジェクト作成
  (既存承認待ち事項)後にオーナー自身がCloud Monitoringコンソール上で設定する想定
  とし、本ドキュメントではプレースホルダのみを定義する。
- 対象関数が4つ(`get_checkout_runtime_dependencies()`・`get_stripe_runtime_
  dependencies()`・`get_deletion_confirmation_runtime_dependencies()`・
  `get_trial_end_email_runtime_dependencies()`)あるが、ログベース指標・アラート
  ポリシーはいずれも1節の共通`event`名で検知するため、関数ごとに個別の指標・
  ポリシーを分ける必要はない(kura-pashaが意図分類失敗とFirestore構築失敗の
  2指標に分けた理由は検知対象の種類が異なるためであり、本venture側の4関数は
  いずれも検知対象が同一〈Firestoreランタイム依存構築失敗〉であるため、kura-pasha
  とは異なり1指標に集約する)。

## 3. スコープ外(引き続き次回以降の課題)

- 1節のログ出力側(`.py`実装)への`event`フィールド構造化反映は、実
  `google-cloud-firestore`導入・本venture用Firestoreアダプタ設計(access-token-
  store-firestore-adapter-design.md以外の3関数向けアダプタ設計)とセットの結合実装
  フェーズに持ち越す。
- `resource.type`のリソースラベル値(`service_name`等)は、実プロジェクト作成後に
  4関数それぞれのデプロイ単位を確認して確定する。
- `get_checkout_runtime_dependencies()`(LP/フォーム経由のチェックアウト起点、
  5.3節)で発生した場合の申込者向けエラー表示自体の文面設計は、本ファイルの
  範囲外(承認後の結合実装フェーズでの別途検討)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト
  作成後にオーナー承認の範囲内で実施する。

最終更新: 2026-10-26 01:00 UTC (フェーズ192: runtime-dependency-switching-design.md
5.3節の次回候補「本venture未作成のcloud-monitoring-alert-policy-design.md相当
文書への横展開」に対応し、本ファイルを新規作成。kura-pashaフェーズ265の
Firestoreランタイム依存構築失敗アラート設計(同ファイル4節)を横展開したが、
本ventureにはchatbot意図分類失敗系の既存アラートが無いため、Firestore構築失敗
アラートのみを対象とした。これでkura-pasha・aircon-pasha・course-set-pasha・
forklift-pashaの4venture全てにFirestoreランタイム依存構築失敗アラート設計が
揃った。残る横展開先はline-reservation-aiのみ。)
