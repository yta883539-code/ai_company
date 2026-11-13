# enqueueフォールバック発生時のオーナー通知 設計

enqueue-failure-partial-processing-safety-design.md(フェーズ373)で実装した
`dispatch_webhook_events()`の`result.enqueue_fallback_webhook_event_ids`(Cloud Tasksへの
`create_task()`が`TaskAlreadyExistsError`以外の例外で失敗し、同期処理へフォールバックした
`webhookEventId`の一覧)について、フェーズ373「次回候補(1)」に対応し、実運用で非ゼロになった
際にオーナーへ知らせる仕組みを設計する。

blocked-but-billing-owner-notification-design.md(フェーズ143)・
payment-suspension-owner-notification-design.md(フェーズ125)が確立した「顧客ごとの
user_idではなく固定のオーナー1件へLINE Push」というチャネル設計をそのまま踏襲する。新たな
通知チャネルの検討は行わない。

## 1. 送信先

既存2設計と同一。`OWNER_LINE_USER_ID_PLACEHOLDER`(実際のオーナーLINEユーザーIDの取得・
設定は既存の「実LINE API接続はオーナー承認待ちの範囲」に含まれるため、新たな承認待ち事項
としては扱わない)。

## 2. 既存2設計との違い:発火タイミング・冪等性の考え方

blocked-but-billing・payment-suspensionの両通知は「顧客の状態(契約・フォロー状態)」を
対象にしており、状態は時間が経っても変わらず残り続けるため、(a)日次バッチで洗い出し、
(b)顧客ごとに一度だけ通知する永続フラグ(`*_owner_notified_at`)で冪等性を担保する、という
設計だった。

一方、`enqueue_fallback_webhook_event_ids`は「1回の`dispatch_webhook_events()`呼び出し内で
Cloud Tasksへのenqueueが一時的に失敗した」という運用上のインシデント信号であり、顧客の
状態ではない。各`webhookEventId`は`_mark_processed()`による既存の重複排除(LINE Platform
からの再送に対する冪等性、line-webhook-event-id-idempotency-design.md)により、同一
webhookEventIdに対してdispatch_webhook_events()が二度呼ばれることは想定しない。したがって:

- 永続的な「通知済みフラグ」をuser_profileやその他のドキュメントに追加する必要はない
  (対象が顧客ではなくイベントIDであり、かつイベントIDは再出現しない前提のため)。
- 日次バッチで洗い出す設計ではなく、`dispatch_webhook_events()`呼び出し直後(=HTTPリクエスト
  処理の中)に、その場で`enqueue_fallback_webhook_event_ids`が非空であれば即座に1回だけ
  digest通知を送る設計とする。運用上のインシデントはできるだけ早くオーナーに届けるべきであり、
  日次バッチまで待つ必要はない。
- 1リクエスト(1回のWebhookバッチ)内で複数の`webhookEventId`がフォールバックした場合も、
  リクエストごとに1通のdigestとしてまとめて送る(1イベント=1通ではない。Cloud Tasksの
  クォータ超過等、同時に多数のイベントがフォールバックしうる障害モードのため、個別送信では
  オーナーのLINEがスパム状態になりかねない)。

## 3. 送信失敗時の扱い

既存2設計は「送信成功時のみ`*_owner_notified_at`を書き込み、失敗時は次回バッチで自然に
再試行される」という設計だったが、本通知は永続フラグを持たないため同じ再試行方式は使えない。
`enqueue_fallback_webhook_event_ids`自体が発生した時点でイベントは同期処理(フォールバック)
済みであり、通知の送信に失敗しても顧客への応答には影響しない(あくまで運用者向けアラートの
配送失敗)。そのため本設計では、通知送信の失敗は`LinePushDeliveryError`を握りつぶして
ログ相当の戻り値(`sent: bool`)に反映するのみとし、再送・リトライの仕組みは設けない
(日次のCloud Tasksダッシュボード・Cloud Loggingでの事後確認を代替手段とする想定。実際の
ログ基盤連携は実GCPデプロイ後の課題として残る)。

## 4. 通知文言

```
[コースセットパシャッと運営] Cloud Tasksへのenqueue失敗のお知らせ

以下のWebhookイベントで、Cloud Tasksへのenqueueに失敗したため同期処理へ
自動フォールバックしました(顧客への応答自体は正常に行われています)。

件数: {count}件
webhookEventId: {webhook_event_id_list}

Cloud Tasksのクォータ超過や一時的なネットワーク障害が疑われます。頻発する場合は
Cloud Tasksの設定(クォータ・リトライポリシー)をご確認ください。
```

`webhook_event_id_list`は件数が多い場合に1通が長大になるのを避けるため、先頭5件までを
列挙し、残りは「...他{N}件」と要約する(既存の他ventureの一覧通知で件数要約を行っている
箇所と同じ方針)。

## 5. 実装方針

- `enqueue_fallback_owner_notification.py`を新設し、`format_enqueue_fallback_owner_
  notification_message(webhook_event_ids)`・`send_enqueue_fallback_owner_notification(
  webhook_event_ids, push_client, owner_line_user_id=...)`を実装する。永続ストアへの
  依存を持たないため、blocked_but_billing_owner_notification.pyのような
  `*NotifiedAtReader/Writer`Protocolは不要。
- `receive_webhook()`に新規オプション引数`enqueue_fallback_owner_push_client: Optional[
  LinePushClient] = None`を追加し、`dispatch_webhook_events()`呼び出し後に
  `dispatch_result.enqueue_fallback_webhook_event_ids`が非空かつ本引数が指定されていれば
  `send_enqueue_fallback_owner_notification()`を呼ぶ。未指定(`None`)時は何もしない
  (既存の全オプション引数と同じ後方互換パターン)。

## 6. 残課題

- 実LINE Push Message APIでの送信・実オーナーLINEユーザーIDの設定は、既存の「実LINE API
  接続はオーナー承認待ちの範囲」に含まれる(新規の承認待ち事項としては扱わない)。
- フェーズ373「次回候補(2)」(本パターンのaircon-pasha等への横展開確認)は未着手のまま残す。
