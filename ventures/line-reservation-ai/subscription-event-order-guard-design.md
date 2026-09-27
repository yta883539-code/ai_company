# サブスクリプションイベント順序保証ガード設計

kura-pashaのsubscription-status-event-order-guard-design.md(フェーズ194)の横展開。
aircon-pashaフェーズ280が「次回候補」に残していた「subscription_status列挙型方式
(kura-pasha・line-reservation-ai共通)におけるStripe Webhook配信順序入れ替わり」の
影響検討を、本venture固有のアーキテクチャ(suspension_reason文字列 + 用途別ハンドラ
モジュール分割)に沿って検討し、対応した記録。

## 1. 前提の訂正

aircon-pashaフェーズ280は「kura-pasha・line-reservation-ai共通のsubscription_status
列挙型方式」としていたが、本venture(line-reservation-ai)はkura-pashaのような単一の
`subscription_status`列挙型ではなく、`suspension_reason`(None/"trial_unselected"/
"payment_failed"/"payment_suspended"/"cancelled")という別方式を採る。そのため
kura-pashaのガード実装をそのまま横展開することはできず、本venture独自の設計が必要
だった。

## 2. 発見した欠落(kura-pashaの「ケースA」と対称)

`cloud_function_subscription_cancelled_webhook.handle_subscription_deleted()`
(`customer.subscription.deleted`受信)と`cloud_function_subscription_activated_
webhook.handle_subscription_activated()`(`subscription_activated`受信、再契約時にも
呼ばれる)は、いずれも`suspension_reason`を無条件に書き換えていた。

- **ケースA(解約直後の即再契約)**: 解約(`customer.subscription.deleted`)発生後、
  オーナーが即座に再契約すると`subscription_activated`が発行され
  `suspension_reason`がNoneに戻る。ここで解約時の`customer.subscription.deleted`が
  何らかの理由で遅延配信されると、有効な契約を誤って`"cancelled"`へ書き換え、
  「ご契約が終了しました」という事実と異なる通知を送ってしまう。
- **ケースB(ケースAと対称)**: 逆に、契約が解約確定した後、それより前に発生していた
  (が遅延配信された)`subscription_activated`が届くと、既に`"cancelled"`へ書き換え
  済みの状態を誤って解除し、終了済みの契約に「ご登録ありがとうございます」の案内を
  送ってしまう。

いずれも実際に店舗が混乱する通知を送ってしまう欠落であり、kura-pashaの発見と同種。

## 3. 対応

`StoreSubscriptionState`(両ファイルにそれぞれ定義された同型のdataclass。既存の
「同じFirestoreフィールドを指す別クラス」という重複は本対応のスコープ外)に
`last_subscription_event_time: datetime | None = None`を追加した。`handle_subscription_
deleted()`・`handle_subscription_activated()`双方に`event_time: Optional[datetime] =
None`引数を追加し、`event_time <= state.last_subscription_event_time`の場合は
状態更新・通知のいずれも行わず`OUTCOME_STALE_EVENT`(`stale=True`)を返して丸ごと
スキップする(kura-pashaと同じ「stale全体スキップ」方針。状態だけスキップして通知だけ
送ると実際の契約状態と矛盾する通知を送ってしまうため)。適用時は
`last_subscription_event_time`をその`event_time`で更新する。

`event_time`省略時、または`state.last_subscription_event_time`が未設定(`None`、
本ガード導入前からの既存店舗等)の場合はチェックを行わず従来通り無条件適用する
(後方互換)。

`route_stripe_event()`(stripe_webhook.py)は現状これらのハンドラを呼び出す統合
エントリポイントを持たない(design「残課題」のとおり別途の課題)ため、`event.created`
から`event_time`を算出して各ハンドラへ渡す配線自体は、統合エントリポイント実装時の
課題として残る。

## 4. スコープ外

- `handle_subscription_updated()`(`cancel_at_period_end`変化)は`suspension_reason`を
  変更しないため対象外(kura-pashaが`customer.subscription.updated`を対象外とした
  のと同じ理由)。
- `cloud_function_payment_webhook.py`の`handle_payment_succeeded()`/
  `handle_payment_failed()`との間の順序入れ替わり(dunning側)は、`suspension_reason`
  が`"payment_failed"`/`"payment_suspended"`のときは両モジュールとも自分の担当外として
  触れない設計(既存の役割分担)のため直接の重複書き換えは起きないが、`payment_failure_
  detected_at`側の順序入れ替わり自体は未検討であり、次回以降の課題として残す。

## 5. テスト

`test_cloud_function_subscription_cancelled_webhook.py`に3件
(`test_applies_when_event_time_newer_than_recorded`〈正常順序の回帰確認〉・
`test_skips_when_deleted_event_is_stale_after_reactivation`〈ケースA〉・
`test_applies_unconditionally_when_event_time_omitted`)、さらに
`test_applies_unconditionally_when_store_lacks_recorded_event_time`
(store未対応時の後方互換確認)を追加(計4件)。`test_cloud_function_subscription_
activated_webhook.py`に3件(同様の正常順序確認・
`test_skips_when_reactivation_event_is_stale_after_later_cancellation`〈ケースB〉・
後方互換確認)を追加。

venture全体`python3 -m unittest discover -s prototype -p "test_*.py"`(877件、
+7)・schema検証`python3 schema/validate_test_cases.py`(28件)いずれもパスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: `route_stripe_event()`から各ハンドラへの統合エントリポイント配線実装時に
`event_time`を実際に渡す配線、または`payment_failure_detected_at`側の順序入れ替わり
検討、あるいは他venture・アイデア領域の前進。
