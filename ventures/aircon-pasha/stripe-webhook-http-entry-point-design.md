# Stripe WebhookのHTTPエントリポイント設計

作成日: 2026-08-27(フェーズ127)

README.md「次にやること」フェーズ126の残課題(1)「`verify_stripe_signature()`と
`dispatch_stripe_event()`を結ぶHTTPエントリポイント本体(`receive_webhook()`のStripe版に
相当、JSONパース・署名検証失敗時の早期リターンを含む)」に対応する。フェーズ125・126時点では
署名検証(`verify_stripe_signature()`、`prototype/stripe_webhook.py`)とイベント種別
ディスパッチ(`dispatch_stripe_event()`、`prototype/stripe_dispatch.py`)がそれぞれ単体で
存在するのみで、両者を実際のHTTPリクエストボディ(bytes)から結ぶエントリポイント関数が
未実装だった。

course-set-pashaの`stripe-webhook-http-entry-point-design.md`(フェーズ95)と同じ位置づけの
設計だが、本ventureはCheckout Session作成時のuser_id紐付け方式(user-account-linking-design.md、
申込フォーム送信完了時の連携コード方式)がcourse-set-pashaの`client_reference_id`方式とは異なり、
かつ`checkout.session.completed`イベントの受信配線自体が本venture未着手のままのため、本設計は
course-set-pashaがフェーズ95時点で持っていた「`customer.subscription.*`系イベントのみを
`dispatch_stripe_event()`に委譲する」範囲に限定する。`checkout.session.completed`の受信配線は
別途今後の課題として残す(下記「残課題」参照)。

## 1. 方針: `receive_stripe_webhook()`

`prototype/stripe_webhook.py`(署名検証を実装済みの既存ファイル)に追加する。

```python
def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
```

処理順序(course-set-pashaフェーズ95版と同じ3段階):

1. `verify_stripe_signature(body, signature_header, webhook_secret, now=<エポック秒>)`が
   `False`なら、JSONパース・`dispatch_stripe_event()`のいずれも呼ばずに`status_code=401`を
   返す(不正なリクエストへの余計な処理を避ける)。`verify_stripe_signature()`自体は
   エポック秒(`float`)の`now`を受け取る一方、本関数の`now`は`dispatch_stripe_event()`に
   渡す`datetime`であるため、両者は別引数として扱う(署名検証用の現在時刻は
   `now.timestamp()`から導出する)。
2. 署名検証通過後、`body`を`json.loads()`でパースする。デコード・パースに失敗した場合は
   `status_code=400`(`error="invalid_json"`)を返す。
3. パース結果が`dict`でない場合は`status_code=400`(`error="invalid_event"`)を返す
   (Stripeからの実際のリクエストでは通常発生しないはずだが、LINE版
   `cloud_function_webhook.receive_webhook()`と同じ方針で、エントリポイントとして
   不正な入力にも例外を外に漏らさない設計とする)。
4. 上記を通過した`event`(dict)をそのまま`dispatch_stripe_event()`に委譲し、
   `status_code=200`・`dispatch_result`にその戻り値(`StripeDispatchResult`)を格納して
   返す。`resolve_user_id`が解決できなかった場合(`unresolved_customers`)・対象外の
   イベント種別(`ignored_types`)であっても、Stripeへの応答としては200を返す(LINE版が
   個々のイベント処理内エラーをdispatch側で吸収する方針と同じく、Stripe側の再送ループを
   避けるため、リクエスト自体が正しく受理・処理された場合は200とする)。

`StripeWebhookReceiverResult`(dataclass)は`status_code`・`dispatch_result`
(成功時のみ`StripeDispatchResult`)・`error`(失敗時のみ理由コード文字列)の3フィールドとし、
course-set-pasha版と同じ形にした。

## 2. プロトタイプ実装方針

- `prototype/stripe_webhook.py`に`StripeWebhookReceiverResult`・`receive_stripe_webhook()`を
  追加する。`stripe_dispatch.py`の`dispatch_stripe_event()`・`StripeDispatchResult`を
  importして使うのみで、既存の`verify_stripe_signature()`・`dispatch_stripe_event()`は
  いずれも変更せず、両者を結ぶ薄いラッパーとして追加する。
