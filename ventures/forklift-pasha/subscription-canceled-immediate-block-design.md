# 解約確定時の生成即時ブロック(subscription-canceled-immediate-block-design.md)

## 1. 発見の経緯

kura-pashaフェーズ188・course-set-pashaフェーズ258・aircon-pashaフェーズ275で順に発見・
修正された欠落(`subscription_status == "canceled"`相当が専用分岐を持たず、有料転換済み
〈`upgraded_at`が非null〉のユーザーが解約後も既存の一時停止判定の対象にならず、決済失敗を
一度も経験しなければ無期限に生成を使い続けられてしまう)が、forklift-pasha自身にも存在するか
を確認した。

`trial_management.py`の`is_generation_paused()`は`trial_end_notified_at`が非null・
`upgraded_at`が未設定(有料転換前)の場合のみTrueを返す設計であり、`stripe_webhook.py`には
`checkout.session.completed`(紐付け・plan_id初回記録)・`customer.subscription.updated`
(plan_id同期)の2イベントしか配線されておらず、`customer.subscription.deleted`
(解約確定)は他venture未着手の種別と同じく常に200で無視されるのみだった。その結果、
**既に有料転換済みのユーザーが解約した場合、`is_generation_paused()`は`upgraded_at`が
非nullである限り常にFalseのまま**であり、course-set-pasha/aircon-pashaと同型の欠落が
forklift-pashaにも存在することを確認した。

## 2. 修正内容

aircon-pashaの`_is_subscription_canceled()`/`subscription_canceled_at`と同じ考え方を、
forklift-pashaの既存コンポーネント構成(`trial_management.FleetOperatorStoreProtocol`・
`form_submission_flow.process_form_submission()`・`stripe_webhook.py`)に合わせて実装した。

- `trial_management.py`の`FleetOperatorStoreProtocol`に`get_canceled_at`/`set_canceled_at`
  を追加し、`InMemoryFleetOperatorStore`にも実装した(`set_canceled_at(internal_id, None)`で
  クリアできる、`get_upgraded_at`/`set_upgraded_at`と同じ「上書き可」方針)。
- `is_subscription_canceled(internal_id, operator_store)`を新設。`canceled_at`が設定済みで
  あれば、トライアル進捗・`upgraded_at`の値によらず常にTrueを返す。
- `form_submission_flow.process_form_submission()`で、`is_generation_paused()`より**先に**
  `is_subscription_canceled()`を判定し、該当時はLLM呼び出し自体を行わず`CANCELED_NOTICE`を
  返す新しい`status="canceled"`分岐を追加した(解約確定を最優先する、aircon-pashaの判定順序
  と同じ方針)。
- `stripe_webhook.py`に`handle_customer_subscription_deleted()`を新設した。
  `handle_customer_subscription_updated()`と同じく`data.object.customer`から
  `store.get_internal_id_by_stripe_customer_id()`で`internal_id`を逆引きし、解決できた場合は
  決済失敗の有無によらず常に`canceled_at`を書き込む(aircon-pashaの方針と同じ、逆引き不可時は
  `error="unknown_customer"`として200で受理しつつ書き込みはスキップする)。
  `receive_stripe_webhook()`から`customer.subscription.deleted`をディスパッチするよう配線した。

## 3. 本venture固有の留意点

- aircon-pashaは`customer.subscription.created`(再契約)受信時に`subscription_canceled_at`を
  クリアする分岐も同時に追加していたが、forklift-pashaは`customer.subscription.created`自体の
  受信・配線が本venture未着手のため、本フェーズでは`customer.subscription.deleted`の配線のみに
  限定した。再契約時に`canceled_at`が残り続けると、再契約後も永久に生成がブロックされたままに
  なる別の欠落になるため、次回候補として明示する(下記「次回候補」参照)。
- `overage_notifications.py`の`PLAN_VEHICLE_LIMIT`等が参照する`plan_id`自体は本フェーズでは
  クリアしていない(`checkout-session-plan-selection-design.md`の既存方針を変更しない範囲に
  限定した)。解約後に再度`checkout.session.completed`を受信すれば`plan_id`は上書きされる。

## 4. テスト

- `test_trial_management.py`(10件追加): `get_canceled_at`/`set_canceled_at`の未設定・設定後
  取得・Noneクリア、`is_subscription_canceled()`の未設定時False・`upgraded_at`非nullでも
  `canceled_at`設定後はTrue・別operatorとの独立性。
