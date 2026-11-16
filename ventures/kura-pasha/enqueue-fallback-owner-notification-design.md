# enqueueフォールバック発生時のオーナー通知 設計(鞍パシャッと版)

course-set-pasha/enqueue-fallback-owner-notification-design.md(フェーズ374)の横展開。
aircon-pashaフェーズ384(2026-11-14 09:00 UTC)に続き、本venture(鞍パシャッと)でも
同じ「Cloud Tasksへのenqueue失敗時に同期処理へフォールバックした件数をオーナーへ
digest通知する」設計が必要と判明したため作成する。

## 0. 本ventureに適用できると判断した根拠

aircon-pashaフェーズ384の次回候補は「kura-pashaへの横展開は未着手のまま残す」として
いたが、本venture独自のFunction A/B分割設計(webhook-async-two-function-design.md)を
確認した結果、`dispatch_webhook_events()`のCloud Tasks `create_task()`が
`TaskAlreadyExistsError`以外の例外(クォータ超過・ネットワーク障害等)で失敗した場合、
course-set-pashaと全く同じ「同期処理へ自動フォールバックし`result.enqueue_fallback_
webhook_event_ids`に記録する」という挙動を既に実装済み(`DispatchResult`のフィールド名も
同一)であることを確認した。したがって line-reservation-ai版(「enqueue断念+オーナー
通知」、Function A単一責務設計のため同期フォールバック自体を行わない)とは異なり、本
ventureは course-set-pasha/aircon-pasha と同型の「同期フォールバック済みの件数を
インシデントとして知らせる」設計がそのまま成立する。

## 1. 送信先

既存の blocked-but-billing-owner-notification-design.md(フェーズ143)・
payment-suspension-owner-notification-design.md(フェーズ125)と同一の
`OWNER_LINE_USER_ID_PLACEHOLDER`(本venture側は blocked_but_billing_owner_
notification.py で定義済みのものを再利用)。新たな通知チャネルの検討は行わない。

## 2. 発火タイミング・冪等性の考え方

course-set-pasha版の設計をそのまま踏襲する。

- `enqueue_fallback_webhook_event_ids`は顧客の状態ではなく「1回の`dispatch_webhook_
  events()`呼び出し内でCloud Tasksへのenqueueが一時的に失敗した」という運用上の
  インシデント信号であるため、永続的な「通知済みフラグ」は持たない(各`webhookEventId`は
  `webhook_event_id_store`による既存の重複排除で再出現しない前提)。
- 日次バッチではなく、`receive_webhook()`呼び出し直後(HTTPリクエスト処理の中)に
  `enqueue_fallback_webhook_event_ids`が非空であれば即座に1回だけdigest通知を送る。
- 1リクエスト内で複数の`webhookEventId`がフォールバックした場合も、リクエストごとに
  1通のdigestとしてまとめて送る(個別送信によるオーナーLINEのスパム化を避ける)。

## 3. 送信失敗時の扱い

通知送信の失敗(`LinePushDeliveryError`)は握りつぶし、再送・リトライの仕組みは設けない
(course-set-pasha版と同じ理由:`enqueue_fallback_webhook_event_ids`発生時点で該当イベント
自体は同期処理済みであり、通知配送の失敗は顧客への応答には影響しない)。

## 4. 通知文言

```
[鞍パシャッと運営] Cloud Tasksへのenqueue失敗のお知らせ

以下のWebhookイベントで、Cloud Tasksへのenqueueに失敗したため同期処理へ
自動フォールバックしました(顧客への応答自体は正常に行われています)。

件数: {count}件
webhookEventId: {webhook_event_id_list}

Cloud Tasksのクォータ超過や一時的なネットワーク障害が疑われます。頻発する場合は
Cloud Tasksの設定(クォータ・リトライポリシー)をご確認ください。
```

`webhook_event_id_list`は先頭5件までを列挙し、残りは「...他{N}件」と要約する
(course-set-pasha/aircon-pasha版と同じ方針)。本venture一貫のLinePushClientは
course-set-pashaと同じくプレーンテキストの`send_message(user_id, text)`のみを提供する
ため(aircon-pasha版のようなFlex Message化は行わない)。

## 5. 実装方針・発見した追加ギャップ

- `prototype/enqueue_fallback_owner_notification.py`を新設し、`format_enqueue_fallback_
  owner_notification_message(webhook_event_ids)`・`send_enqueue_fallback_owner_
  notification(webhook_event_ids, push_client, owner_line_user_id=...)`を実装する
  (course-set-pasha版のそのままの横展開、LinePushClient/LinePushDeliveryErrorは
  subscription_cancellation_notification.pyの既存定義を再利用)。
- 本venture固有の追加発見: `receive_webhook()`は`dispatch_webhook_events()`が
  フェーズ続き302で`task_queue_client`引数を受け取るようになった後も、自身の引数一覧に
  `task_queue_client`を持たず、`dispatch_webhook_events()`呼び出し時にも橋渡ししていな
  かった(aircon-pashaフェーズ384で発見された同種のギャップ)。これは実HTTPエントリ
  ポイント経由では`task_queue_client`を指定する手段自体が無く、Cloud Tasksへのenqueue
  機能全体が実質到達不能だったことを意味する。本フェーズで`receive_webhook()`に
  `task_queue_client`(省略時None、後方互換)を追加し橋渡しした上で、`enqueue_fallback_
  owner_push_client`(省略時None、後方互換)も追加し、dispatch結果の`enqueue_fallback_
  webhook_event_ids`が非空の場合に`send_enqueue_fallback_owner_notification()`を呼ぶ
  配線を実装した。

## 6. 残課題

- 実LINE Push Message APIでの送信・実オーナーLINEユーザーIDの設定は、既存の「実LINE API
  接続はオーナー承認待ちの範囲」に含まれる(新規の承認待ち事項としては扱わない)。
- ~~forklift-pasha・event-komiguai-pasha・oshien-pashaについては、enqueue失敗時の挙動
  の個別確認がまだ行われていない~~ → 2026-11-16 12:00 UTC時点のcross-venture-enqueue-
  fallback-applicability-review.mdで確認済み。3venture全てCloud Tasks等の非同期キュー
  構成をそもそも採用していないため、本パターンは「該当なし」と結論済み(フェーズ続き
  305・306の次回候補(2)としてクローズ)。本項目は解消済みのため以後の棚卸し候補からは
  除外する(フェーズ続き310で記載の陳腐化を是正)。
