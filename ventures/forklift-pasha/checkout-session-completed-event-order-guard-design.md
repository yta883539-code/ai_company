# checkout.session.completed(stripe_customer_id書き込み)配信順序入れ替わりガード
(checkout-session-completed-event-order-guard-design.md、フェーズ213)

## 1. 背景

subscription-updated-event-order-guard-design.md(フェーズ212)の「4. スコープ外」で、
`checkout.session.completed`等、本venture内の他イベントハンドラにも同種のevent_timeベースの
配信順序入れ替わりガードが一度も実装されていないことが判明していた(次回候補(1))。

横断棚卸しの結果、aircon-pashaフェーズ287(checkout-session-completed-event-order-guard-
design.md)・kura-pashaが、`checkout.session.completed`受信時の`stripe_customer_id`書き込みに
同種のガードを既に横展開済みであることを確認した。一方、本venture
(forklift-pasha)の`stripe_webhook.handle_checkout_session_completed()`(フェーズ127)は
`store.set_stripe_customer_id()`を受信のたびに無条件で上書きしており、event_timeベースの
ガードが一度も実装されていなかった。

## 2. 具体的にどう壊れるか

`client_reference_id`(= `internal_id`)に対して、何らかの理由(例: 決済フォームの
二重送信・古いタブでの再送信)で複数のCheckout Sessionが作成され、それぞれ異なる
`stripe_customer_id`に対する`checkout.session.completed`イベントが短期間に発生した場合、
Stripeの「at least once」配信・非同期配送により配信順序が入れ替わることが理論上あり得る。
この場合、従来コードでは無条件で最新の`data_object`を反映してしまうため、既に新しいイベントで
確定済みの`stripe_customer_id`(以降の`customer.subscription.*`イベントの逆引きキーとして
使われる)を、遅延配信された古いイベントの値で誤って上書きしてしまう
(subscription-updated-event-order-guard-design.mdの「ケースA/B」と同種の欠落)。

誤った`stripe_customer_id`で上書きされると、`get_internal_id_by_stripe_customer_id()`の
逆引きインデックスが古い値を指したままになり、以降の`customer.subscription.updated`等の
plan_id同期が本来の事業者に届かなくなる可能性がある。

## 3. 修正方針

`FleetOperatorStoreProtocol`(trial_management.py)に
`get_checkout_session_completed_event_time(internal_id) -> Optional[datetime]`/
`set_checkout_session_completed_event_time(internal_id, event_time: datetime) -> None`を
追加し、`InMemoryFleetOperatorStore`にも実装した(`_subscription_updated_event_time`と
同型の専用辞書)。

`stripe_webhook.py`に以下のヘルパーを新設した
(aircon-pashaフェーズ287の同名ヘルパーと同一の変換・判定ルール)。

- `_is_stale_checkout_session_completed_event(store, internal_id, event_time)`: `event_time`
  が`None`、または`store`が新メソッド未対応、または記録済みevent_timeが未設定の場合は
  「判定不能」として`False`(常に適用、後方互換)。今回の`event_time`が記録済みのevent_time
  「以下」であれば`True`(stale、同時刻は既に処理済みとして再適用しない)。
- `_record_checkout_session_completed_event_time(store, internal_id, event_time)`: `event_time`
  が`None`、または`store`が新メソッド未対応の場合は何もしない。

`handle_checkout_session_completed()`に`event_time: Optional[datetime] = None`引数を追加し、
`internal_id`・`stripe_customer_id`の必須チェック通過直後にstale判定を行う。staleでない場合
のみ`store.set_stripe_customer_id()`を呼び出しevent_timeを記録する(staleの場合は
`stripe_customer_id`を一切書き込まず`stale=True`を返す)。既存の`plan_id`書き込み
(`write_plan_id_from_checkout_session_metadata()`)・`upgraded_at`書き込み(「一度きり」判定)
は本ガードの対象外とし、従来通りの挙動を維持する(aircon-pashaフェーズ287と同じ切り分け。
`plan_id`は`customer.subscription.updated`側で既に独立したガードを持ち、`upgraded_at`は
「未設定時のみ書き込み」で既に保護されているため、対象を`stripe_customer_id`のみに限定する)。

`receive_stripe_webhook()`の`checkout.session.completed`分岐から、既存の
`_event_time_from_created()`(subscription-updated-event-order-guard-design.mdで追加済みの
汎用ヘルパー、イベント全体のトップレベル`created`を変換)の結果をそのまま渡すよう配線した。

## 4. スコープ外

- `customer.subscription.deleted`・`customer.subscription.created`・`invoice.payment_failed`・
  `invoice.payment_succeeded`には、本venture内に同種のevent_timeベースのガードが一度も
  実装されていない(次回以降の棚卸し候補)。特に`customer.subscription.deleted`
  (`canceled_at`書き込み)と`customer.subscription.created`(`canceled_at`クリア)は、
  解約後の即時再契約時に配信順序が入れ替わった場合、再契約後に遅延配信された解約イベントが
  `canceled_at`を誤って再設定してしまう可能性があり、同種の欠落が疑われるため優先度が高い。
- event-komiguai-pasha・oshien-pasha(いずれもStripe決済導線自体が設計途上)の同種ガード
  有無の確認は未実施。

## 5. テスト

`test_stripe_webhook.py`に`handle_checkout_session_completed()`向け9件のチェックを追加
(正常順序での適用確認・遅延配信された古いイベントのstaleスキップ・同時刻イベントのstale
スキップ・より新しいevent_timeでの正常適用・event_time省略時の従来通り無条件適用の後方互換
確認)。単体の`python3 prototype/test_stripe_webhook.py`のcheck()呼び出しは100件→104件
(+4、既存の`_checkout_event()`ヘルパーへの`created`引数追加分を含む)。venture全体は
`python3 -m unittest discover -s prototype -p "test_*.py"`(100件、変更なし)・`python3
prototype/run_all_tests.py`(24ファイル全パス、変更なし)・schema検証11件(`python3
schema/validate_test_cases.py`)・`node prototype/browser_mockup_checks.js`(49件、変更なし)
いずれもパスを確認した(回帰なし)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: (1)`customer.subscription.deleted`・`customer.subscription.created`への同種
ガードの横展開(4節で優先度が高いと判断した解約直後の再契約シナリオ)、(2)
event-komiguai-pasha・oshien-pashaの同種ガード有無の確認、(3)他venture・アイデア領域の前進。
