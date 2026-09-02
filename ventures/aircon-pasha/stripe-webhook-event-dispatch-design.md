# Stripe Webhookのイベント種別ディスパッチ設計

作成日: 2026-08-25(フェーズ126)

フェーズ125の申し送り通り、「Stripe Webhookエンドポイント本体(`receive_webhook()`のStripe版に
相当する、リクエストボディの受け取り〜`verify_stripe_signature()`〜イベント種別
(`customer.subscription.deleted`等)ディスパッチ〜`mark_deletion_candidate_on_subscription_deleted()`
等(`prototype/deletion_candidate.py`フェーズ124で実装済み)の呼び出しを結ぶ層)」のうち、
実Stripeアカウント接続なしでも設計・実装できる部分(イベント種別に応じた振り分けロジック)に
対応する。course-set-pashaのstripe-webhook-event-dispatch-design.md(フェーズ94)と同じ位置づけ。

## 1. 方針: `dispatch_stripe_event()`

`prototype/deletion_candidate.py`の3関数(`mark_deletion_candidate_on_subscription_deleted()`・
`clear_deletion_candidate_on_subscription_reactivated()`・`list_deletion_candidates()`)は
いずれも`user_id`を直接引数に取る設計だが、実際のStripe Webhookイベント(`event.data.object`)
が持つのは`customer`(Stripeカスタマーオブジェクト ID、例: `cus_ABC123`)であり、内部の
`user_id`(本ventureではLINEの`user_id`)とは別の識別子である。この対応付け
(`stripe_customer_id → user_id`)自体は、user-account-linking-design.md(フェーズ107)で
連携コード方式の設計までは完了しているが、実際のストア実装(実Firestoreクエリ等)は実Stripe
アカウント接続後の課題として残っている。

そのため本フェーズでは、course-set-pasha版と同じく`customer` → `user_id`の解決を
`resolve_user_id`という1引数の呼び出し可能オブジェクト(`Callable[[str], Optional[str]]`)
として外から注入する設計とし、実際の解決ロジックを待たずにディスパッチ本体を検証可能にする
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

処理順序(course-set-pasha版と同一):

1. `event.get("type")`を確認する。対象は`customer.subscription.deleted`・
   `customer.subscription.created`・`customer.subscription.updated`の3種のみ。
   それ以外(`invoice.paid`等)は`StripeDispatchResult.ignored_types`に種別名を記録し、
   何もせず終える。
2. `event["data"]["object"]["customer"]`を`resolve_user_id()`に渡す。`None`が
   返った場合(未知の顧客・連携コード未紐付け)は処理をスキップし、
   `StripeDispatchResult.unresolved_customers`に`customer` IDを記録する(実害のある
   例外にはせず、未解決のまま安全側に倒す)。
3. `customer.subscription.deleted`: `event.get("created")`(Stripeイベントの発生時刻、
   Unixタイムスタンプ)を`event_time`として`mark_deletion_candidate_on_subscription_deleted()`
   を呼ぶ。`created`が無い/数値でない場合は`status="invalid_event"`扱いで記録し呼ばない。
4. `customer.subscription.created`: 常に`clear_deletion_candidate_on_subscription_reactivated()`
   を呼ぶ(初回契約時に呼ばれても冪等で実害なしのため区別しない)。
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
消したか否か)は`cleared_user_ids`には反映しない(冪等呼び出しであること自体が目的であり、
呼び出し自体を記録すれば十分。実際に変更が発生したかは`prototype/test_deletion_candidate.py`で
別途担保済み)。

## 3. `verify_stripe_signature()`との結線

(解消済み 2026-09-02 14:02 UTC・フェーズ173点検: 以下は執筆時点〈フェーズ94〉の想定として
残っていたが、実際にはフェーズ127(stripe-webhook-http-entry-point-design.md)で
`receive_stripe_webhook()`として実装済み。想定通り(1)`verify_stripe_signature()`で署名検証、
(2)`json.loads()`でパース、(3)`dispatch_stripe_event()`(`customer.subscription.*`)/
`handle_checkout_session_completed()`(`checkout.session.completed`)への委譲、という順序で
結線されている)

