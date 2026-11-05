# customer.subscription.updated(plan_id同期)配信順序入れ替わりガード
(subscription-updated-event-order-guard-design.md、フェーズ212)

## 1. 背景

kura-pashaフェーズ198(subscription-updated-event-order-guard-design.md)は、`customer.
subscription.updated`受信時のplan_id同期・解約予約受理/取り消し通知が、Stripeの
「at least once」配信・非同期配送により配信順序が入れ替わった場合に、既に新しいイベントで
確定済みの値を遅延配信された古いイベントの値で誤って上書きしてしまう欠落を発見・是正した。
course-set-pasha・line-reservation-ai・aircon-pashaはいずれも同種のガードを既に横展開済み
(各venture内のコメント・design docで相互参照済み)であることを、本フェーズ(kura-pasha側の
「次回候補」対応としての横断棚卸し、2026-11-05 21:00 UTC定例更新)で確認した。

一方、本venture(forklift-pasha)の`stripe_webhook.handle_customer_subscription_updated()`
(stripe-subscription-updated-dispatch-design.md、フェーズ128)は、`customer`から
`internal_id`を逆引きした後、`plan_id_resolution.sync_plan_id_on_subscription_event()`を
常に無条件で呼び出しており、event_timeベースの配信順序入れ替わりガードが一度も実装されて
いなかったことが、今回の棚卸しで判明した。

## 2. 具体的にどう壊れるか

Stripeカスタマーポータル経由で短期間に複数回プラン変更(例: light→fleet→lightのように
連続変更)が行われた場合、後発のイベントが先に、先発のイベントが後から遅延配信される
ケースが理論上あり得る。この場合、従来コードでは無条件で最新の`data_object`を反映して
しまうため、既に新しいイベントで確定済みの`plan_id`を、遅延配信された古いイベントの値で
誤って上書きしてしまう(kura-pashaの「ケースA/B」と同種の欠落)。

本ventureは`customer.subscription.updated`でplan_id同期のみを行い(解約予約受理/取り消し
通知のようなLINE通知配線は未着手、tech-stack.mdフェーズ7のLINE非依存Webフォーム方針の
ため)、影響範囲はWebフォーム上に表示される現在のプラン表示が一時的に誤った値になる点に
限定される(決済自体の二重課金・契約状態の誤判定には直結しない)。

## 3. 修正方針

`FleetOperatorStoreProtocol`(trial_management.py)に`get_subscription_updated_event_time
(internal_id) -> Optional[datetime]`/`set_subscription_updated_event_time(internal_id,
event_time: datetime) -> None`を追加し、`InMemoryFleetOperatorStore`にも実装した
(internal_idごとに、plan_id同期を最後に実際に反映したイベントの`event.created`を記録する
専用の辞書)。

`stripe_webhook.py`に以下のヘルパーを新設した(kura-pashaフェーズ194の同名ヘルパーと同一の
変換・判定ルール)。

- `_event_time_from_created(event: dict) -> Optional[datetime]`: イベント全体のトップ
  レベル`created`(Unixタイムスタンプ)を`datetime`へ変換する。欠落・非数値の場合は`None`
  (判定不能として常に適用)。
- `_is_stale_subscription_updated_event(store, internal_id, event_time)`: `event_time`が
  `None`、または`store`が新メソッド未対応(`getattr(..., None)`)、または記録済み
  event_timeが未設定の場合は「判定不能」として`False`(常に適用、後方互換)。今回の
  `event_time`が記録済みのevent_time「以下」であれば`True`(stale、同時刻は既に処理済み
  として再適用しない)。
- `_record_subscription_updated_event_time(store, internal_id, event_time)`: `event_time`
  が`None`、または`store`が新メソッド未対応の場合は何もしない。

`handle_customer_subscription_updated()`に`event_time: Optional[datetime] = None`引数を
追加し、`internal_id`解決直後・`sync_plan_id_on_subscription_event()`呼び出し直前でstale
判定を行う。stale時はplan_id同期を一切行わず`SubscriptionUpdatedSyncResult(synced=False,
error="stale_event", stale=True)`を返す(他venture同様「stale全体スキップ」方針)。stale
判定を通過した場合はplan_id同期の成否(`plan_id_written`がTrue/False)にかかわらず
event_timeを記録する(course-set-pashaの`_record_subscription_updated_event_time()`と
同じ「結果にかかわらず記録」方針)。

`receive_stripe_webhook()`の`customer.subscription.updated`分岐から、受信したイベント
全体に`_event_time_from_created(parsed)`を適用した結果をそのまま渡すよう配線した。

## 4. スコープ外

- 本ガードは`customer.subscription.updated`のplan_id同期のみを対象とする。本venture未着手
  の解約予約受理/取り消し通知(LINE非依存のWebフォーム方針のため、そもそも通知導線自体が
  存在しない)は対象外。
- `checkout.session.completed`・`customer.subscription.deleted`・`customer.subscription.
  created`・`invoice.payment_failed`・`invoice.payment_succeeded`にも同種のevent_time
  ベースのガードは本venture内に一度も実装されていないことが今回の棚卸しで判明したが、本
  フェーズでは`customer.subscription.updated`の是正のみに限定する(次回以降の棚卸し候補)。
- event-komiguai-pasha・oshien-pasha(いずれもStripe決済導線自体が設計途上)の同種ガード
  有無の確認は未実施。

## 5. テスト

`test_stripe_webhook.py`に9件のテスト関数相当のチェックを追加(正常順序での適用確認・
遅延配信された古いイベントのstaleスキップ・同時刻イベントのstaleスキップ・より新しい
event_timeでの正常適用・event_time省略時の従来通り無条件適用の後方互換確認)。
`python3 prototype/test_stripe_webhook.py`単体のcheck()呼び出しは86件→95件(+9)。venture
全体は`python3 -m unittest discover -s prototype -p "test_*.py"`(100件、変更なし)・
`python3 prototype/run_all_tests.py`(24ファイル全パス、変更なし)・schema検証11件
(`python3 schema/validate_test_cases.py`)・`node prototype/browser_mockup_checks.js`
(49件、変更なし)いずれもパスを確認した(回帰なし)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: (1)`checkout.session.completed`等、本venture内の他イベントハンドラへの同種
ガードの横展開、(2)event-komiguai-pasha・oshien-pashaの同種ガード有無の確認、(3)他
venture・アイデア領域の前進。
