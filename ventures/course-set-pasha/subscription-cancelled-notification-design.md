# 解約確定(customer.subscription.deleted)時の顧客向け案内メッセージ配線設計(フェーズ155)

## 0. 発見された経緯(残課題棚卸し)

subscription-cancellation-flow-design.md(フェーズ55)2節に、解約確定Webhook受信時に
送るべき案内メッセージの文言が以下のとおり草案として記載されていた。

```
【コースセットパシャッと】解約手続きが完了しました

ご契約は◯月◯日をもって終了となります。それまでは引き続きご利用いただけます。
またのご利用をお待ちしております。
```

しかし実際の`prototype/stripe_webhook.py` `dispatch_stripe_event()`の
`customer.subscription.deleted`分岐を確認したところ、
`mark_deletion_candidate_on_subscription_deleted()`(削除候補フラグの内部書き込み)と
`user_profile_store.clear_blocked_but_billing_owner_notified_at()`(フェーズ144)を
呼ぶのみで、上記メッセージを実際にLINEで顧客へ送信する配線が一切存在しないことが
判明した。つまり顧客は解約が確定しても、その旨のLINE通知を一度も受け取れない状態が
フェーズ55(2026-08-15)から本フェーズまで約3週間放置されていたことになる
(`payment_recovery_notification.py`が同種の決済系通知をすべて実送信配線まで
済ませているのとは対照的)。本フェーズはこのギャップに対応する。

## 1. 文言の見直し(日付プレースホルダの扱い)

上記の草案文言は「それまでは引き続きご利用いただけます」という一文を含むが、これは
`customer.subscription.deleted`イベントの実際の意味(=請求期間が終了し契約が
完全に終わった後に届くイベント)と矛盾する。Stripeの標準的な解約フロー
(Customer Portalでの解約操作)は次の2段階のイベントに分かれる。

1. 解約操作の受理時点: `customer.subscription.updated`
   (`cancel_at_period_end`が`false→true`に変化) — この時点では契約はまだ継続中。
   「◯月◯日まで引き続き利用可能」という案内が意味を持つのはここ。
2. 実際の契約終了時点: `customer.subscription.deleted` — この時点では既に
   利用不可となっている。

line-reservation-aiはフェーズ続き177・185
(`blocked-but-billing-detection-design.md`・`customer-subscription-updated-event-
routing-design.md`)でこの2段階を`cancel_at_period_end`の前後比較により正しく
区別し、`prototype/cloud_function_subscription_cancelled_webhook.py`に
`render_cancellation_scheduled_message()`(1のタイミング、終了日を含む)・
`render_cancellation_rescheduled_message()`(解約取り消し時)・
`render_cancellation_completed_message()`(2のタイミング、終了日を含まないシンプルな
完了案内)の3種類を実装済みである。

本フェーズはこのうち**2(実際の契約終了時点)のみ**を本ventureへ横展開する
(`customer.subscription.deleted`は既存のハンドリング対象イベントであり、追加の
設計投資なく対応できるため)。1(解約予約受理時点、`cancel_at_period_end`の
前後比較を要する新規ロジック)は本フェーズの範囲外とし、次回以降の課題として残す
(4節参照)。

## 2. 実装方針

`line-reservation-ai`の`render_cancellation_completed_message()`(日付プレースホルダ
なし、単純な完了案内+再契約導線)と同じ構成を、本venture向けに翻案する。

- 新規モジュール`prototype/subscription_cancellation_notification.py`を作成する。
  `payment_recovery_notification.py`と同じ「文言定数+`render_*()`+
  `handle_*()`実送信配線」の3点セット構成を踏襲する。
- 本ventureは決済系通知(`PAYMENT_RECOVERED_MESSAGE`等)と同様、トーン分岐
  (formal/standard/casual)は行わない単一のプレーンテキストとする
  (message-tone-variants.mdのトーン分岐はSNS投稿文生成のみが対象で、決済・契約系の
  システム通知はこれまで一貫してプレーンテキスト、`payment_recovery_notification.py`
  参照)。
- `SUBSCRIPTION_CANCELLED_MESSAGE`は「契約終了」「本日以降、投稿文の生成は
  ご利用いただけない」「再開時は新規契約と同じ手続き」の3点を含む
  (line-reservation-ai版の「新規予約受付を停止」を、本venture固有の
  「投稿文の生成が利用不可になる」に翻案)。
- `handle_subscription_cancelled(user_id, push_client) -> SubscriptionCancelledNotificationResult`
  を新設する。`push_client.send_message()`が`LinePushDeliveryError`を送出した場合は
  `notified=False`を返す。

## 3. `dispatch_stripe_event()`側の配線

`customer.subscription.deleted`分岐の末尾、`mark_deletion_candidate_on_subscription_
deleted()`呼び出しの後に`push_client`指定時のみ通知を送信する
(既存の他イベント同様、未指定時は従来通り通知なしで後方互換を保つ)。

**状態変更(`mark_deletion_candidate_on_subscription_deleted()`・
`clear_blocked_but_billing_owner_notified_at()`)は通知の送信成否と独立して常に行う**
(`payment_recovery_notification.py`の「送信失敗時は状態変更をスキップしWebhook
リトライに委ねる」という既存方針とは意図的に異なる)。理由:

- `deletion_candidate_at`・`blocked_but_billing_owner_notified_at`はいずれも
  「実際に解約が確定したという事実」を反映するための内部フラグであり、
  LINE通知が届いたかどうかとは無関係の情報である。
- 仮に送信失敗時に状態変更を止めてWebhookリトライに委ねる設計にすると、
  LINE Push配信が継続的に失敗する状況下で削除候補化(data-retention-policy.md)や
  ブロック中課金検知除外(blocked-but-billing-owner-notification-design.md)が
  いつまでも行われず、他の仕組みに悪影響を及ぼすリスクがある(通知の欠落より
  実害が大きい)。
- `payment_recovery_notification.py`側で状態変更をブロックしているのは、その状態
  自体が「通知を送ったかどうか」を表すフラグ(`payment_failure_reminder_sent_at`等)
  だからであり、本ケースとは前提が異なる。

`StripeDispatchResult`に`cancellation_notified_user_ids`
(送信成功)・`cancellation_notification_failed_user_ids`(送信失敗、状態変更自体は
実行済み)を新設する。

## 4. 次回以降の課題

- 1節で述べた「解約予約受理時点(`cancel_at_period_end`の`false→true`変化)」の
  即時案内メッセージ配線は、line-reservation-aiフェーズ続き185
  (`customer-subscription-updated-event-routing-design.md`)と同じ
  `previous_attributes`からの前後比較ロジックの新規実装を要するため、次回以降の
  課題として残す。実装時は本ventureの`customer.subscription.updated`分岐に
  既に存在するプラン変更検知ロジック(フェーズ153・154)と同じ分岐内で
  `cancel_at_period_end`の変化も検知する構成になる見込み。
- 実LINE Push Message API接続・実Stripe接続はいずれも実アカウント作成
  (オーナー承認待ち)後の課題として引き続き残る。
