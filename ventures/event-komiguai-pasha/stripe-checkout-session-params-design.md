# Stripe Checkout Session実パラメータ構成設計

## 背景

README.mdフェーズ104の次回候補(2)「`StripeCheckoutSessionClientProtocol`の実Stripe SDK
実装(`stripe.checkout.Session.create(**params)`相当)の検討」に対応する。

本venture(event-komiguai-pasha)はaircon-pasha・course-set-pasha・kura-pashaと異なり、
サブスクリプション(`mode="subscription"`)ではなく単発決済(`mode="payment"`、
one-time-checkout-no-account-design.md 2節)を採用している点が構成上の最大の違いである。

## aircon-pasha等との構成差

aircon-pasha/prototype/checkout_session.py の`build_checkout_session_params()`は、
事前にStripeダッシュボードで作成済みのPrice ID
(`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`、プラン名→Price IDの辞書)を`line_items`の
`price`に指定する方式を取っている。これはプラン数が固定(スモール/ミドル等)かつ
料金が月額課金で変動しないサブスクリプションに適した方式。

本ventureは単発利用プラン(500円/回、pricing-plan.mdフェーズ4)のみで金額は
`DEFAULT_AMOUNT_JPY`(=500)の単一値だが、サブスクリプションのPrice IDのような
「事前にダッシュボードで作成しておく固定オブジェクト」を使うか、Checkout Session
作成時に`price_data`で金額・商品名をインラインに指定するかは別途決める必要がある。

## 決定: `price_data`インライン指定方式を採用

理由:
1. 単発決済(`mode="payment"`)のみで将来的な価格変更(pricing-plan.mdの仮決め金額が
   実データに基づき調整される可能性、フェーズ4「従来単価・単発利用単価の原価比較は
   未検証の仮説として残した」)に備え、Stripeダッシュボード側のPrice ID管理を増やさず
   コード側の定数(`DEFAULT_AMOUNT_JPY`)変更のみで追従できる方式が、低頻度利用
   venture(tech-stack.mdフェーズ7「常時稼働コンポーネントを増やさない」方針)に
   合致する。
2. サブスクリプションのような複数プラン選択(aircon-pasha等)がなく単一金額のため、
   Price IDを事前作成して管理する利点(プラン一覧のダッシュボード管理)が本venture
   には当てはまらない。

## `build_stripe_checkout_session_params()`の構成

`checkout_session_creation.py`に、実Stripe SDK呼び出し時に`stripe.checkout.Session.
create(**params)`へそのまま渡すparamsを組み立てる純粋関数を新設する。

```python
def build_stripe_checkout_session_params(
    *, amount, currency, client_reference_id, success_url, cancel_url,
) -> dict:
    return {
        "mode": "payment",
        "client_reference_id": client_reference_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount,
                    "product_data": {
                        "name": STRIPE_PRODUCT_NAME_JA,
                    },
                },
                "quantity": 1,
            }
        ],
    }
```

- `product_data.name`は固定文字列(`"イベントこみぐあいパシャっと 一次チェック(1回)"`)
  とし、Stripeの決済ページ・レシートに表示される商品名とする。
- `customer_email`はcheckout-session-success-cancel-url-design.md(フェーズ104)の
  方針どおり、ここでは渡さずStripe Checkoutページ標準の入力欄に委ねる(既存の
  `StripeCheckoutSessionClientProtocol.create_session()`docstring記載どおり変更なし)。
- `StripeCheckoutSessionClientProtocol.create_session()`自体のシグネチャ(amount・
  currency・client_reference_id・success_url・cancel_url)は変更しない。実Stripe接続後の
  実クライアント実装(`StripeSdkCheckoutSessionClient`相当、本design未実装・次回課題)が
  この関数を内部で呼び出して`stripe.checkout.Session.create(**params)`に渡す、という
  位置づけ。

## 残課題(次回以降)

- 実Stripeアカウント接続自体はオーナー承認待ちの範囲(pending-approval.md参照)のため、
  `build_stripe_checkout_session_params()`の返り値を実際に`stripe.checkout.Session.
  create()`へ渡す`StripeSdkCheckoutSessionClient`の実装(`import stripe`を伴う)は
  見送る。他venture(aircon-pasha・course-set-pasha・kura-pasha)も同様に実SDK呼び出し
  コードを持たず、Protocol定義とInMemory/スタブ実装のみに留めている現状と揃える。
- `product_data.name`の文言は仮決めであり、実際のStripe決済ページ・レシート表示で
  利用者にとって分かりやすい文言かはヒアリング実施(オーナー承認後)まで未検証。
