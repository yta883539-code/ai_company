# 解約確定(customer.subscription.deleted)時の契約者向け案内メッセージ配線設計

作成日: 2026-09-09(フェーズ54)

## 1. 発見された経緯(残課題棚卸し)

subscription-cancellation-flow-design.md(フェーズ23)2節に、解約確定Webhook受信時に
送るべき案内メッセージの文言が以下のとおり草案として記載されていた。

```
【鞍パシャッと】解約手続きが完了しました

ご契約は◯月◯日をもって終了となります。それまでは引き続きご利用いただけます。
またのご利用をお待ちしております。
```

しかし実際の`prototype/stripe_webhook.py`の`handle_customer_subscription_deleted()`
(フェーズ53)を確認したところ、`workshop_store.set_subscription_status(workshop_id,
"canceled")`を呼ぶのみで、上記メッセージを実際にLINEで契約者へ送信する配線が一切
存在しないことが判明した。加えて、この草案文言自体にも
course-set-pasha/subscription-cancelled-notification-design.md(フェーズ155)が
発見したのと同種の矛盾が含まれている。

`customer.subscription.deleted`は「請求期間が終了し契約が完全に終わった後」に届く
イベントであり、この時点では既に生成が利用不可になっている
(trial-end-condition-design.md・フェーズ52で`subscription_status != "active"`の
workshopは`TrialPeriodOverError`相当のブロック対象になる設計と整合させる必要がある)。
にもかかわらず草案文言は「それまでは引き続きご利用いただけます」と記載しており、
実際の意味と矛盾する。本venture固有の解約フローは、course-set-pashaやline-reservation-ai
のような「`customer.subscription.updated`のcancel_at_period_end変化を検知して解約予約
受理案内を送る」設計をまだ持たない(subscription-cancellation-flow-design.md「1. 解約
意図検知時の案内メッセージ」がその代わりを果たしている、LINEトーク内の意図検知方式)ため、
本フェーズは`customer.subscription.deleted`受信時の完了案内**のみ**を対象とする
(`customer.subscription.updated`のcancel_at_period_end前後比較への対応は本venture未着手
であり、次の課題とする)。

## 2. 文言の見直し

course-set-pasha/aircon-pashaが確定した「契約終了のご案内」パターンを踏襲し、本venture
固有の業務内容(受注内容整理メモ・納品案内・お手入れ案内の3点セット)に翻案する。

```
【鞍パシャッと】ご契約終了のご案内

ご契約が終了しました。ご利用ありがとうございました。
本日以降、受注内容整理メモ・納品案内・お手入れ案内の生成はご利用いただけません。

またのご利用をお待ちしております。再開をご希望の際は、いつでも新規契約と
同じお手続きでお申し込みいただけます。
```

「それまでは引き続きご利用いただけます」の一文は削除し、course-set-pashaフェーズ155と
同じ理由(このイベントは契約終了後に届くため、猶予がある旨の案内は誤り)で除外した。
subscription-cancellation-flow-design.md 2節の草案もこの修正内容へ更新する(3節参照)。

## 3. 実装方針

- 新規モジュール`prototype/subscription_cancellation_notification.py`を作成する。
  course-set-pasha/prototype/subscription_cancellation_notification.pyと同じ
  「文言定数+`LinePushClient`Protocol+`LinePushDeliveryError`+`handle_*()`実送信配線」の
  構成を踏襲する。本ventureも決済・契約系のシステム通知はプレーンテキスト1本のみとし
  (トーン分岐は行わない、message-context-selection-design.md「4. 未検証・残課題」が
  扱う優先順位付けの対象は生成リクエスト系の一時状態のみで、契約終了通知はそれとは独立に
  即時送信するため対象外)、aircon-pashaのFlex Message形式は採用しない(本venture固有の
  既存通知〈解約意図検知時の案内メッセージ〉自体がすべてプレーンテキストで統一されている
  ため)。
- 本ventureは他venture(1事業者=1LINEアカウント=1契約者)と異なり、契約は
  `craftsman_workshop/{workshop_id}`単位・支払い名義人は`contractor_user_id`一人に
  限定される(craftsman-account-linking-design.md、subscription-billing-data-model-
  design.md)。そのため`handle_subscription_cancelled(user_id, push_client)`
  (course-set-pasha方式、引数はLINE user_id 1つ)をそのまま踏襲せず、
  `handle_subscription_cancelled(workshop_id, workshop_store, push_client) ->
  SubscriptionCancelledNotificationResult`とし、関数内部で
  `workshop_store.get_contractor_user_id(workshop_id)`により送信先user_idを解決する
  設計とする(共同利用者〈契約者以外のメンバー〉には送らない。解約操作の権限自体が
  契約者本人に限定されている設計〈subscription-cancellation-flow-design.md「複数職人
  プラン固有の論点」〉と整合させるため)。
- `push_client.send_message(user_id, SUBSCRIPTION_CANCELLED_MESSAGE)`が
  `LinePushDeliveryError`を送出した場合は`notified=False`を返す(例外は関数内で捕捉し
  呼び出し元に伝播させない、course-set-pashaと同じ方針)。

## 4. `handle_customer_subscription_deleted()`側の配線

`prototype/stripe_webhook.py`の`handle_customer_subscription_deleted()`に新規引数
`push_client: Optional[LinePushClient] = None`(省略時`None`、既存呼び出し元への
後方互換)を追加する。

**状態変更(`set_subscription_status(workshop_id, "canceled")`)は通知の送信成否と
独立して常に行う**(course-set-pashaフェーズ155と同じ設計判断)。理由:
`subscription_status`はtrial-end-condition-design.md・フェーズ52の生成ブロック判定が
直接参照する実体のある状態であり、LINE通知の配信可否とは無関係の情報である。仮に送信
失敗時に状態更新を止めてWebhookリトライに委ねる設計にすると、LINE Push配信が継続的に
失敗する状況下で契約終了後も誤って生成が許可され続けるリスクが生じ、通知の欠落より
実害が大きい。

`CustomerSubscriptionDeletedResult`に`notified: bool = False`フィールドを追加する
(`invalid`・`unresolved`時は常に`False`のまま、状態更新に成功し`push_client`が指定
された場合のみ送信を試行する)。

`receive_stripe_webhook()`にも新規引数`push_client: Optional[LinePushClient] = None`を
追加し、`handle_customer_subscription_deleted()`へそのまま委譲する(`checkout.session.
completed`分岐には影響しない)。

## 5. 残課題

- (解消済み 2026-09-09・フェーズ55: `customer.subscription.updated`の
  `cancel_at_period_end`前後比較による「解約予約受理・解約取り消し」案内は
  subscription-cancellation-scheduled-notification-design.mdとして設計・実装済み
  〈`handle_customer_subscription_updated()`・`receive_stripe_webhook()`への
  ディスパッチ配線を含む〉。本項目は作成時(フェーズ54)時点で未着手だったが、
  直後のフェーズ55で解消されたにもかかわらず本ファイル側の訂正が漏れていたもの。
  2026-09-11 07:00 UTC・フェーズ82で訂正。)
- `receive_stripe_webhook()`実HTTPエントリポイントでの`push_client`配線・実LINE Push
  Message API接続はオーナー承認待ち(pending-approval.md参照)。
- `invoice.payment_failed`/`invoice.payment_succeeded`(決済失敗ダニング)への対応は
  引き続き対象外(README「次にやること」参照)。
