# 意図分類失敗の運用検知(最小構成)設計

chatbot-intent-classification-wiring-design.md フェーズ174が実装した
`_classify_chatbot_intent_with_retry()`のWARNINGログ出力について、course-set-pasha/
intent-classification-failure-observability-design.md・aircon-pasha側の同種設計を本
venture向けに横展開する(course-set-pashaフェーズ249「次回候補」・kura-pashaフェーズ174
「次回候補」で申し送られていたcross-venture parityギャップに対応)。

## 1. 前提の確認

tech-stack.mdの想定コンポーネント2により、本ventureもaircon-pasha・course-set-pashaと
同じGCP Cloud Functions (Python)をWebhook/バックエンドの第一候補としている
(line-reservation-aiで選定済みの構成を流用)。Cloud Functionsは標準`logging`モジュールの
出力を追加設定なしにCloud Loggingへ自動転送するため、専用のログ基盤を新規に整備する
必要はない。

`prototype/cloud_function_webhook.py`の`_classify_chatbot_intent_with_retry()`
(フェーズ174で実装済み)は、`chatbot_intent_classifier.classify()`が2回とも
`LlmApiError`となった場合に`_logger.warning()`で1件のログを既に出力している。
ログに含める情報も course-set-pasha と同じ最小限の2点に既に揃っている。

- `event`: 固定文字列`"chatbot_intent_classification_failed"`
- `memo_length`: `len(memo_text)`(メモの文字数のみ、本文自体は含めない)

つまり本venture固有のコード変更(ログ出力の実装自体)は既にフェーズ174で完了済みで
あり、course-set-pashaのintent-classification-failure-observability-design.mdが
1〜4節で行った検討のうち、本ドキュメントで新たに必要なのは「Cloud Logging上での
検知が可能である」という前提の確認と、cloud-monitoring-alert-policy-design.md
(本venture向けに別途作成)へつなぐcross-venture parityの記録のみである。

## 2. course-set-pashaとの差異確認

- ログ出力の実装位置(`_classify_chatbot_intent_with_retry()`という関数名も含めて)・
  ログの構造(`event`・`memo_length`の2フィールド、本文除外の方針)はいずれも
  course-set-pasha/aircon-pashaと同一であり、翻案は不要だった。
- 本venture固有の`craftsman_workshop/{workshop_id}`単位の課金構造(tech-stack.md 4節)は
  この意図分類失敗ログとは無関係(ログはworkshop_idやuser_idを含まず、メモ単位の
  分類失敗事象のみを記録する設計のため)であり、観測設計自体に翻案は発生しない。

## 3. スコープ外(次回以降の課題)

- Cloud Monitoringのログベース指標・アラートポリシーの具体的な設定値は
  cloud-monitoring-alert-policy-design.md(本venture向け新規作成)に譲る。
- 意図分類の成功率・レイテンシ等、失敗以外の運用指標の収集は本設計のスコープ外
  (course-set-pasha同様)。
- 実際のログベース指標・アラートポリシーの作成は、GCPプロジェクト作成
  (既存のオーナー承認待ち事項、tech-stack.md想定コンポーネント2)後の課題とする。