`webhook-http-entry-point-design.md`(LINE版`receive_webhook()`)と同じ構成で、将来的に
生のHTTPリクエストボディを受け取るエントリポイント(`receive_stripe_webhook()`相当)を
追加する際は、(1)`verify_stripe_signature()`(フェーズ125実装済み)で署名検証、
(2)通過後に`json.loads()`でパース、(3)`dispatch_stripe_event()`に委譲、という順序になる
想定。本フェーズは`dispatch_stripe_event()`本体のみを対象とし、HTTPエントリポイント自体の
実装は次の課題として残す(`resolve_user_id`の実装〈実Firestoreクエリ〉・`webhook_secret`の
取得方法と合わせ、実Stripeアカウント接続後の課題)。

## 4. プロトタイプ実装方針

- course-set-pashaはフェーズ94時点で設計のみにとどめ、プロトタイプ実装
  (`prototype/`への反映)は未着手のまま残っている。本ventureでは設計に続けて同一フェーズ内で
  `prototype/stripe_dispatch.py`に`dispatch_stripe_event()`本体・`StripeDispatchResult`
  データクラスを実装し、`prototype/test_stripe_dispatch.py`にテスト13件を追加した(下記の
  テスト観点を全てカバー)。`deletion_candidate.py`の3関数をそのままインポートして呼び出す
  構成とし、判定ロジック自体の再実装は行っていない。
- テスト観点: (1)対応3種別それぞれの正常系呼び出し、(2)対象外type(`invoice.paid`等)が
  `ignored_types`に記録され関数が呼ばれないこと、(3)`resolve_user_id`が`None`を返す場合に
  `unresolved_customers`へ記録されること、(4)`customer.subscription.deleted`で`created`
  欠落/非数値(`bool`型の混入を含む)時に`invalid_events`へ記録されマーク処理が呼ばれない
  こと、(5)`customer.subscription.updated`で`status`が`active`/`trialing`以外
  (`past_due`・`canceled`)なら何もしないこと、(6)`customer.subscription.created`は
  削除候補未設定でも冪等に呼べること。`prototype/`配下の全テスト実行で154件全件パス
  (既存141件+新規13件)を確認した。

## 5. 未解決事項・次の課題

- (解消済み 2026-09-02 14:02 UTC・フェーズ173点検: 以下の2点は執筆時点〈フェーズ94〉の
  記載として残っていたが、実際にはフェーズ107(user-account-linking-design.md、`get_user_id_
  by_stripe_customer_id()`のインメモリ実装)・フェーズ127(stripe-webhook-http-entry-point-
  design.md、`receive_stripe_webhook()`実装)でいずれも解消済みだったにもかかわらず本ファイルが
  未訂正のまま残っていた記載漏れと判明した)
- ~~`stripe_customer_id → user_id`の対応付けストア自体(`resolve_user_id`の実装)は
  user-account-linking-design.md(フェーズ107)で連携コード方式の設計までは完了しているが、
  実際のストア実装(実Firestoreクエリ)は未着手。~~ → `prototype/user_id_linking.py`の
  `get_user_id_by_stripe_customer_id()`としてインメモリ実装・テスト済み(実Firestore接続のみ
  実Stripeアカウント接続後の課題として残る)。
- ~~`receive_stripe_webhook()`(HTTPエントリポイント本体、`verify_stripe_signature()`と
  `dispatch_stripe_event()`を結ぶ薄い配線)自体はまだ実装していない。~~ →
  `prototype/stripe_webhook.py`の`receive_stripe_webhook()`として実装済み(フェーズ127)。
- 実Stripe Webhookエンドポイントのデプロイ(実GCPプロジェクト・実Stripeアカウント接続)は
  引き続きオーナー承認待ちの範囲。
