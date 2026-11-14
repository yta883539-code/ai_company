# enqueueフォールバック発生時のオーナー通知 設計(aircon-pasha版)

course-set-pashaのenqueue-fallback-owner-notification-design.md(フェーズ374)を、
process-memo-event-async-split-design.md「残課題・次回候補(2)」(本venture等への横展開
確認)の一環として本ventureへ横展開する設計。本ventureの`dispatch_webhook_events()`は
既にフェーズ380〜382相当で`result.enqueue_fallback_webhook_event_ids`(Cloud Tasksへの
`create_task()`が`TaskAlreadyExistsError`以外の例外で失敗し、同期処理へフォールバックした
`webhookEventId`の一覧)を記録しているが、course-set-pashaのように非空になった際に
オーナーへ知らせる通知の配線は未着手だったため、本設計で対応する。

## 1. 送信先・既存2設計との関係

course-set-pasha版と同じ考え方(blocked-but-billing-owner-notification-design.md・
payment-suspension-owner-notification-design.mdが確立した「顧客ごとのuser_idではなく
固定のオーナー1件へLINE Push」というチャネル設計)を踏襲する。送信先は
`OWNER_LINE_USER_ID_PLACEHOLDER`(本venture既存定数、`blocked_but_billing_owner_
notification.py`で定義済みのものを再利用し、新規の承認待ち事項は増やさない)。

## 2. course-set-pasha版との違い:Flex Message形式の採用

course-set-pasha版はプレーンテキストの`send_message()`で送信するが、本venture一貫の
`LinePushClient`(trial_end_scheduler.py)はプレーンテキストではなくFlex Message
(`send_flex_message(user_id, alt_text, contents)`)のみを提供するため、
payment_suspension_owner_notification.py・blocked_but_billing_owner_notification.pyと
同様に、ボタンを持たないシンプルなbubble形式のFlex Messageを組み立てる。

発火タイミング・冪等性の考え方(「1回のdispatch_webhook_events()呼び出し内でのdigest、
1イベント=1通ではない」「永続的な通知済みフラグは持たない」「送信失敗時の再送は行わず
Cloud Loggingでの事後確認を代替手段とする」)はcourse-set-pasha版の設計(2〜3節)を
そのまま踏襲する(対象がwebhookEventIdであり、顧客の状態ではないため)。

## 3. 通知文言(Flex Message)

```
altText: "[エアコンパシャッと運営] Cloud Tasksへのenqueue失敗のお知らせ"

bubble本文:
  以下のWebhookイベントで、Cloud Tasksへのenqueueに失敗したため同期処理へ
  自動フォールバックしました(顧客への応答自体は正常に行われています)。
  件数: {count}件
  webhookEventId: {webhook_event_id_list}

  Cloud Tasksのクォータ超過や一時的なネットワーク障害が疑われます。頻発する場合は
  Cloud Tasksの設定(クォータ・リトライポリシー)をご確認ください。
```

`webhook_event_id_list`はcourse-set-pasha版と同じく先頭5件までを列挙し、残りは
「...他{N}件」と要約する。

## 4. 実装方針

- `enqueue_fallback_owner_notification.py`を新設し、
  `build_enqueue_fallback_owner_notification_flex_message(webhook_event_ids)`・
  `send_enqueue_fallback_owner_notification(webhook_event_ids, push_client,
  owner_line_user_id=...)`を実装する。course-set-pasha版と異なり戻り値はFlex Message用の
  `dict`(`build_...`)であり、`format_...`(プレーンテキスト)は持たない。永続ストアへの
  依存を持たない点はcourse-set-pasha版と同じ。
- `receive_webhook()`に新規オプション引数`enqueue_fallback_owner_push_client:
  Optional[LinePushClient] = None`を追加し、`dispatch_webhook_events()`呼び出し後に
  `dispatch_result.enqueue_fallback_webhook_event_ids`が非空かつ本引数が指定されていれば
  `send_enqueue_fallback_owner_notification()`を呼ぶ。未指定(`None`)時は何もしない
  (既存の全オプション引数と同じ後方互換パターン)。
- 本フェーズで併せて解消する既存ギャップ: `receive_webhook()`はこれまで
  `dispatch_webhook_events()`が受け取る`task_queue_client`引数自体を一切橋渡ししておらず
  (常に`None`扱いでFAQ/非FAQ振り分けが発火しない状態だった)、本フェーズで
  `task_queue_client`も`receive_webhook()`の引数として追加し`dispatch_webhook_events()`へ
  橋渡しする。これにより、実デプロイ後に`task_queue_client`を渡せば振り分け・enqueue
  フォールバック通知の両方が機能するようになる。

## 5. 残課題

- 実LINE Push Message APIでの送信・実オーナーLINEユーザーIDの設定・実Cloud Tasksデプロイは、
  既存の「実GCPプロジェクト・LINE API接続はオーナー承認待ちの範囲」に含まれる(新規の
  承認待ち事項としては扱わない)。
- kura-pashaへの同種横展開(process-memo-event-async-split-design.md「残課題・次回候補(2)」
  のうち本venture分は本フェーズで解消、kura-pasha分は未着手のまま残す)。
