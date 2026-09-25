# Cloud Monitoringログベース指標・アラートポリシー設計(事前検討)

intent-classification-failure-observability-design.md(本venture向け新規作成)が
確認した、フェーズ174実装済みのWARNINGログ(`event=chatbot_intent_classification_failed`,
`memo_length=<int>`)を対象に、course-set-pasha/cloud-monitoring-alert-policy-design.md・
aircon-pasha側の同種設計を本venture向けに横展開する。実際のGCPプロジェクト上での作成
作業自体は、既存のオーナー承認待ち事項(GCPプロジェクト作成、tech-stack.md想定
コンポーネント2)の範囲内であり実行しないが、承認・プロジェクト作成後に即座に設定
できるよう、設定値をここで確定しておく。

## 1. ログベース指標(Log-based Metric)

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `kura_pasha_chatbot_intent_classification_failure_count`
  (aircon-pasha・course-set-pasha・line-reservation-aiの既存指標名を確認したところ、
  いずれも`chatbot_intent_classification_failure_count`という同一名を使っており、
  venture名を含めない場合は将来同一GCPプロジェクト配下で複数venture分を運用する際に
  指標名が衝突する可能性がある。他venture側の既存指標名を今から変更する必要は無いが、
  本venture分は新規作成のため、衝突を避けるため`kura_pasha_`接頭辞を付与する方針とした)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_function"
  jsonPayload.event="chatbot_intent_classification_failed"
  severity="WARNING"
  ```
  course-set-pasha側の既存設計と同様、`resource.type`はCloud Functions (2nd gen)の場合
  `cloud_run_revision`になる可能性があるため、実デプロイ時に採用するランタイム世代に
  応じて調整する(hosting-platform-selection.md・tech-stack.mdでは世代未確定のため、
  この1点は実プロジェクト作成後に要確認として残す)。
- ラベル: `memo_length`はカーディナリティが高く指標のラベルには不向きなため含めない
  (course-set-pashaと同じ方針)。障害調査時はCloud Logging側のログ本文
  (jsonPayload全体)を直接参照する運用とし、指標はあくまで「発生有無・頻度」の検知に
  用途を絞る。

## 2. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。
- しきい値を「1件以上」とした理由: course-set-pashaと同じく、意図分類は
  `chatbot_intent`が`None`でも既存の生成フロー(memo_processing_request相当)へ
  フォールスルーする設計(chatbot-intent-classification-wiring-design.md 4節、
  フェーズ174実装)であり顧客影響は軽微だが、LLM API側の障害・レート制限等の前兆を
  早期に把握する目的のため、件数の多寡によらず発生自体を即検知する方針とする。
  本ventureは低頻度受注特性(llm-api-cost-estimate.md、他ventureより受注件数自体が
  少ない)のため、同じ「1件以上」しきい値でも実際の発火頻度は他ventureより低くなる
  見込みだが、しきい値自体を緩める理由にはならないためcourse-set-pashaと同一の
  設定値を採用する。将来的に誤検知(一時的なAPI瞬断等)が頻発する場合は、しきい値を
  緩和する調整を運用開始後に検討する。
- 通知チャネル: payment-suspension-owner-notification-design.mdで確認した通り、本
  ventureの「オーナー(契約者・工房)向け通知」は`OWNER_LINE_USER_ID_PLACEHOLDER`への
  LINE Push固定送信先として設計済みである。本アラートは低頻度・技術的な運用監視目的
  であり、契約者向け業務通知とは経路・宛先(運営者自身であり契約者ではない)が異なる
  ため、既存のLINE通知導線は流用せず、course-set-pashaと同様にCloud Monitoring標準の
  メール通知チャネル(`OWNER_ALERT_EMAIL_PLACEHOLDER`)を素直に使う方針とする。実際の
  送信先メールアドレス設定は、GCPプロジェクト作成(既存承認待ち事項)後にオーナー自身が
  Cloud Monitoringコンソール上で設定する想定とし、本ドキュメントではプレースホルダの
  みを定義する。

## 3. スコープ外(引き続き次回以降の課題)

- 上記フィルタの`resource.type`は、Cloud Functions採用世代(1st gen / 2nd gen)確定後に
  要調整(他venture共通の課題)。
- 意図分類の成功率・レイテンシ等、失敗以外の運用指標の収集(intent-classification-
  failure-observability-design.md 3節から継続して範囲外)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後に
  オーナー承認の範囲内で実施する。
- line-reservation-ai向けの検討(会話状態管理を前提とする別構成のため、本設計を
  そのまま横展開できるかは別途course-set-pasha側の記載の通り同venture固有の課題として
  残る、本ドキュメントの範囲外)。
