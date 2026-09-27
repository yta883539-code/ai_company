# subscription_statusへのStripe Webhook配信順序入れ替わりガード
(subscription-status-event-order-guard-design.md、フェーズ194)

## 1. 背景

course-set-pasha(フェーズ261・262)・aircon-pasha(フェーズ280)は、Stripeが配信順序を
保証しない(公式ドキュメントが明記する「イベントは発生順に届くとは限らず、再送により
大幅に遅延することもある」)ことに起因する、`subscription_canceled_at`・
`deletion_candidate_at`という専用フィールドへのstale event(配信順序入れ替わり)ガードを
既に実装済みだった。aircon-pashaフェーズ280は「次回候補」として、kura-pasha・
line-reservation-aiは`subscription_status`という単一のenumフィールド方式のため同一の
実装パターン(専用フィールドの新旧比較)はそのまま適用できず、enum方式における配信順序
入れ替わりの影響を別途検討する必要があると指摘していた。本フェーズはkura-pasha側でこの
検討・実装を行った。

## 2. 具体的にどう壊れるか

kura-pashaの`subscription_status`は、`stripe_webhook.py`内の4つのハンドラがそれぞれ
無条件に上書きしている(`customer.subscription.updated`は`cancel_at_period_end`の前後比較
のみを行い、`subscription_status`自体は変更しない)。

| イベント | 遷移先 |
|---|---|
| `checkout.session.completed` | `"active"` |
| `customer.subscription.deleted` | `"canceled"` |
| `invoice.payment_failed` | `"past_due"` |
| `invoice.payment_succeeded` | `"active"` |

いずれも「今受け取ったイベントが最新の真実」という前提で無条件に上書きしていたため、
以下のような入れ替わりが理論上発生しうる。

- ケースA(解約→即再契約): 解約直後に別プランで即再契約した際、`customer.subscription.
  deleted`の配信がリトライで遅延し、新しい`checkout.session.completed`(→`"active"`)より
  後に届くと、既に有効な契約者を`"canceled"`へ誤って書き換えてしまう
  (`process_generation_request()`が`subscription_status == "canceled"`を理由に生成を
  拒否するようになる)。
- ケースB(決済失敗→即成功): 一時的な決済失敗の直後にカード情報更新等で即座に決済が
  成功した際、`invoice.payment_failed`の配信が遅延し`invoice.payment_succeeded`
  (→`"active"`)より後に届くと、既に決済済みの契約者を`"past_due"`へ誤って書き換えて
  しまう。さらに`payment_failure_detected_at`も再設定されるため、`daily_scheduler.py`の
  督促リマインドが決済済みの契約者へ送られてしまう。
- 対称のケース(解約が先に確定した後、古い決済成功イベントが遅れて届く等)も同型で、
  `"canceled"`を`"active"`へ誤って書き戻してしまう。

course-set-pasha/aircon-pashaの既存バグ(`subscription_canceled_at`という真偽値寄りの
専用フィールド)と異なり、本ventureは4値enumの単一フィールドを複数ハンドラが共有して
上書きするため、「どのハンドラの書き込みが最後に反映されるべきか」を`event.created`
(Stripeイベントのトップレベルタイムスタンプ)で一元的に比較する必要がある。

## 3. 修正方針

`WorkshopStoreProtocol`に`get_subscription_status_event_time(workshop_id) -> Optional[
datetime]`/`set_subscription_status_event_time(workshop_id, event_time: datetime) -> None`
を追加し、`InMemoryWorkshopStore`にも実装した(`subscription_status`を最後に実際に反映
したイベントの`event.created`をworkshop_idごとに記録する、専用の別辞書)。

`stripe_webhook.py`に以下のヘルパーを新設した。

- `_event_time_from_created(event: dict) -> Optional[datetime]`: イベント全体の
  トップレベル`created`(Unixタイムスタンプ)を`datetime`へ変換する。欠落・非数値の場合は
  `None`(判定不能として常に適用、既存の`invoice.payment_failed`の`data_object.created`
  〈`payment_failure_detected_at`の検知時刻用、こちらは変更していない〉とは別の値)。
