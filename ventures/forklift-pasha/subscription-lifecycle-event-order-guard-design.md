# customer.subscription.deleted/created(canceled_at)配信順序入れ替わりガード
(subscription-lifecycle-event-order-guard-design.md、フェーズ214)

## 1. 背景

フェーズ213(checkout-session-completed-event-order-guard-design.md)の「次回候補(1)」
として、`customer.subscription.deleted`・`customer.subscription.created`への同種ガードの
横展開(解約直後の再契約シナリオで優先度が高いと判断)を棚卸しした。

`stripe_webhook.handle_customer_subscription_deleted()`(フェーズ129)・
`handle_customer_subscription_created()`(フェーズ130)はいずれも`customer`から
`internal_id`を逆引きした後、`canceled_at`の書き込み/クリアを無条件に行っており、
`handle_customer_subscription_updated()`・`handle_checkout_session_completed()`が既に
備えるevent_timeベースの配信順序入れ替わりガードが一度も実装されていなかった。

## 2. 具体的にどう壊れるか

解約直後に同じ事業者がすぐ再契約する(例: 誤って解約した後にすぐ契約し直す、プラン変更の
ためいったん解約してから別プランで契約し直す)運用は実際に起こり得る。Stripeの
「at least once」配信・非同期配送により、`customer.subscription.deleted`
(解約、古いイベント)と`customer.subscription.created`(再契約、新しいイベント)の到着
順序が入れ替わるケースが理論上あり得る。

従来コードでは両ハンドラとも無条件で`canceled_at`を書き換えるため、以下の順で配信される
と、再契約済みにもかかわらず事業者が解約状態のまま扱われてしまう欠落がある。

1. 事業者が解約(`subscription.deleted`発生、event_time=t1)。
2. 直後に再契約(`subscription.created`発生、event_time=t2 > t1)。
3. ネットワーク遅延等により`created`(t2)が先に届き、`handle_customer_subscription_
   created()`が`canceled_at`をクリアする。
4. 遅延配信された`deleted`(t1)が後から届き、`handle_customer_subscription_deleted()`が
   `canceled_at`を再契約後の時刻で再設定してしまう。

結果として、`is_subscription_canceled()`相当の判定(`trial_management.py`)が再契約済みの
事業者を解約済みと誤判定し、`is_generation_paused()`の対象になってしまう(有料の再契約
ユーザーが生成機能を使えなくなる重大な欠落)。

## 3. 修正方針

`customer.subscription.deleted`と`customer.subscription.created`はどちらも`canceled_at`
を書き換える対になるイベントのため、`customer.subscription.updated`
(`subscription_updated_event_time`)・`checkout.session.completed`
(`checkout_session_completed_event_time`)とは異なり、**両イベント種別で1つの
event_timeキーを共有する**設計とした(片方のevent_timeだけを見ても、もう片方との
前後関係が判定できないため)。

`FleetOperatorStoreProtocol`(trial_management.py)に`get_subscription_lifecycle_event_time
(internal_id) -> Optional[datetime]`/`set_subscription_lifecycle_event_time(internal_id,
event_time: datetime) -> None`を追加し、`InMemoryFleetOperatorStore`にも実装した
(internal_idごとに、deleted/createdのいずれかで`canceled_at`を最後に実際に反映した
イベントの`event.created`を記録する専用の辞書)。

`stripe_webhook.py`に以下のヘルパーを新設した(既存の`_is_stale_subscription_updated_
event()`等と同一の変換・判定ルール)。

- `_is_stale_subscription_lifecycle_event(store, internal_id, event_time)`: `event_time`が
  `None`、または`store`が新メソッド未対応、または記録済みevent_timeが未設定の場合は
  「判定不能」として`False`(常に適用、後方互換)。今回の`event_time`が記録済みの
  event_time「以下」であれば`True`(stale)。
- `_record_subscription_lifecycle_event_time(store, internal_id, event_time)`: `event_time`
  が`None`、または`store`が新メソッド未対応の場合は何もしない。

