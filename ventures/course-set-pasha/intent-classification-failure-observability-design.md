# 意図分類失敗の運用検知(最小構成)設計

chatbot-intent-router-webhook-wiring-design.md 8節(フェーズ246)が「分類失敗の発生自体を
運用上検知したい場合は、本venture共通のログ基盤(未整備、tech-stack.md参照)の整備が
前提となるため、次回以降の課題として残す」としていた点に対応する。

## 1. 前提の確認

tech-stack.mdを確認したところ、本ventureには専用のログ基盤(ログ集約サービス・監視
ダッシュボード等)の記載は無い。一方、想定コンポーネント2(Webhook/バックエンド)は
GCP Cloud Functions (Python)を第一候補としており、Cloud Functionsは標準出力・標準エラー
出力、および標準ライブラリ`logging`モジュールの出力を追加設定なしに自動でCloud Logging
へ転送する(GCPプロジェクト自体の作成は既存のオーナー承認待ち事項の範囲内)。

つまり「専用のログ基盤を新規に整備する」までは不要で、`logging`モジュールで警告ログを
出力するだけの最小限のコード変更で、実デプロイ後にCloud Logging上での検知が可能になる。
これは新たな外部サービス接続・アカウント作成・支払いを一切伴わないため、承認不要で
着手できる。

## 2. 設計方針

- `_classify_intent_with_retry()`が2回ともLlmApiErrorとなり`None`を返す直前に、
  `logging.getLogger(__name__).warning(...)`で1件のログを出力する。
- ログに含める情報は最小限とし、以下の2点に限定する。
  - `event`: 固定文字列`"chatbot_intent_classification_failed"`(Cloud Logging上で
    フィルタ・アラート条件のクエリキーとして使う想定)。
  - `memo_length`: `len(memo_text)`(メモの文字数のみ。内容そのものは含めない)。
- メモ本文(顧客の自由入力テキスト)自体はログに含めない。意図分類の失敗原因調査に
  本文が必要になった場合でも、ログという長期保存されがちな媒体に顧客の生入力を
  そのまま残すことは望ましくないため、本設計では意図的に除外する
  (post_generation_requestへのフォールスルー処理自体は本文を使い続けるため、
  実際の投稿文生成は失敗しない前提と両立する)。
- ログの出力形式は`logging`モジュールの標準的な`extra`引数を用いた構造化ロギングとし、
  メッセージ本文は人間可読な固定文言、`extra`に`event`・`memo_length`を持たせる。
  Cloud Logging側でのJSON構造化ログ連携(`jsonPayload`化)は、Cloud Functionsの
  Python標準ロギング連携の既定動作に委ねる(追加のフォーマッタ実装は本設計の
  スコープ外とし、必要になった時点で別途検討)。

## 3. スコープ外(次回以降の課題)

- Cloud Monitoringのログベース指標・アラートポリシーの作成は、実際のGCPプロジェクト
  上での設定作業であり、コード変更では完結しない。GCPプロジェクト作成自体は既存の
  オーナー承認待ち事項(tech-stack.md想定コンポーネント2)の範囲内であるため、
  ログベース指標・アラートポリシーの具体的な設定手順は、実際にプロジェクトが作成された
  後の課題として申し送る。
- 意図分類の成功率・レイテンシ等、失敗以外の運用指標の収集は本設計のスコープ外。
- aircon-pasha・kura-pasha側で同種の意図分類機能を実装する際に、本設計をそのまま
  横展開できるか(line-reservation-aiのような双方向会話状態を持つventureにも
  同様の最小構成ログ出力が適用できるか)の検討は、各venture側の次回以降の課題とする。

## 4. 実装

`prototype/cloud_function_webhook.py`の`_classify_intent_with_retry()`に上記の
警告ログ出力を追加し、`prototype/test_cloud_function_webhook.py`に
`assertLogs`を用いた検証テストを追加する(詳細はコード・テストコミット参照)。