- `_is_stale_subscription_status_event(store, workshop_id, event_time)`: `event_time`が
  `None`、または`store`が新メソッド未対応(`getattr(..., None)`)、または記録済み
  event_timeが未設定の場合は「判定不能」として`False`(常に適用、後方互換)。今回の
  `event_time`が記録済みのevent_time「以下」であれば`True`(stale、同時刻は既に処理済み
  として扱い再適用しない)。
- `_record_subscription_status_event_time(store, workshop_id, event_time)`: `event_time`
  が`None`、または`store`が新メソッド未対応の場合は何もしない。

4つのハンドラ(`handle_checkout_session_completed`/`handle_customer_subscription_deleted`/
`handle_invoice_payment_failed`/`handle_invoice_payment_succeeded`)にそれぞれ
`event_time: Optional[datetime] = None`引数を追加し、`set_subscription_status`の直前で
stale判定を行う。stale時は`subscription_status`の書き込みだけでなく、各ハンドラが
`subscription_status`更新に付随して行っていた副作用(`clear_blocked_but_billing_owner_
notified_at`・`payment_failure_detected_at`の設定/クリア・LINE通知送信)もまとめてスキップ
する(course-set-pasha/aircon-pashaの`mark_deletion_candidate_on_subscription_deleted()`と
同じ「stale全体スキップ」方針。仮に状態更新だけをスキップして通知だけ送ると、実際の契約
状態と矛盾する通知〈例: 決済成功済みなのに「決済に失敗しました」〉を送ってしまうため)。
各ハンドラの戻り値dataclassに`stale: bool = False`を追加し、呼び出し元がスキップの発生を
観測できるようにした。

`receive_stripe_webhook()`は受信したイベント全体から`_event_time_from_created(event)`で
`event_time`を一度だけ算出し、対応する4イベント種別のハンドラ呼び出しへそのまま渡す
(`customer.subscription.updated`は`subscription_status`を変更しないため対象外)。

## 4. スコープ外

- 本ガードはkura-pasha単体への適用に留める。line-reservation-aiも`subscription_status`
  列挙型方式(aircon-pashaフェーズ280確認済み)のため同種の検討が必要だが、次回以降の
  横展開候補として残す。
- `customer.subscription.updated`の`cancel_at_period_end`前後比較(解約予約受理・取り消し
  通知)自体には本ガードを適用していない(`subscription_status`を変更しないイベントの
  ため、course-set-pasha/aircon-pashaが`updated`イベントを対象外にしたのと同じスコープ)。
- `workshop_linking.py`の`resolve_linking_code()`(新規workshop作成時の`subscription_
  status="trialing"`初期設定)は既存契約のイベント適用ではないため対象外。

## 5. テスト

`test_stripe_webhook.py`に7件のテスト関数を追加(`test_checkout_completed_skips_when_
event_time_not_after_recorded`・`test_checkout_completed_applies_when_event_time_missing`
・`test_deleted_skips_when_reactivated_after_stale_deleted_arrives_late`〈ケースA〉・
`test_deleted_applies_when_event_time_newer_than_recorded`〈正常順序の回帰確認〉・
`test_deleted_applies_unconditionally_when_store_lacks_event_time_methods`〈store未対応
時の後方互換確認〉・`test_invoice_failed_skips_when_event_time_older_than_recorded`
〈ケースB〉・`test_invoice_succeeded_skips_when_event_time_older_than_recorded`〈対称
ケースの確認〉)。`test_stripe_webhook.py`単体のcheck()呼び出しは142件→159件(+17)。
venture全体は`python3 prototype/run_all_tests.py`(全16ファイルOK)・schema検証32件
(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: line-reservation-aiへの同種ガードの横展開、または他venture・アイデア領域の
前進。