- `test_form_submission_flow.py`(3件追加): `upgraded_at`設定済み(有料転換済み)でも
  `canceled_at`設定後は`status="canceled"`でLLM呼び出し自体を行わないこと。
- `test_stripe_webhook.py`(9件追加): `handle_customer_subscription_deleted()`の正常系
  (`canceled_at`書き込み・`upgraded_at`設定済みでも書き込まれること)・`customer`欠落・
  未知の`stripe_customer_id`、`receive_stripe_webhook()`経由のディスパッチ確認。既存の
  「未対応イベント種別は200で無視」テストが`customer.subscription.deleted`を例に使っていたが
  対応済みイベントになったため`invoice.payment_failed`に差し替えた。
- 回帰確認: `python3 prototype/run_all_tests.py`(10ファイル、全パス)・
  `python3 schema/validate_test_cases.py`(11件、変更なし)をいずれも実行しパスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし(実Stripeアカウント接続自体は既存の承認待ち事項
〈2026-10-06 22:00 UTC記載〉の範囲内であり、新たな承認待ち事項ではない)。

## 5. 次回候補(フェーズ129時点)

- (1)`customer.subscription.created`(再契約)受信時の`canceled_at`クリア分岐の実装
  (本フェーズの留保事項、再契約後に永久ブロックされたままになる欠落を未然に防ぐ)。
  → フェーズ130で対応(6節)。
- (2)承認待ち事項がオーナーから承認された場合はその着手を最優先。
- (3)Webフォームのプラン選択UI自体の実装。
- (4)他venture・アイデア領域の前進。

## 6. 再契約時のcanceled_atクリア(フェーズ130)

3節の留保事項に対応した。aircon-pashaが同時に追加していた
`customer.subscription.created`(再契約)分岐と同じ考え方を、forklift-pashaの
`stripe_customer_id`逆引き方式(`handle_customer_subscription_updated()`・
`handle_customer_subscription_deleted()`と同じ引数形)に合わせて実装した。

- `prototype/stripe_webhook.py`に`SubscriptionCreatedResult`データクラスと
  `handle_customer_subscription_created(event, store)`を新設した。`customer`から
  `internal_id`を逆引きし、`store.set_canceled_at(internal_id, None)`で`canceled_at`を
  クリアする。`InMemoryFleetOperatorStore.set_canceled_at()`は`None`渡しで該当キーを
  popする実装(2節、フェーズ129時点で既にクリア用途を想定)のため、`trial_management.py`
  側の変更は不要だった。`canceled_at`が元々未設定(初回契約、解約を経ていない)の場合も
  エラーにせず`cleared=True`を返す(冪等)。plan_id・upgraded_atの同期は対象外とし、
  既存の`customer.subscription.updated`側の配線にそのまま委ねる。
- `receive_stripe_webhook()`から`customer.subscription.created`を
  `handle_customer_subscription_created()`へディスパッチするよう配線した。

### テスト

- `test_stripe_webhook.py`にテスト18件追加: 正常系(解約済み`internal_id`の
  `canceled_at`クリア)、解約を経ていない場合の冪等なクリア、`customer`欠落、未知の
  `stripe_customer_id`、`receive_stripe_webhook()`経由のディスパッチ確認(3件)。
- 回帰確認: `python3 prototype/test_stripe_webhook.py`(68件、変更前50件+新規18件、
  全件パス)・`python3 prototype/run_all_tests.py`(10ファイル、全パス)・
  `python3 schema/validate_test_cases.py`(11件、変更なし)。

### 残課題

- line-reservation-aiの同種確認(1節で触れたkura-pasha/course-set-pasha/aircon-pashaへの
  横展開)は本フェーズでも未着手のまま。
- `customer.subscription.created`が「再契約」以外の経路(初回契約時にも発行される
  可能性があるというStripe API仕様上の論点)で届いた場合でも、本関数は`canceled_at`の
  クリアのみを行うため冪等であり実害は無いと判断し、追加の分岐は設けなかった。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。

## 7. 次回候補(フェーズ130時点)

- (1)承認待ち事項がオーナーから承認された場合はその着手を最優先。
- (2)line-reservation-aiの解約確定専用状態の横展開確認(6節から持ち越し)。
- (3)Webフォームのプラン選択UI自体の実装。
- (4)他venture・アイデア領域の前進。
