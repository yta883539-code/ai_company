# subscription-plan-sync-design.md

フェーズ続き220(2026-09-12 18:00 UTC)。kura-pashaフェーズ93が「line-reservation-aiへの
横展開要否は次回以降の棚卸し候補として残す(店舗単位で複数プランを持つか自体を要確認)」と
申し送っていた件の棚卸しと対応。

## 1. 確認結果

pricing-plan.mdの通り、本ventureは店舗単位の契約でスタータープラン/スタンダードプラン/
プロプランの3プランを持つ(横展開の前提が成立)。`store_profile_store.py`の`get_plan()`/
`set_plan()`(フェーズ続き181)が契約プランの保持先であり、`resolve_monthly_booking_limit()`
(フェーズ続き182)がこの値からmonthly-booking-limit-notification-design.mdの通知しきい値を
決定する。

`set_plan()`を呼ぶのは`store_profile_store.handle_checkout_session_completed()`
(`checkout.session.completed`受信時)のみで、`customer.subscription.updated`
(Stripeカスタマーポータル経由のプラン変更)受信時に`plan`を更新する処理は一度も
実装されていなかった。aircon-pasha/kura-pashaで発見・解消された配線漏れと同種のギャップ。

## 2. 実害の範囲

monthly-booking-limit-notification-design.md 56行目の通り、この機能は「通知のみ」で
予約自体をブロックしない設計のため、実害はプラン変更後も旧プランの通知しきい値が
使われ続けること(オーナーへの通知タイミングのズレ)にとどまる。

## 3. 対応

`prototype/subscription_plan_sync.py`を新設した。

- `resolve_plan_from_subscription(data_object)`: `items.data[0].price.lookup_key`から
  `LOOKUP_KEY_TO_PLAN`(`line_reservation_ai_starter`/`_standard`/`_pro` →
  「スタータープラン」/「スタンダードプラン」/「プロプラン」)で解決する。解決できない
  場合は常に`None`(呼び出し元は既存値を維持)。
- `sync_plan_on_subscription_event(store, store_id, data_object)`: 解決できたplanが
  既存の`get_plan(store_id)`と異なる場合のみ`set_plan()`を呼ぶ(差分チェックは
  aircon-pashaフェーズ208・kura-pashaフェーズ93の教訓を踏まえ最初から組み込んだ)。
- `stripe_webhook_entry_point.py`の`receive_stripe_webhook()`に`store_profile_store`
  引数(`PlanStoreProtocol`)を追加し、`EVENT_CUSTOMER_SUBSCRIPTION_UPDATED`分岐の
  冒頭(`cancellation_store`/`push_client`の要否チェックより前)で呼び出す。解約通知の
  要否・成否とは独立に同期する(aircon-pasha/kura-pashaと同じ位置づけ)。
  `get_stripe_webhook_runtime_dependencies()`の返り値にも`store_profile_store`を追加した。

## 4. 本venture固有の差異(aircon-pasha/kura-pashaとの比較)

- `checkout_session.py`の`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`は既にPrice IDを直接
  指定する仕組みを持つが、これは本モジュールが使う`lookup_key`とは独立(実アカウント
  接続後、同一Priceに両方を設定すればよい)。
- `customer.subscription.deleted`受信時に`plan`を`None`へ戻す処理
  (aircon-pashaの`clear_current_plan_on_subscription_deleted()`相当)は実装しない。
  `plan`が`None`になっても`resolve_monthly_booking_limit()`は「通知しきい値機能を
  無効化する」だけで、予約受付・会話応答自体は独立した`suspension_reason`
  (blocked-but-billing-detection-design.md)側で制御されるため、解約後に`plan`を
  残しても「無制限扱いでサービスが使い続けられる」実害が生じない。次回契約時は
  `checkout.session.completed`が新たなplanを設定し直す。

## 5. 動作確認

- `test_subscription_plan_sync.py`(新設、16件): lookup_key解決の網羅・差分チェックに
  よる書き込み省略/再書き込みを確認。
- `test_stripe_webhook_entry_point.py`(3件追加): `store_profile_store`指定時に
  `EVENT_CUSTOMER_SUBSCRIPTION_UPDATED`から実際にplanが同期されること、
  `cancellation_store`/`push_client`未指定でも同期は行われること、
  `store_profile_store`省略時はエラーにならずスキップされることを確認。
- `python3 -m unittest discover -s prototype -p "test_*.py"`: 796件全件パス
  (既存776件→796件、20件追加)。
- `python3 schema/validate_test_cases.py`: 27件全件パス(変更前と同じ結果、
  schema/booking_output.schema.jsonへの影響は無し。`plan`はLLM構造化出力に
  登場しないフィールド)。

## 6. 次の課題

- 実Stripeアカウント接続後、Price作成時に`line_reservation_ai_starter`/`_standard`/
  `_pro`のlookup_keyを実際に設定する作業自体はオーナー承認待ちの範囲
  (pending-approval.md参照)であり、本フェーズでは行っていない。
- aircon-pasha/course-set-pasha/kura-pashaの3venture・本ventureとも同種のギャップは
  解消済みとなったため、他venture・アイデア領域の前進を優先候補とする。
