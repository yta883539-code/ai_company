# Stripe WebhookのHTTPエントリポイント設計

作成日: 2026-08-22(フェーズ95)

README.md「次にやること」フェーズ94の残課題(1)「`verify_stripe_signature()`と
`dispatch_stripe_event()`を結ぶHTTPエントリポイント本体(`receive_webhook()`のStripe版に
相当、JSONパース・署名検証失敗時の早期リターンを含む)」に対応する。フェーズ93・94時点では
署名検証(`verify_stripe_signature()`)とイベント種別ディスパッチ(`dispatch_stripe_event()`)が
それぞれ単体で存在するのみで、両者を実際のHTTPリクエストボディ(bytes)から結ぶ
エントリポイント関数が未実装だった。

## 1. 方針: `receive_stripe_webhook()`

LINE側`cloud_function_webhook.py`の`receive_webhook()`(フェーズ82、
`receive-webhook-http-entry-point-design.md`)と同じ位置づけの関数を、
`prototype/stripe_webhook.py`に追加する。LINE版との違いは次の2点。

- Stripeは1リクエストにイベント1件のみを含む(LINE版の`events`配列のような複数件束ねは
  行わない)。そのためJSONパース後は`dispatch_stripe_event()`に1回だけ委譲すればよい。
- 署名検証のパラメータ名が`channel_secret`ではなく`webhook_secret`になる
  (`verify_stripe_signature()`のシグネチャに合わせる)。

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

処理順序(LINE版`receive_webhook()`と同じ3段階):

1. `verify_stripe_signature(body, signature_header, webhook_secret, now=<エポック秒>)`が
   `False`なら、JSONパース・`dispatch_stripe_event()`のいずれも呼ばずに`status_code=401`を
   返す(不正なリクエストへの余計な処理を避ける)。`verify_stripe_signature()`自体は
   エポック秒(`float`)の`now`を受け取る一方、本関数の`now`は`dispatch_stripe_event()`に
   渡す`datetime`であるため、両者は別引数として扱う(署名検証用の現在時刻は
   `now.timestamp()`から導出する)。
2. 署名検証通過後、`body`を`json.loads()`でパースする。デコード・パースに失敗した場合は
   `status_code=400`(`error="invalid_json"`)を返す。
3. パース結果が`dict`でない場合は`status_code=400`(`error="invalid_event"`)を返す
   (Stripeからの実際のリクエストでは通常発生しないはずだが、LINE版と同じ方針で
   エントリポイントとして不正な入力にも例外を外に漏らさない設計とする)。
4. 上記を通過した`event`(dict)をそのまま`dispatch_stripe_event()`に委譲し、
   `status_code=200`・`dispatch_result`にその戻り値(`StripeDispatchResult`)を格納して
   返す。`resolve_user_id`が解決できなかった場合(`unresolved_customers`)・対象外の
   イベント種別(`ignored_types`)であっても、Stripeへの応答としては200を返す(LINE版が
   個々のイベント処理内エラーをdispatch側で吸収する方針と同じく、Stripe側の再送ループを
   避けるため、リクエスト自体が正しく受理・処理された場合は200とする)。

`StripeWebhookReceiverResult`(dataclass)は`status_code`・`dispatch_result`
(成功時のみ`StripeDispatchResult`)・`error`(失敗時のみ理由コード文字列)の3フィールドとし、
LINE版`WebhookReceiverResult`と同じ形にした。

## 2. プロトタイプ実装方針

- `prototype/stripe_webhook.py`に`StripeWebhookReceiverResult`・`receive_stripe_webhook()`を
  追加する。既存の`verify_stripe_signature()`・`dispatch_stripe_event()`はいずれも変更せず、
  両者を結ぶ薄いラッパーとして追加する。
- テストは`prototype/test_stripe_webhook.py`に`ReceiveStripeWebhookTest`として追加し、
  LINE版`ReceiveWebhookTest`と対称になる形で最低限次のケースをカバーする。
  1. 署名不正時は401かつ`dispatch_stripe_event()`自体が呼ばれない
     (`store`への書き込みが発生しないことを確認)。
  2. JSONとしてパースできないbodyは400・`error="invalid_json"`。
  3. パース結果がdictでない(例: JSON配列トップレベル)bodyは400・`error="invalid_event"`。
  4. 正常な`customer.subscription.deleted`イベントは200・`dispatch_result.marked_user_ids`に
     反映される。
  5. `resolve_user_id`が解決できないイベント(`unresolved_customers`)でも200を返す
     (Stripeへの応答としては受理扱いとする方針の確認)。

## 残課題

- `main(request)`相当(実Cloud Functionsの`functions_framework`リクエストオブジェクトからの
  `body`・`Stripe-Signature`ヘッダ取り出し配線)は、LINE版フェーズ83の`main(request)`と
  同様の薄い配線となる見込みだが、`webhook_secret`の環境変数名(`STRIPE_WEBHOOK_SECRET`
  想定)の最終確認と合わせて次の課題として残す。
- `resolve_user_id`(`stripe_customer_id → user_id`)の実装自体
  (`stripe-webhook-event-dispatch-design.md`で名指しされていた未解決事項)は本設計の
  範囲外のまま引き続き残る。申込フォーム提出フローのどこで`stripe_customer_id`を
  `user_profile`に書き込むかの設計と合わせて検討が必要。
- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)は実Stripeアカウント接続
  (オーナー承認待ち)後の課題として残る。
