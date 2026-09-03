# Stripe Webhook HTTPエントリポイント設計

フェーズ続き183で新規作成。stripe-event-idempotency-design.md「残課題」に残っていた、
`route_stripe_event()`(ルート解決のみを行う薄い層)を実際に`handle_payment_succeeded()`・
`handle_payment_failed()`・`handle_subscription_activated()`へつなぐ統合エントリポイント
(`receive_stripe_webhook()`相当)を設計・実装する。course-set-pasha/aircon-pashaの
`stripe-webhook-http-entry-point-design.md`と同じ位置づけのドキュメントだが、本venture
固有の事情(1節参照)により実装の形は異なる。

## 0. 経緯・本venture固有の事情

course-set-pasha/aircon-pashaはStripeの状態を単一の店舗プロフィールストア
(`UserProfileStore`)に集約しており、`dispatch_stripe_event()`もそのストア1つだけを
読み書きすれば済む設計だった。一方、本ventureは以下の2つの独立した状態モデルに
分かれている(cloud_function_payment_webhook.py・cloud_function_subscription_
activated_webhook.pyの冒頭コメントで既に整理済みの設計判断):

- `StoreDunningState`(`cloud_function_send_dunning_notifications.py`): 加入後の毎月の
  継続課金失敗(dunning)、および猶予期間・制限モードからの決済成功による復旧を扱う。
  `handle_payment_succeeded()`・`handle_payment_failed()`(いずれも
  `cloud_function_payment_webhook.py`)が読み書きする。
- `StoreSubscriptionState`(`cloud_function_subscription_activated_webhook.py`):
  トライアル終了後、有料プラン未選択のまま休止モードに入っていた店舗が初めてプランを
  選択し決済を完了した場合を扱う。`handle_subscription_activated()`が読み書きする。

`route_stripe_event()`が扱う3つのイベント種別(`stripe_webhook.py`の
`_ROUTABLE_EVENT_TYPES`)は、この2つの状態モデルへ次のように振り分けられる:

| イベント種別 | 状態モデル | ハンドラ |
|---|---|---|
| `checkout.session.completed` | `StoreSubscriptionState` | `handle_subscription_activated()` |
| `invoice.payment_succeeded` | `StoreDunningState` | `handle_payment_succeeded()` |
| `invoice.payment_failed` | `StoreDunningState` | `handle_payment_failed()` |

`customer.subscription.updated`/`customer.subscription.deleted`(`cloud_function_
subscription_cancelled_webhook.py`の`handle_subscription_updated()`/
`handle_subscription_deleted()`が扱う解約フロー)は`route_stripe_event()`が現時点で
扱う3種に含まれておらず、本ドキュメントのスコープ外(引き続き次回以降の課題として残す。
7節参照)。

## 1. ストアProtocol

2つの状態モデルそれぞれについて、`store_id`をキーに読み書きするProtocolを新設する
(course-set-pashaの`ProfileDeletionCandidateStoreProtocol`等と同じ「単一store_idに
対する薄いget/set」という設計方針を踏襲)。

```python
class StoreDunningStateStoreProtocol(Protocol):
    def get_dunning_state(self, store_id: str) -> Optional[StoreDunningState]: ...
    def set_dunning_state(self, store_id: str, state: StoreDunningState) -> None: ...

class StoreSubscriptionStateStoreProtocol(Protocol):
    def get_subscription_state(self, store_id: str) -> Optional[StoreSubscriptionState]: ...
    def set_subscription_state(self, store_id: str, state: StoreSubscriptionState) -> None: ...
```

`InMemoryStoreDunningStateStore`・`InMemoryStoreSubscriptionStateStore`をそれぞれの
検証用実装として提供する(実Firestoreへの永続化は実GCPプロジェクト作成後の課題として
別途残る、既存の全InMemory実装と同じ位置づけ)。

## 2. `receive_stripe_webhook()`

```python
def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    resolve_store_id_by_customer: Callable[[str], Optional[str]],
    dunning_store: Optional[StoreDunningStateStoreProtocol] = None,
    subscription_store: Optional[StoreSubscriptionStateStoreProtocol] = None,
    push_client: Optional[LinePushClient] = None,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
```

処理の流れ(course-set-pasha/aircon-pashaの`receive_stripe_webhook()`と同じ「安全側で
早期リターン」方針を踏襲):

1. `verify_stripe_signature()`で署名検証。失敗時は401相当を返し以降の処理を行わない。
2. `body`をJSONとしてパース。失敗、またはdictでない場合は400相当を返す。
3. `route_stripe_event()`(`event_id_store`をそのまま渡す)でイベント種別・`store_id`を
   解決する。`route.duplicate`が`True`の場合はハンドラを一切呼び出さず200・
   `duplicate=True`を返す(`route_stripe_event()`自身が`event_id_store`への
   `mark_processed()`も既に行っているため、ここでの追加のべき等性処理は不要)。
4. `route.ignored`(対象外イベント種別)、または`route.store_id`が`None`
   (`unresolved_customer`。Stripeの`customer`からstore_idへ解決できなかった、
   または`checkout.session.completed`で`client_reference_id`が空だった場合)は、
   Stripe側の再送ループを避けるためリクエスト自体は200(受理)として扱い、
   ハンドラは呼び出さない(他venture既存の方針と同じ)。
