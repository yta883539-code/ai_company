# Cloud Monitoringログベース指標・アラートポリシー設計(事前検討)

作成日: 2026-09-25(定例更新フェーズ261)

course-set-pashaのcloud-monitoring-alert-policy-design.md(フェーズ250)が「スコープ外」
として残していた「aircon-pasha側で同種の意図分類機能を実装する場合の本設計の横展開検討」に
対応する。フェーズ260で本venture向けに実装済みの`_classify_intent_with_retry()`が出力する
WARNINGログを対象に、Cloud Monitoringのログベース指標・アラートポリシーの設定内容を事前に
設計する。実際のGCPプロジェクト上での作成作業自体は、既存のオーナー承認待ち事項(GCPプロジェクト
作成、tech-stack.md想定コンポーネント)の範囲内であり実行しないが、承認・プロジェクト作成後に
即座に設定できるよう、設定値をここで確定しておく。

## 1. 前提

フェーズ260で`_classify_intent_with_retry()`が2回ともLlmApiErrorとなり`None`を返す直前に
WARNINGログ(`event=chatbot_intent_classification_failed`, `memo_length=<int>`)を出力する
実装が完了している(`prototype/cloud_function_webhook.py`)。course-set-pasha版と同じ
イベント名・フィールド構成であり、Cloud Functionsの標準`logging`連携により追加設定なしで
Cloud Loggingへ`jsonPayload`として転送される想定も同様(course-set-pashaのintent-
classification-failure-observability-design.md 1節と同じ考え方)。

## 2. ログベース指標(Log-based Metric)

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `chatbot_intent_classification_failure_count`(course-set-pasha版と同名)。
  各venture(aircon-pasha・course-set-pasha・kura-pasha)はそれぞれ別個のGCPプロジェクトを
  持つ想定(tech-stack.md)のため、venture間でのプロジェクト内リソース名の衝突は発生しない。
  同名を採用することで、将来複数venture分の運用ダッシュボードを横断比較する際にも指標名の
  読み替えが不要になる利点がある。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_function"
  jsonPayload.event="chatbot_intent_classification_failed"
  severity="WARNING"
  ```
  course-set-pashaのcloud-functions-generation-decision.md(2026-09-25 11:00 UTC定例更新)の
  確定に基づき、`resource.type`は`cloud_run_revision`を採用する(2nd gen / Cloud Run
  functionsに確定。Googleが新規プロジェクトでの1st gen新規作成を停止済みのため、本venture
  含め未着手の全venture共通で選択の余地がない)。`service_name`・`revision_name`等の
  具体的なリソースラベル値は実プロジェクト作成後(関数デプロイ後)でなければ確定できないため、
  この点のみ引き続き要確認として残す。
- ラベル: `memo_length`はメモごとに値が変わりカーディナリティが高いため、ログベース指標の
  ラベルには含めない(course-set-pasha版と同じ判断)。障害調査時はCloud Logging側の
  ログ本文(jsonPayload全体)を直接参照する運用とし、指標は「発生有無・頻度」の検知に
  用途を絞る。

## 3. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火するしきい値
  アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。course-set-pasha版と
  同じしきい値を採用する。
- しきい値を「1件以上」とした理由: 本ventureも`chatbot_intent`が`None`の場合は既存の完了
  報告書生成フローへフォールスルーする設計(フェーズ260、chatbot-intent-classification-
  escalation-design.md 5節)であり顧客影響は軽微だが、LLM API側の障害・レート制限等の
  前兆を早期に把握する目的のため、件数の多寡によらず発生自体を即検知する方針とする
  (course-set-pasha版と同じ理由付け)。将来的に誤検知(一時的なAPI瞬断等)が頻発する場合は、
  しきい値を「60分間で3件以上」等に緩和する調整を運用開始後に検討する。
- 通知チャネル: 本venture既存のオーナー(運営者)向け通知は、payment-suspension-owner-
  notification-design.md・chatbot-intent-classification-escalation-design.mdいずれも
  LINE Push固定送信先(`OWNER_LINE_USER_ID_PLACEHOLDER`)経由だが、Cloud Monitoringの
  アラートポリシーはメール・Slack・PagerDuty等の通知チャネルを指定できる方式でLINE Push経路
  とは異なる。本アラートは低頻度・技術的な運用監視目的であるため、既存のLINE通知導線を
  流用せず、course-set-pasha版と同じくCloud Monitoring標準のメール通知チャネル
  (`OWNER_ALERT_EMAIL_PLACEHOLDER`)を素直に使う方針とする。実際の送信先メールアドレス設定は、
  GCPプロジェクト作成(既存承認待ち事項)後にオーナー自身がCloud Monitoringコンソール上で
  設定する想定とし、本ドキュメントではプレースホルダのみを定義する。

## 4. スコープ外(引き続き次回以降の課題)

- 上記フィルタの`service_name`・`revision_name`等の具体的なリソースラベル値は、
  実プロジェクト作成後(関数デプロイ後)に要確認(世代自体はcloud-functions-generation-
  decision.mdにて2nd genに確定済み)。
- 意図分類の成功率・レイテンシ等、失敗以外の運用指標の収集(course-set-pasha版と同じく
  範囲外)。
- kura-pasha側の横展開検討: kura-pashaはフェーズ174(`prototype/cloud_function_webhook.py`
  `_classify_intent_with_retry()`)で本ventureと同一のイベント名・フィールド構成
  (`event=chatbot_intent_classification_failed`, `memo_length`)のWARNINGログを既に
  実装済みのため、本ドキュメントの2節・3節の設計はkura-pasha側にもそのまま適用可能と
  見込まれる。実際の横展開ドキュメント化・確定はkura-pasha側の次回以降の課題として残す。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`および
  `gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後にオーナー
  承認の範囲内で実施する。
