# Stripe Webhookのイベント種別ルーティング設計

作成日: 2026-08-31(フェーズ続き159)

stripe-webhook-signature-verification-design.md(フェーズ続き158)「残課題」で残っていた
「実際のWebhookエンドポイント本体(署名検証〜イベント種別ディスパッチ〜
`handle_checkout_session_completed()`等の呼び出しを結ぶ層。`cloud_function_payment_
webhook.py`・`cloud_function_subscription_activated_webhook.py`との責務分担も要整理)」に
対応する。course-set-pasha/aircon-pashaの`stripe-webhook-event-dispatch-design.md`
(フェーズ94)と同じ位置づけだが、本ventureは既に2つの独立したWebhookハンドラモジュール
(`cloud_function_payment_webhook.py`・`cloud_function_subscription_activated_webhook.py`)が
「実際のStripeイベント種別」を明示せず抽象的な概念名(`payment_succeeded`・
`subscription_activated`)のまま実装されていたため、まず実イベント種別との対応を確定する。

## 1. 実イベント種別との対応関係の確定

| 本venture内の呼称 | 実装モジュール | 実際に対応すべきStripeイベント種別 | 理由 |
| --- | --- | --- | --- |
| `subscription_activated` | `cloud_function_subscription_activated_webhook.py` | `checkout.session.completed` | トライアル終了後に休止モード(`suspension_reason == "trial_unselected"`)だった店舗が初めてプランを選択・決済を完了する操作は、checkout-initiation-flow-design.mdの決済導線(`build_checkout_session_params()`)が発行するCheckout Sessionの完了イベントそのもの。Stripeに`subscription_activated`という種別は存在しないため、これが実体。 |
| `payment_succeeded` | `cloud_function_payment_webhook.py` | `invoice.payment_succeeded` | 既存契約の月次請求・dunning中の決済成功はCheckout Sessionを経由しないため、Invoiceオブジェクトの決済成功イベントが実体。 |
| (未実装) | (無し、本フェーズで新設) | `invoice.payment_failed` | `cloud_function_send_dunning_notifications.py`が読む`payment_failure_detected_at`を実際に**書き込む**処理が本venture内のどのモジュールにも存在しなかった(既存の`_demo()`はこのフィールドを手動で埋めた`StoreDunningState`を使うのみ)。dunningスケジュール全体の起点となる検知処理そのものが欠落していたことが、本フェーズの棚卸しで判明した(3節で対応)。

## 2. `checkout.session.completed`のstore_id解決は`client_reference_id`で完結する

course-set-pasha/aircon-pashaは`customer`(Stripeカスタマー ID)から`user_id`への変換を
別ストアで解決する必要があった(`resolve_user_id`コールバック)。本ventureは
checkout-initiation-flow-design.md 3節で`build_checkout_session_params()`が
`client_reference_id`に店舗の`user_id`(LINE user_id)をそのまま設定する設計を既に
採用しているため、`checkout.session.completed`受信時は`event.data.object.
client_reference_id`を読むだけでstore_idが直接得られ、別ストアへの問い合わせが不要という
点が本venture固有の単純化点。

一方、`invoice.payment_succeeded`・`invoice.payment_failed`はInvoiceオブジェクトが持つのは
`customer`(Stripeカスタマー ID)のみで`client_reference_id`は含まれないため、
course-set-pasha同様に`customer → store_id`変換を外部から注入する
(`resolve_store_id_by_customer: Callable[[str], Optional[str]]`)。この変換テーブル自体
(`stripe_customer_id`フィールドを店舗プロフィールへ書き込む実装)は、`checkout.session.
completed`受信時に得られる`customer`をstore_idに紐付けて書き込むのが自然な設計だが、実
Firestore接続が前提のため本フェーズでは設計のみに留め、次回以降の課題として残す。

## 3. `route_stripe_event()`: イベント種別・store_id解決のみを行う薄い関数

course-set-pasha/aircon-pashaの`dispatch_stripe_event()`は「解決した上でハンドラ関数まで
呼び出す」設計だったが、本ventureの2つの既存ハンドラ(`handle_payment_succeeded()`・
`handle_subscription_activated()`)はいずれも`StoreDunningState`・`StoreSubscriptionState`
という別々の状態クラス(実Firestoreドキュメントの読み取り結果)を引数に取り、`route_stripe_
event()`自身はFirestore接続を持たない。そのため本関数は「どのイベントか・store_idは何か」を
判定するところまでに留め、対応する状態クラスの読み込み・ハンドラ呼び出し・書き戻しは、実際の
Cloud Functionsエントリポイント(実Firestore接続後に実装)側の責務として切り分ける。

