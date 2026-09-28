# checkout.session.completedイベント順序保証ガード設計

subscription-event-order-guard-design.md(フェーズ続き282〜283)・payment-failure-
detected-at-event-order-guard-design.md(フェーズ続き284)が「次回候補」として残していた
「`handle_checkout_session_completed()`にも同種の順序入れ替わりの影響があるかの検討」
に対応した記録。

## 1. 検討したシナリオ

`handle_checkout_session_completed()`(store_profile_store.py)は`checkout.session.
completed`受信のたびに`stripe_customer_id`・`plan`を無条件に上書きする。同一user_idが
短期間に2回以上Checkout Sessionを完了させるケース(例: 一度解約後に別プランで即座に
再購入した場合、あるいはStripe側の再送により最初のイベントが大幅に遅延配信された場合)で、
配信順序が入れ替わると、新しいCheckout Sessionのcustomer_id・planを古いイベントの値で
誤って上書きしてしまう欠落が理論上存在することを確認した。これはsubscription-event-
order-guard-design.mdの「ケースA/B」と同種の、Stripeの「イベントは発生順に届くとは
限らない」という前提を考慮していなかった欠落である。

customer_idが実運用上ほぼ変化しない(同一Stripe顧客であれば通常同じcustomer_idが
再利用される、resolve_existing_stripe_customer_id()参照)ため実害の頻度は低いと
見積もられるが、planは「解約後に別プランで再契約」のような正当なケースで実際に
変わり得るため、古いplanでの誤上書きは月間予約件数上限(PLAN_MONTHLY_BOOKING_LIMITS)を
実際の契約と異なる値にしてしまう実害がある。

## 2. 対応

`StoreProfileStoreProtocol`に`get_checkout_session_completed_event_time()`/
`set_checkout_session_completed_event_time()`(user_idキー)を追加した。
`handle_checkout_session_completed()`に`event_time: Optional[datetime] = None`引数を
追加し、記録済みの`event_time`以下(同時刻含む)の場合はstripe_customer_id・plan
いずれの書き込みも行わず`CheckoutSessionLinkResult(stale=True)`を返す「丸ごとスキップ」
方針とした(customer_idだけ古いまま・planだけ新しいという中途半端な状態を避けるため、
subscription側と同じ考え方)。適用時は`event_time`をそのまま記録する。

`event_time`省略時、または記録済みの時刻が未設定(本ガード導入前からの既存店舗等)の
場合はチェックを行わず従来通り無条件適用する(後方互換)。

`stripe_webhook_entry_point.py`の`receive_stripe_webhook()`は既に`_event_time_from_
created()`で`event_time`を解決済み(フェーズ続き283)のため、`handle_checkout_session_
completed()`呼び出しに`event_time=event_time`を渡す配線を追加するのみで済んだ。

## 3. スコープ外

- `checkout.session.completed`同士の重複配信(同一event_id)は既に`event_id_store`
  による`route.duplicate`判定で別途扱われており、本ガードは同一user_idに対する
  「複数の異なるCheckout Session完了イベント」間の順序入れ替わりのみを対象とする。
- `resolve_existing_stripe_customer_id()`側(Checkout Session作成時に既存customer_idを
  再利用するかどうかの判定)は本フェーズの対象外。

## 4. テスト

`test_store_profile_store.py`に`HandleCheckoutSessionCompletedEventOrderGuardTest`
(5件: event_time省略時の無条件適用・記録なし時の無条件適用・正常順序の適用・
stale時のスキップ・同時刻はstale扱いの確認)、`test_stripe_webhook_entry_point.py`に
統合エントリポイント経由でstale eventが新しいcustomer_idを上書きしないことを確認する
1件を追加(計6件)。

venture全体`python3 -m unittest discover -s prototype -p "test_*.py"`(891件、
885→891)・schema検証`python3 schema/validate_test_cases.py`(28件)いずれもパスを
確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: 他venture・アイデア領域の前進。