`handle_customer_subscription_deleted()`・`handle_customer_subscription_created()`の両方に
`event_time: Optional[datetime] = None`キーワード引数を追加し、`internal_id`解決直後・
`canceled_at`書き込み/クリア直前でstale判定を行う。stale時は`canceled_at`を一切変更せず
`stale=True`(`SubscriptionDeletedResult`/`SubscriptionCreatedResult`に新設)を返す(他
ガード同様「stale全体スキップ」方針)。stale判定を通過した場合は書き込み/クリアの成否に
かかわらずevent_timeを記録する。

上記2.の壊れ方のシナリオでは、ステップ3で`created`(t2)が共有キーにt2を記録するため、
ステップ4の遅延`deleted`(t1 ≤ t2)はstale判定されて`canceled_at`を再設定しない
(再契約状態が正しく保たれる)。逆に、再契約後に本当に再度解約した場合(t3 > t2の
`deleted`)は正しく適用される。

`receive_stripe_webhook()`の両分岐から、受信したイベント全体に
`_event_time_from_created(parsed)`を適用した結果をそのまま渡すよう配線した。

## 4. スコープ外

- (解消済み 2026-11-06 20:00 UTC・フェーズ216: `invoice.payment_failed`・
  `invoice.payment_succeeded`間の配信順序入れ替わりガードを
  payment-failure-event-order-guard-design.mdとして設計・実装した。`payment_failure_
  event_time`キーを両イベントで共有する方式。詳細は同ファイル参照。)
- (解消済み 2026-11-07 19:00 UTC・フェーズ219: `firestore_fleet_operator_adapter.py`に
  `subscription_updated_event_time`・`checkout_session_completed_event_time`と同時に
  `subscription_lifecycle_event_time`も実コード化した〈`get/set_subscription_lifecycle_
  event_time()`〉。詳細はfirestore-data-model.md・README.mdフェーズ219参照。)
- (解消済み 2026-11-08 10:00 UTC・フェーズ221: oshien-pasha側を確認したところ、
  `prototype/stripe_webhook.py`は`customer.subscription.deleted`・
  `customer.subscription.created`・`customer.subscription.updated`をいずれも
  `fan_pass_store.update_subscription_status(internal_id, status, event_time=event_time)`
  経由でディスパッチしており、`update_subscription_status()`自体がフェーズ88
  〈subscription-updated-event-order-guard-preemptive-note.md〉時点で
  `event_time <= 直前の適用済みevent_time`ならスキップする配信順序入れ替わりガードを
  既に備えていた。本ファイル作成時点(フェーズ214)の「oshien-pashaはStripe決済導線が
  設計途上で未着手」という前提が陳腐化していたと判明し是正した。一方event-komiguai-pasha
  は`prototype/stripe_webhook.py`が`checkout.session.completed`のみを処理し
  `customer.subscription.*`のディスパッチ自体が未実装のため、本ガードの横展開要否確認は
  同venture側でサブスクリプションライフサイクル処理に着手した時点まで持ち越しとする
  〈次回以降の棚卸し候補として継続〉。)

## 5. テスト

`test_stripe_webhook.py`に11件のテスト関数相当のチェックを追加(正常順序での適用確認・
遅延配信された古いdeletedのstaleスキップ・同時刻イベントのstaleスキップ・より新しい
event_timeのcreatedでの正常適用・再契約直後に遅延配信された古いdeletedがstaleスキップ
されcanceled_atが再設定されないこと〈本ガードの主目的のシナリオ〉・event_time省略時の
従来通り無条件適用の後方互換確認)。`python3 prototype/test_stripe_webhook.py`単体の
check()呼び出しは104件→115件(+11)。venture全体は`python3 -m unittest discover -s
prototype -p "test_*.py"`(100件、変更なし)・`python3 prototype/run_all_tests.py`
(24ファイル全パス、変更なし)・schema検証11件(`python3 schema/validate_test_cases.py`)・
`node prototype/browser_mockup_checks.js`(49件、変更なし)いずれもパスを確認した
(回帰なし)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: (1)`invoice.payment_failed`・`invoice.payment_succeeded`への同種ガードの
横展開の要否検討(両イベントはそれぞれ別フィールド`payment_failure_detected_at`を扱い、
`canceled_at`とは独立しているため同一キー共有の必要性は低いと見込まれるが未検討)、
(2)event-komiguai-pasha・oshien-pashaの同種ガード有無の確認、(3)他venture・アイデア
領域の前進。
