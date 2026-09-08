# Stripe Webhook署名検証・`checkout.session.completed`受信処理設計

作成日: 2026-09-08(フェーズ51)

checkout-initiation-flow-design.md(フェーズ50)「次にやること」1点目、
subscription-billing-data-model-design.md(フェーズ46)「次にやること」に残っていた、
Stripe Webhook(`checkout.session.completed`)の受信・署名検証・イベントディスパッチに
対応する。

## 1. 方針: 署名検証はcourse-set-pasha/aircon-pashaと同一アルゴリズムを踏襲

course-set-pasha/prototype/stripe_webhook.pyの`verify_stripe_signature()`は、
aircon-pashaフェーズ125のdocstringが明記する通り「venture固有の差異は無い」
(`Stripe-Signature`ヘッダの`t`/`v1`パース、HMAC-SHA256による署名一致確認、
タイムスタンプ許容誤差300秒によるリプレイ対策)。本ventureも同じアルゴリズムを
そのまま踏襲する(`prototype/stripe_webhook.py`の`verify_stripe_signature()`として実装、
既存2venture版と関数シグネチャ・戻り値も同一)。

## 2. `checkout.session.completed`ハンドラの本venture固有部分

course-set-pasha/aircon-pashaの`handle_checkout_session_completed()`はいずれも
「Checkout Session作成時にどうやってuser_id(本ventureではworkshop_id)を
`client_reference_id`へ渡していたか」の設計(user-account-linking-design.md等)に
依存する。本ventureは`checkout-initiation-flow-design.md`(フェーズ50)3節の通り、
`build_checkout_session_params()`が`client_reference_id`に`workshop_id`をそのまま
設定する設計のため、course-set-pashaのような連携コード方式(LIFF IDトークン検証)は
不要で、aircon-pashaの`client_reference_id`直接方式と同じ扱いにできる。

処理内容(`handle_checkout_session_completed(data_object, workshop_store)`):

1. `data_object["client_reference_id"]`を`workshop_id`として取り出す。空・欠落の場合は
   `invalid_events`扱いとし、以降の処理を行わない(不正なイベントで例外を外に
   漏らさない、course-set-pasha/aircon-pashaと同じ方針)。
2. `workshop_store.get_stripe_customer_id(workshop_id)`が`None`の場合のみ、
   `data_object["customer"]`(Stripe顧客ID)を`set_stripe_customer_id()`で書き込む
   (フェーズ50の`build_checkout_session_params()`が`existing_stripe_customer_id`
   指定時は`customer`パラメータを設定し既存顧客を再利用する設計のため、初回契約時のみ
   新規書き込みが発生する想定。再契約時は既存customer_idと一致するため上書きしても
   実害はないが、初回書き込みのみに絞ることで意図を明確にする)。
3. `workshop_store.set_subscription_status(workshop_id, "active")`を呼び、
   `subscription_status`を`"trialing"`から`"active"`へ遷移させる。

`customer.subscription.deleted`・`invoice.payment_failed`等の他イベント種別への対応
(course-set-pasha/aircon-pashaが実装済みの解約通知・決済失敗ダニング等)は、本venture
ではまだ設計しておらず引き続き次の課題として残す(`checkout.session.completed`単体の
受信ができないことには有償契約自体が始まらないため、まず最小のイベント種別のみを
対象とする)。

## 3. `receive_stripe_webhook()`エントリポイント

course-set-pashaの`receive_webhook()`(LINE側、フェーズ82)と同じ位置づけで、
生のHTTPリクエストボディ(bytes)・`Stripe-Signature`ヘッダ・webhook_secretを受け取り、
署名検証→JSONパース→イベント種別ディスパッチを1つの関数にまとめる。

```python
def receive_stripe_webhook(
    body: bytes, sig_header, webhook_secret, *, workshop_store=None,
) -> StripeWebhookReceiverResult:
```

処理順序:

1. `verify_stripe_signature(body, sig_header, webhook_secret)`が`False`なら、
   JSONパース・ハンドラ呼び出しのいずれも行わず`status_code=400`
   (`error="invalid_signature"`)を返す。
2. 署名検証通過後、`body`を`json.loads()`でパースする。失敗時は`status_code=400`
   (`error="invalid_json"`)。
3. `event["type"]`が`"checkout.session.completed"`の場合のみ
   `handle_checkout_session_completed(event["data"]["object"], workshop_store)`を呼ぶ。
   それ以外の`type`は`status_code=200`・`ignored_type=event["type"]`として無視する
   (Stripeへは常に200を返し、未対応イベント種別によるリトライの無限ループを避ける、
   course-set-pasha/aircon-pashaと同じ方針)。

`StripeWebhookReceiverResult`(dataclass): `status_code`・`workshop_id`
(処理成功時のみ)・`ignored_type`(無視時のみ)・`error`(失敗時のみ理由コード)の4フィールド。

## 4. 未検証・残課題

- 実Stripeアカウント接続・実webhook_secretの取得・Cloud Functionsへのデプロイは
  いずれもアカウント作成・外部サービス公開に該当しオーナー承認待ちのため未着手のまま残る
  (pending-approval.md参照)。
- `customer.subscription.deleted`(解約確定)・`invoice.payment_failed`/
  `invoice.payment_succeeded`(決済失敗ダニング)への対応は、course-set-pasha/
  aircon-pashaの既存設計を横展開する形で別途設計する(本フェーズでは
  `checkout.session.completed`のみに範囲を絞った)。
- 本フェーズ完了後、フェーズ48で見送った`is_trial_period_over`のトライアル終了時
  生成一時停止への配線に着手できる状態になる
  (`get_subscription_status(workshop_id) == "active"`を判定条件に含めることで、
  正規契約者を誤って生成停止にする問題を回避できる)。
- イベントID(`event.id`)によるべき等性チェック(course-set-pashaフェーズ151・
  aircon-pashaフェーズ177が実装済み)は、本ventureでは`checkout.session.completed`が
  workshop_idごとに複数回届いても`set_subscription_status`の上書きで実害が無いため
  当面省略した。将来`invoice.payment_failed`等の非べき等な通知処理を追加する際に
  改めて必要性を検討する。
