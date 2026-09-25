# Cloud Monitoringログベース指標・アラートポリシー設計(事前検討)

intent-classification-failure-observability-design.md 3節が「次回以降の課題」として
残していた、Cloud Monitoringのログベース指標・アラートポリシーの具体的な設定内容を
事前に設計する。実際のGCPプロジェクト上での作成作業自体は、既存のオーナー承認待ち
事項(GCPプロジェクト作成、tech-stack.md想定コンポーネント2)の範囲内であり実行しないが、
承認・プロジェクト作成後に即座に設定できるよう、設定値をここで確定しておく。

## 1. 前提

フェーズ249で`_classify_intent_with_retry()`が2回ともLlmApiErrorとなり`None`を返す直前に
WARNINGログ(`event=chatbot_intent_classification_failed`, `memo_length=<int>`)を
出力する実装が完了している(`prototype/cloud_function_webhook.py`)。Cloud Functionsの
標準`logging`連携により、このログは追加設定なしでCloud Loggingへ`jsonPayload`として
転送される想定(intent-classification-failure-observability-design.md 1節)。

## 2. ログベース指標(Log-based Metric)

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `chatbot_intent_classification_failure_count`
  (line-reservation-ai側に既存の同名指標が無いことを確認済み、venture間の命名衝突なし)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_function"
  jsonPayload.event="chatbot_intent_classification_failed"
  severity="WARNING"
  ```
  `resource.type`はcloud-functions-generation-decision.md(本フェーズ確定)により
  `cloud_run_revision`を採用する(2nd gen / Cloud Run functionsに確定。1st genは
  Googleが新規プロジェクトでの作成を停止済みのため選択の余地がない)。`service_name`・
  `revision_name`等の具体的なリソースラベル値は、実プロジェクト作成後(関数デプロイ後)
  でなければ確定できないため、この点のみ引き続き要確認として残す。
- ラベル: `memo_length`はカーディナリティが高く(メモごとに値が変わる)指標のラベルには
  不向きなため、ログベース指標のラベルには含めない。障害調査時はCloud Logging側の
  ログ本文(jsonPayload全体)を直接参照する運用とし、指標はあくまで「発生有無・頻度」の
  検知に用途を絞る。

## 3. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。
- しきい値を「1件以上」とした理由: 意図分類は`chatbot_intent`が`None`でも既存の生成
  フローへフォールスルーする設計(フェーズ246、design 3節・5節)であり顧客影響は
  軽微だが、LLM API側の障害・レート制限等の前兆を早期に把握する目的のため、件数の
  多寡によらず発生自体を即検知する方針とする。将来的に誤検知(一時的なAPI瞬断等)が
  頻発する場合は、しきい値を「60分間で3件以上」等に緩和する調整を運用開始後に検討する。
- 通知チャネル: Cloud Monitoringのアラートポリシーはメール・Slack・PagerDuty等の
  通知チャネルを指定できるが、本ventureはpayment-suspension-owner-notification-design.md
  で「オーナー(運営者)向け通知」をLINE Push固定送信先(`OWNER_LINE_USER_ID_PLACEHOLDER`)
  として設計済みであり、Cloud Monitoringの通知チャネルとは経路が異なる。本アラートは
  低頻度・技術的な運用監視目的であるため、既存のLINE通知導線を流用せず、Cloud
  Monitoring標準のメール通知チャネル(`OWNER_ALERT_EMAIL_PLACEHOLDER`)を素直に使う方針
  とする。実際の送信先メールアドレス設定は、GCPプロジェクト作成(既存承認待ち事項)後に
  オーナー自身がCloud Monitoringコンソール上で設定する想定とし、本ドキュメントでは
  プレースホルダのみを定義する(payment-suspension-owner-notification-design.mdの
  `OWNER_LINE_USER_ID_PLACEHOLDER`と同じ考え方)。

## 4. スコープ外(引き続き次回以降の課題)

- 上記フィルタの`service_name`・`revision_name`等の具体的なリソースラベル値は、
  実プロジェクト作成後(関数デプロイ後)に要確認(世代自体はcloud-functions-generation-
  decision.mdにて2nd genに確定済み)。
- 意図分類の成功率・レイテンシ等、失敗以外の運用指標の収集(intent-classification-
  failure-observability-design.md 3節から継続して範囲外)。
- aircon-pasha・kura-pasha側で同種の意図分類機能を実装する場合の本設計の横展開検討
  (同上、各venture側の課題として据え置き)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後に
  オーナー承認の範囲内で実施する。
