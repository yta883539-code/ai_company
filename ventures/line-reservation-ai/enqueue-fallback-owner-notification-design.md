# enqueueフォールバック発生時のオーナー通知 設計(line-reservation-ai版)

course-set-pasha・aircon-pashaのenqueue-fallback-owner-notification-design.mdを、cross-venture
parityの観点で本venture未作成分として横展開する設計(本venture側はこれまで未着手だった)。

## 1. 他venture版との前提の違い

course-set-pasha・aircon-pasha版は、`dispatch_webhook_events()`がCloud Tasksへの
`create_task()`失敗時に**同期処理へフォールバック**(その場でFunction B相当のロジックを
直接呼ぶ)した上で、その旨をオーナーへ通知する設計だった。

本venture(`prototype/cloud_function_webhook.py`)の`handle_webhook_event()`は、
`TaskAlreadyExistsError`のみを捕捉し、それ以外の例外(Cloud Tasksのクォータ超過・一時的な
ネットワーク障害等)は捕捉せずそのまま呼び出し元へ伝播する。この状態で`webhook_receiver()`の
forループに達すると、`except ValueError`では捕捉されず例外が外へ伝播し、同じリクエスト内の
後続イベントも含めて200応答自体が返せなくなる。これはwebhook-async-processing-design.md・
webhook-function-a-implementation.mdが明言する「個々のイベント処理の異常では200を維持し
LINE側の不要な再送連鎖を避ける」という設計方針に反するギャップであり、本フェーズで発見した。

## 2. 採用方針: 同期フォールバックではなく「enqueue断念+オーナー通知」

Function A(`webhook_receiver`)はwebhook-async-processing-design.md上「署名検証・構造
チェック・enqueueのみを行い、LLM呼び出しは一切行わない」という単一責務に設計されている。
course-set-pasha版のように同期フォールバックでFunction B相当のLLM呼び出しをA内で直接行うと、
この責務分離(Aの応答時間をLLM待ちから完全に切り離す、という非同期処理設計の目的そのもの)を
破ることになる。したがって本venture版では、enqueue失敗時はそのイベントの処理を断念し
(顧客への応答は行われない)、オーナーへ「対応漏れの可能性」を知らせることを優先する設計とする。

## 3. 実装方針

- `handle_webhook_event()`に、`TaskAlreadyExistsError`以外の例外を捕捉する分岐を追加し、
  `EventHandleResult(webhook_event_id, enqueued=False, reason="enqueue_failed")`を返す
  (例外を外へ伝播させない)。
- `webhook_receiver()`側で`reason == "enqueue_failed"`の`webhook_event_id`を集約し、
  `WebhookReceiverResult`に新規フィールド`enqueue_failed_webhook_event_ids: list[str]`を
  追加する。
- `owner-notification-channel-design.md`準拠の既存チャネル(店舗設定の`owner_user_id`への
  LINE Push、`_notify_owner()`ヘルパー)を再利用し、プレーンテキストで通知する
  (本venture一貫のLINE Push送信は`_send()`/`_notify_owner()`経由でプレーンテキストが基本形、
  aircon-pasha版のようなFlex Message専用クライアントではないため、course-set-pasha版と同じ
  プレーンテキスト方式を踏襲する)。
- 通知文言(案):
  ```
  [予約管理アシスタント運営より] 一部のお客様メッセージの処理に失敗しました。
  Cloud Tasksへのキュー登録でエラーが発生したため、以下のメッセージは未処理のままです。
  件数: {count}件
  webhookEventId: {先頭5件、残りは「...他N件」}
  お客様から返信がないとのお問い合わせがあった場合は、直接ご確認をお願いします。
  ```
- 送信タイミング・冪等性の考え方(1回のリクエスト処理内でのdigest、永続的な通知済みフラグは
  持たない、送信失敗時の再送は行わずCloud Loggingでの事後確認を代替とする)はcourse-set-pasha
  版の設計をそのまま踏襲する。

## 4. 残課題

- `owner_user_id`は店舗ごとの設定値のため、本関数はstoreId解決後(`destination`からの
  `resolve_store_id_from_destination()`経由、store-id-resolution-and-owner-identity-design.md
  準拠)に呼ばれる想定だが、Function A自体はstoreId単位の店舗設定ストアに現時点でアクセスしない
  設計(ステートレスなenqueueのみ)のため、本通知の送信元をA・Bどちらに置くかは未確定。
  候補: (a) Aがenqueue失敗イベントをそのまま返り値に残し、呼び出し元(HTTPハンドラ)が店舗設定
  ストアを引いて通知する、(b) enqueue失敗イベント自体を別の軽量キュー/ログに記録し、Bまたは
  定期実行ジョブが後から拾って通知する。次回フェーズで検討する。
- 実コード変更(`cloud_function_webhook.py`の例外捕捉分岐・テスト追加)・実LINE Push送信・
  実Cloud Tasksデプロイは、既存の「実GCPプロジェクト・LINE API接続はオーナー承認待ちの範囲」
  に含まれる(新規の承認待ち事項としては扱わない)。コード変更は次回フェーズで着手する。