```python
EVENT_CHECKOUT_SESSION_COMPLETED = "checkout.session.completed"
EVENT_INVOICE_PAYMENT_SUCCEEDED = "invoice.payment_succeeded"
EVENT_INVOICE_PAYMENT_FAILED = "invoice.payment_failed"

@dataclass
class StripeEventRoute:
    event_type: Optional[str]
    store_id: Optional[str] = None
    customer_id: Optional[str] = None
    ignored: bool = False
    unresolved_customer: bool = False

def route_stripe_event(
    event: dict,
    *,
    resolve_store_id_by_customer: Callable[[str], Optional[str]],
) -> StripeEventRoute:
```

処理:

1. 対象3種(上記EVENT_*定数)以外は`ignored=True`で終える(LINE側`dispatch_webhook_events()`
   ・course-set-pasha `dispatch_stripe_event()`と同じ「対応ハンドラの無い種別は無視」方針)。
2. `checkout.session.completed`: `client_reference_id`を直接読む。空/欠落時は
   `unresolved_customer=True`で終える(Checkout Session作成時に必ず設定される想定〈2節〉
   だが、不正なイベント・テスト用イベントへの防御)。`resolve_store_id_by_customer`は
   **呼ばない**(2節の単純化点)。
3. `invoice.payment_succeeded`・`invoice.payment_failed`: `customer`を
   `resolve_store_id_by_customer()`に渡す。`None`が返れば`unresolved_customer=True`
   (未知の顧客、`stripe_customer_id`変換テーブル未整備)。

## 4. 新設: `handle_payment_failed()`(1節で判明した欠落の解消)

`cloud_function_payment_webhook.py`に、`invoice.payment_failed`受信時に
`payment_failure_detected_at`を書き込む関数を新設する(`handle_payment_succeeded()`と対の
関数)。

```python
def handle_payment_failed(state: StoreDunningState, event_time: datetime) -> bool:
```

- 既に`payment_failure_detected_at`が設定済み(dunning進行中)の場合は何もせず`False`を返す
  (Stripeは決済失敗を複数回リトライしうるため、2回目以降の`invoice.payment_failed`で検知
  時刻を上書きするとdunningスケジュールの起点がずれてしまう。冪等性を状態そのもので担保する
  既存方針〈`classify_payment_succeeded()`と同じ考え方〉を踏襲)。
- `suspension_reason == "trial_unselected"`(既存の別の休止経路)の場合も何もせず`False`を
  返す。`cloud_function_subscription_activated_webhook.py`の`classify_subscription_
  activated()`が`payment_failed`側の状態に触れないのと対称に、本関数も`trial_unselected`側の
  状態には触れない(1節の責務分担の原則を新規関数にも適用)。
- それ以外は`payment_failure_detected_at = event_time`を設定し`True`を返す。

## 5. 未解決事項・次の課題

- `route_stripe_event()`・`handle_payment_failed()`とも実装・テストは本フェーズで完了させる
  (承認不要、実接続なしで検証可能)。
- 実際のCloud Functionsエントリポイント(`receive_stripe_webhook(request)`相当。
  `verify_stripe_signature()`→JSONパース→`route_stripe_event()`→store_idを使った実
  Firestore読み込み→該当ハンドラ〈`handle_payment_succeeded()`/`handle_subscription_
  activated()`/`handle_payment_failed()`〉呼び出し→書き戻し、の一連の配線)は、実Firestore
  接続(オーナー承認待ち)が前提のため引き続き次回以降の課題として残る。
- (解消済み 2026-08-31・フェーズ続き160: `customer → store_id`変換テーブルを
  stripe-customer-id-reverse-lookup-design.mdとして設計・実装した。
  `store_profile_store.py`に`get_store_id_by_stripe_customer_id()`(逆引き)・
  `make_resolve_store_id_by_customer()`(`route_stripe_event()`への結線用ファクトリ)を
  追加し、既存の`handle_checkout_session_completed()`が順引きと同時に逆引きも書き込むよう
  拡張した。テスト11件追加、venture全体461件全件パス。実際のCloud Functionsエントリ
  ポイント本体は実Firestore接続が前提のため引き続き次回以降の課題として残る)。
- 実Stripe Webhookエンドポイントのデプロイ・`webhook_secret`の取得・保管はいずれも
  オーナー承認待ちの範囲(pending-approval.md参照)。