5. `route.event_type`に応じて対応するストア(`dunning_store`/`subscription_store`)から
   `route.store_id`で状態を取得する。ストア未指定(`None`)、または該当`store_id`の
   状態が見つからない場合(未知の`store_id`、または実データ未整備)は、何もせず200を
   返す(`get_runtime_dependencies()`が空の辞書を返す設計と同じ「未接続時は安全側で
   スキップ」方針。実際に発生するのは実Stripe/実Firestore接続後、通常運用では起こらない
   はずの異常系)。
6. `push_client`が`None`の場合もハンドラを呼び出さず200を返す(3つのハンドラは
   いずれも`push_client`を必須引数として取るため、未接続のまま呼び出すと例外になる。
   `dispatch_webhook_events()`側の「未接続時はスキップ」方針と同じ)。
7. 上記のいずれにも該当しない場合のみ、対応するハンドラを呼び出す:
   - `checkout.session.completed` → `handle_subscription_activated(state, push_client)`
   - `invoice.payment_succeeded` → `handle_payment_succeeded(state, push_client)`
   - `invoice.payment_failed` → `handle_payment_failed(state, event_time=resolved_now)`
     (この経路のみ`push_client`を使わない。3節参照)
8. ハンドラ呼び出し後、`SendFailed`系のoutcome(`OUTCOME_SEND_FAILED`)でなければ
   (`handle_payment_failed()`は例外なくbool、他2つはoutcomeで判定)、更新後の状態を
   `set_dunning_state()`/`set_subscription_state()`で書き戻す。送信失敗時は状態を
   変更せず、呼び出し側がHTTP 5xxを返してWebhookリトライに委ねる(各ハンドラの既存
   docstringに明記された方針をそのまま踏襲)。

## 3. `invoice.payment_failed`経路の`push_client`扱いについて

`handle_payment_failed()`(`cloud_function_payment_webhook.py`)は`push_client`を
取らず、`payment_failure_detected_at`の書き込みのみを行う(検知時点では通知を送らず、
検知〜猶予期間の通知自体は別経路の`cloud_function_send_dunning_notifications.py`
(Cloud Scheduler起動、5節)が担う設計、フェーズ続き159時点で既に確定している役割分担)。
そのため`receive_stripe_webhook()`のこの経路は2節6.の「`push_client`が`None`なら
スキップ」判定の対象外とし、`dunning_store`が指定されていれば`push_client`の有無に
関わらず状態書き込みのみを行う。

## 4. `event_id_store`の二重チェックについて

`route_stripe_event()`は自身の内部で`event_id_store.has_processed()`/
`mark_processed()`を呼び出す(stripe-event-idempotency-design.md 3節)。
`receive_stripe_webhook()`はこの結果(`route.duplicate`)をそのまま使うのみで、
`event_id_store`への直接アクセスは行わない(責務の重複を避ける)。

## 5. `StripeWebhookReceiverResult`

```python
@dataclass
class StripeWebhookReceiverResult:
    status_code: int
    route: Optional[StripeEventRoute] = None
    outcome: Optional[str] = None  # 各ハンドラのoutcome文字列、またはhandle_payment_failed()のbool由来
    error: Optional[str] = None
    duplicate: bool = False
```

## 6. テスト

`prototype/test_stripe_webhook_entry_point.py`に以下を確認するテストを追加する
(course-set-pashaの`receive_stripe_webhook()`テストと同様の観点):

1. 署名検証失敗 → 401
2. 不正JSON → 400
3. 重複イベント(`event_id_store`経由) → 200・`duplicate=True`・ハンドラ未呼び出し
4. 対象外イベント種別 → 200・ハンドラ未呼び出し
5. `store_id`未解決 → 200・ハンドラ未呼び出し
6. `checkout.session.completed` → `handle_subscription_activated()`が呼ばれ、
   状態が`subscription_store`へ書き戻される
7. `invoice.payment_succeeded` → `handle_payment_succeeded()`が呼ばれ、
   状態が`dunning_store`へ書き戻される
8. `invoice.payment_failed` → `push_client`未指定でも`handle_payment_failed()`が
   呼ばれ状態が書き戻される(3節の扱いの確認)
9. `dunning_store`/`subscription_store`/`push_client`いずれか未指定時は
   該当経路がスキップされる(後方互換の確認)
10. 該当`store_id`の状態が見つからない場合はスキップされる

## 7. 今後の課題

- `customer.subscription.updated`/`customer.subscription.deleted`
  (`cloud_function_subscription_cancelled_webhook.py`)は`route_stripe_event()`が
  扱う3種に含まれていないため、本エントリポイントの対象外のまま残る。将来対応する場合、
  `route_stripe_event()`側に対象イベント種別を追加した上で本設計と同様の振り分けを
  追加する必要がある。
- 実際のCloud FunctionsエントリポイントHTTP関数(`main(request)`相当、
  `request.get_data()`・`request.headers.get("Stripe-Signature")`からの取り出し配線)は
  course-set-pasha/aircon-pashaの`stripe_webhook.py`側`main()`相当がまだ存在しない
  (現状`cloud_function_payment_webhook.py`等はいずれも`main()`を持たずロジック本体の
  みが実装されている)ため、本venture向けに新規作成する必要がある。次回以降の課題として
  残す。
- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)、実Stripeアカウント
  接続自体は、引き続き実Stripe接続待ち(オーナー承認)の課題として残る(既存の記載を
  参照、新規追加なし)。