- テストは`prototype/test_stripe_webhook.py`に`ReceiveStripeWebhookTest`として追加し、
  course-set-pasha版と対称になる形で最低限次のケースをカバーする。
  1. 署名不正時は401かつ`dispatch_stripe_event()`自体が呼ばれない
     (`store`への書き込みが発生しないことを確認)。
  2. JSONとしてパースできないbodyは400・`error="invalid_json"`。
  3. パース結果がdictでない(例: JSON配列トップレベル)bodyは400・`error="invalid_event"`。
  4. 正常な`customer.subscription.deleted`イベントは200・`dispatch_result.marked_user_ids`に
     反映される。
  5. `resolve_user_id`が解決できないイベント(`unresolved_customers`)でも200を返す
     (Stripeへの応答としては受理扱いとする方針の確認)。

## 残課題

- `checkout.session.completed`の受信配線(user-account-linking-design.mdの連携コード方式との
  接続)は本設計の範囲外のまま残る。course-set-pashaはこの部分を後のフェーズで
  `handle_checkout_session_completed()`として`receive_stripe_webhook()`に追加したが、
  本ventureは連携コード方式が申込フォーム送信時点(Checkout Session作成前)で完結する設計
  (user-account-linking-design.md 3節)のため、Checkout Session完了イベント自体をトリガーに
  何かを書き込む必要があるかどうかは別途整理が必要。
- ~~`main(request)`相当(実Cloud Functionsの`functions_framework`リクエストオブジェクトからの
  `body`・`Stripe-Signature`ヘッダ取り出し配線)は、course-set-pashaの`main(request)`(Stripe版)
  と同様の薄い配線となる見込みだが、`webhook_secret`の環境変数名(`STRIPE_WEBHOOK_SECRET`
  想定)の最終確認と合わせて次の課題として残す。~~ → フェーズ150で解消。`stripe_webhook.py`に
  course-set-pasha版と対称の`main(request)`・`get_stripe_runtime_dependencies()`を実装した。
  `get_stripe_runtime_dependencies()`は`InMemoryUserProfileStore()`を1つ生成し
  `user_profile_store`・`payment_store`の両方として渡す(duck typingで
  `PaymentFailureStoreProtocol`を満たすため)。`push_client`・`recovery_push_client`は
  実LINE Push API接続がオーナー承認待ちのため意図的に渡さない(省略時`None`)。
  環境変数名は予定どおり`STRIPE_WEBHOOK_SECRET`とした。テスト13件追加、詳細は
  README.mdフェーズ150参照。
- ~~`resolve_user_id`(`stripe_customer_id → user_id`)の実装自体
  (`stripe-webhook-event-dispatch-design.md`で名指しされていた未解決事項)は本設計の
  範囲外のまま引き続き残る。~~ → フェーズ140以降(`stripe_webhook.py`の
  `make_resolve_user_id()`、checkout-session-completed-handling-design.md)で対応済み。
  `user_profile_store.get_user_id_by_stripe_customer_id`を`resolve_user_id`にそのまま
  渡す薄いファクトリとして実装されている(本文書作成当初は未着手だったが、後続フェーズで
  解消され本節の更新が漏れていたため、フェーズ149でまとめて反映)。
- **(2026-08-29追記・フェーズ149で解消)** `receive_stripe_webhook()`が`dispatch_stripe_
  event()`の`payment_store`/`push_client`/`recovery_push_client`引数(フェーズ140・147・148で
  追加済み)を委譲しておらず、HTTPエントリポイント経由では`invoice.payment_failed`/
  `invoice.payment_succeeded`が常に`ignored_types`扱いになってしまう配線漏れがあった。
  3引数を`receive_stripe_webhook()`にも追加してそのまま`dispatch_stripe_event()`へ渡す
  薄い配線を追加し解消した。詳細はREADME.mdフェーズ149参照。
- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)は実Stripeアカウント接続
  (オーナー承認待ち)後の課題として残る。
