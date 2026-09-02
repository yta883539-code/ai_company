# stripe_customer_id → store_id 逆引き設計(フェーズ続き160)

作成日: 2026-08-31(フェーズ続き160)

stripe-webhook-event-dispatch-design.md(フェーズ続き159)5節「残課題」に残っていた、
`route_stripe_event()`が`invoice.payment_succeeded`/`invoice.payment_failed`受信時に
必要とする`resolve_store_id_by_customer`(`customer → store_id`逆引き)の実装本体を設計・
実装する。course-set-pasha/stripe-customer-id-linking-design.md(フェーズ97)と同じ課題設定
だが、本ventureは`route_stripe_event()`がイベント種別判定・store_id解決のみを行う薄い関数
(実ハンドラ呼び出し・Firestore読み書きは含まない)という前提が既に確定しているため、本設計も
その前提に合わせて逆引きの提供のみに絞る。

## 1. 前提・方針

- `store_profile_store.py`(checkout-initiation-flow-design.md「残課題」で新設済み)は、
  `checkout.session.completed`受信時に`handle_checkout_session_completed()`経由で
  `user_id → stripe_customer_id`の順引きを既に書き込んでいる(2026-08-28実装済み)。
  本ventureは`user_id`をそのまま`store_id`として扱う(stripe-webhook-event-dispatch-
  design.md 2節: `client_reference_id`に店舗の`user_id`を直接設定する設計のため)ので、
  この順引きインデックスに逆引き用の辞書を追加するだけで`customer → store_id`変換が完成する。
- course-set-pashaは`UserProfileStoreProtocol`に`get_user_id_by_stripe_customer_id`を追加
  したが、本ventureでは`user_id`=`store_id`という呼称の一貫性を保つため、メソッド名は
  `get_store_id_by_stripe_customer_id`とする。

**訂正(フェーズ続き169、store-id-resolution-and-owner-identity-design.md参照)**: 上記
「`user_id`をそのまま`store_id`として扱う」の`user_id`は、店舗オーナー個人のLINE user_id
ではなく`store_id`(=`destination`)を指す(checkout-initiation-flow-design.md 9節・
stripe-webhook-event-dispatch-design.md 2節の訂正と同じ)。`store_profile_store.py`の
各メソッドが引数名`user_id`をキーとして扱う実装自体は変更不要で、渡す値の由来のみが
訂正される。本節・本ドキュメントの結論(`get_store_id_by_stripe_customer_id`という
メソッド名・データモデル)への影響は無い。

## 2. データモデル

- `StoreProfileStoreProtocol`に`get_store_id_by_stripe_customer_id(stripe_customer_id) ->
  Optional[str]`を追加する(実Firestoreでは`stripe_customer_index/{stripe_customer_id} =
  {store_id}`という別コレクションでの逆引き用インデックスを想定。course-set-pashaの設計と
  同じ構造)。
- `InMemoryStoreProfileStore`は`_store_ids_by_stripe_customer_id: dict[str, str]`を追加で
  保持し、`set_stripe_customer_id()`が順引き・逆引き両方の辞書を同時に更新する。
- 同一`user_id`(store_id)に別の`stripe_customer_id`が再紐付けされるケース(通常は
  `resolve_existing_stripe_customer_id()`が既存customerを再利用するため起こらない想定だが、
  防御的に対応)では、古い`stripe_customer_id`の逆引きエントリを削除してから新しいエントリを
  書き込む。これを怠ると、古い`stripe_customer_id`宛のWebhookイベント(Stripe側の遅延配送等)
  が別の店舗の`store_id`に誤って解決されるリスクがあるため。

## 3. `route_stripe_event()`との結線

- `make_resolve_store_id_by_customer(store) -> Callable[[str], Optional[str]]`を
  `store_profile_store.py`に新設し、`store.get_store_id_by_stripe_customer_id`をそのまま
  返す薄いファクトリとする(course-set-pashaの`make_resolve_user_id()`と同じ考え方)。
- 実際のCloud Functionsエントリポイント(design「残課題」に残る次の課題)は、起動時に
  `resolve_store_id_by_customer=make_resolve_store_id_by_customer(store_profile_store)`を
  `route_stripe_event()`へ渡すだけで結線が完成する。

## 4. 動作確認

- `test_store_profile_store.py`に`GetStoreIdByStripeCustomerIdTest`(5件: 未設定時None、
  順引き後の逆引き、同一イベント再送時の冪等性、同一user_idへの再紐付け時の古いエントリ除去、
  複数customerの分離)・`MakeResolveStoreIdByCustomerTest`(2件)・
  `HandleCheckoutSessionCompletedTest`への追加1件(`handle_checkout_session_completed()`が
  逆引きも同時に整備することの確認)を追加した。
- `test_stripe_webhook.py`に`RouteStripeEventWithStoreProfileStoreWiringTest`(3件:
  `checkout.session.completed`受信前は`invoice.payment_succeeded`が未解決のままであること、
  受信後は`invoice.payment_succeeded`/`invoice.payment_failed`いずれも実際に`store_id`を
  解決できること)を追加し、`store_profile_store.py`→`stripe_webhook.py`の結線が実際に
  機能することを確認した。
- venture全体461件全件パス(`python3 -m unittest discover -s prototype -p "test_*.py"`、
  既存450件+新規11件)・`schema/validate_test_cases.py`25件全件パスを確認した。

## 残課題

- 実際のCloud Functionsエントリポイント(`receive_stripe_webhook(request)`相当。
  `verify_stripe_signature()`→JSONパース→`route_stripe_event()`→store_idを使った実
  Firestore読み込み→該当ハンドラ呼び出し→書き戻し、の一連の配線)は、実Firestore接続
  (オーナー承認待ち)が前提のため引き続き次回以降の課題として残る(stripe-webhook-event-
  dispatch-design.md 5節から持ち越し、本フェーズでは解消せず)。
- 実Stripe Webhookエンドポイントのデプロイ・`webhook_secret`の取得・保管はいずれも
  オーナー承認待ちの範囲(pending-approval.md参照)。
