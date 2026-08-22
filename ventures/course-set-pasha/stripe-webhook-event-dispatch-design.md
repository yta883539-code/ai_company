# Stripe Webhookのイベント種別ディスパッチ設計

作成日: 2026-08-22(フェーズ94)

stripe-webhook-signature-verification-design.md(フェーズ93)「次にやること」で残っていた
「イベント種別(`customer.subscription.deleted`等)ディスパッチ〜
`mark_deletion_candidate_on_subscription_deleted()`等の呼び出しを結ぶエンドポイント本体」
のうち、実Stripeアカウント接続なしでも設計・実装できる部分(イベント種別に応じた振り分け
ロジック)に対応する。webhook-event-dispatch-design.md(フェーズ81、LINE側)と同じ位置づけ。

## 1. 方針: `dispatch_stripe_event()`

`prototype/deletion_candidate.py`の3関数(`mark_deletion_candidate_on_subscription_deleted()`・
`clear_deletion_candidate_on_subscription_reactivated()`・`list_deletion_candidates()`)は
いずれも`user_id`を直接引数に取る設計だが、実際のStripe Webhookイベント(`event.data.object`)
が持つのは`customer`(Stripeカスタマーオブジェクト ID、例: `cus_ABC123`)であり、内部の
`user_id`とは別の識別子である。この対応付け(`stripe_customer_id → user_id`)を管理する
ストアはcourse-set-pashaにまだ存在せず(申込フォーム提出フロー・LINE user_id連携のいずれも
Stripeカスタマー作成を扱っていないため)、実Stripe接続後にどう`user_profile`へ
`stripe_customer_id`を書き込むかは別途設計が必要な未解決事項として残る。

そのため本フェーズでは、`customer` → `user_id`の解決を`resolve_user_id`という1引数の
呼び出し可能オブジェクト(`Callable[[str], Optional[str]]`)として外から注入する設計とし、
実際の解決ロジック(実Firestoreクエリ等)を待たずにディスパッチ本体を検証可能にする
(`InMemoryProfileDeletionCandidateStore`と同じ「Protocol/Callableの差し替えで実接続を
後回しにする」パターンの踏襲)。

```python
def dispatch_stripe_event(
    event: dict,
    *,
    store: ProfileDeletionCandidateStoreProtocol,
    resolve_user_id: Callable[[str], Optional[str]],
    now: Optional[datetime] = None,
) -> StripeDispatchResult:
```

処理順序:

1. `event.get("type")`を確認する。対象は`customer.subscription.deleted`・
   `customer.subscription.created`・`customer.subscription.updated`の3種のみ。
   それ以外(`invoice.paid`等)は`StripeDispatchResult.ignored_types`に種別名を記録し、
   何もせず終える(design方針: webhook-event-dispatch-design.mdのLINE側「対応する
   ハンドラを持たない種別は無視」を踏襲)。
2. `event["data"]["object"]["customer"]`を`resolve_user_id()`に渡す。`None`が
   返った場合(未知の顧客・マッピング未整備)は処理をスキップし、
   `StripeDispatchResult.unresolved_customers`に`customer` IDを記録する(実害のある
   例外にはせず、未解決のまま安全側に倒す)。
3. `customer.subscription.deleted`: `event.get("created")`(Stripeイベントの発生時刻、
   Unixタイムスタンプ)を`event_time`として`mark_deletion_candidate_on_subscription_deleted()`
   を呼ぶ。`created`が無い/数値でない場合は`status="invalid_event"`扱いで記録し呼ばない
   (不正なペイロードへの防御)。
4. `customer.subscription.created`: 常に`clear_deletion_candidate_on_subscription_reactivated()`
   を呼ぶ(design 4節のとおり、初回契約時に呼ばれても冪等で実害なしのため区別しない)。
5. `customer.subscription.updated`: `event["data"]["object"]["status"]`が`active`または
   `trialing`の場合のみ`clear_deletion_candidate_on_subscription_reactivated()`を呼ぶ。
   それ以外のstatus(`past_due`・`canceled`等)への変化は本設計の対象外
   (stripe-cancellation-deletion-candidate-trigger-design.mdの前提どおり、
   `canceled`への遷移は`customer.subscription.deleted`イベント自体で捕捉される)。

## 2. 結果の集約

```python
@dataclass
class StripeDispatchResult:
    marked_user_ids: list = field(default_factory=list)       # 削除候補化した user_id
    cleared_user_ids: list = field(default_factory=list)      # 削除候補化を取り消した user_id
    ignored_types: list = field(default_factory=list)         # 対応ハンドラの無い type
    unresolved_customers: list = field(default_factory=list)  # resolve_user_id が None を返した customer
    invalid_events: list = field(default_factory=list)        # created が数値でない等、不正な payload
```

`clear_deletion_candidate_on_subscription_reactivated()`の戻り値(実際に削除候補フラグを
消したか否か)は`cleared_user_ids`には反映しない(design方針: 冪等呼び出しであること自体が
目的であり、呼び出し自体を`cleared_user_ids`に記録すれば十分。実際に変更が発生したかは
`prototype/deletion_candidate.py`のテストで別途担保済み)。

## 3. `verify_stripe_signature()`との結線

`receive-webhook-http-entry-point-design.md`(LINE版`receive_webhook()`)と同じ構成で、
将来的に生のHTTPリクエストボディを受け取るエントリポイント(`receive_stripe_webhook()`相当)を
追加する際は、(1)`verify_stripe_signature()`で署名検証、(2)通過後に`json.loads()`で
パース、(3)`dispatch_stripe_event()`に委譲、という順序になる想定。本フェーズは
`dispatch_stripe_event()`本体のみを対象とし、HTTPエントリポイント自体の実装は次の課題として
残す(`resolve_user_id`の実装〈実Firestoreクエリ〉・`webhook_secret`の取得方法と合わせ、
実Stripeアカウント接続後の課題)。

## 4. 未解決事項・次の課題

- `stripe_customer_id → user_id`の対応付けストア自体(`resolve_user_id`の実装)は未設計。
  実Stripe接続時に、申込フォーム提出フロー(application-form-submission-flow-design.md)の
  どの段階で`user_profile/{user_id}`に`stripe_customer_id`を書き込むかを含めて設計する
  必要がある。
- `receive_stripe_webhook()`(HTTPエントリポイント本体、`verify_stripe_signature()`と
  `dispatch_stripe_event()`を結ぶ薄い配線)自体はまだ実装していない。LINE側
  `receive_webhook()`と同じ構成で追加できる見込みだが、`webhook_secret`の取得方法
  (環境変数 or Secret Manager)の設計と合わせ次回に持ち越す。
- 実Stripe Webhookエンドポイントのデプロイ(実GCPプロジェクト・実Stripeアカウント接続)は
  引き続きオーナー承認待ちの範囲。
