# checkout.session.completedイベント順序保証ガード設計

subscription-event-out-of-order-guard-design.md(フェーズ261〜262)・
payment-failure-event-order-guard-design.md(フェーズ264)がcourse-set-pasha自身の
`customer.subscription.*`/dunning側に対応した一方、line-reservation-aiフェーズ続き285
(checkout-session-completed-event-order-guard-design.md)が同種のガードを
`handle_checkout_session_completed()`にも横展開していたのに対し、course-set-pasha側は
その元となった`stripe_webhook.handle_checkout_session_completed()`自身が未対応のまま
残っていたことが判明したため、今回是正した記録。

## 1. 検討したシナリオ

`handle_checkout_session_completed()`(stripe_webhook.py)は`checkout.session.
completed`受信のたびに`stripe_customer_id`・`plan`を無条件に上書きする。同一user_idが
短期間に2回以上Checkout Sessionを完了させるケース(例: 一度解約後に別プランで即座に
再購入した場合、あるいはStripe側の再送により最初のイベントが大幅に遅延配信された場合)で、
配信順序が入れ替わると、新しいCheckout Sessionのcustomer_id・planを古いイベントの値で
誤って上書きしてしまう欠落が理論上存在する。これはsubscription-event-out-of-order-
guard-design.mdの「ケースA/B」と同種の、Stripeの「イベントは発生順に届くとは限らない」
という前提を考慮していなかった欠落である。

customer_idが実運用上ほぼ変化しない(同一Stripe顧客であれば通常同じcustomer_idが
再利用される)ため実害の頻度は低いと見積もられるが、planは「解約後に別プランで再契約」の
ような正当なケースで実際に変わり得るため、古いplanでの誤上書きは月間コースセット数上限
(PLAN_MONTHLY_LIMITS)を実際の契約と異なる値にしてしまう実害がある。

## 2. 対応

`UserProfileStoreProtocol`(application_form_submission_flow.py)に
`get_checkout_session_completed_event_time()`/`set_checkout_session_completed_event_
time()`(user_idキー)を追加した。`handle_checkout_session_completed()`に
`event_time: Optional[datetime] = None`引数を追加し、記録済みの`event_time`以下
(同時刻含む)の場合はstripe_customer_id・planいずれの書き込みも行わず
`CheckoutSessionLinkResult(stale=True)`を返す「丸ごとスキップ」方針とした(customer_id
だけ古いまま・planだけ新しいという中途半端な状態を避けるため、subscription側・
line-reservation-ai側と同じ考え方)。`upgraded_at`の書き込みはstale時もそのまま行う
(`set_upgraded_at_if_unset()`は既存値があれば上書きしない設計のため、staleなイベントで
誤って有料転換前の状態に戻ることはない)。適用時は`event_time`をそのまま記録する。

`event_time`省略時、`store`が対応メソッドを持たない場合(`hasattr`未対応の簡易スタブ等)、
または記録済みの時刻が未設定(本ガード導入前からの既存ユーザー等)の場合はチェックを
行わず従来通り無条件適用する(後方互換)。

`receive_stripe_webhook()`の`checkout.session.completed`分岐で`parsed.get("created")`
から`event_time`を算出(他のcustomer.subscription.*分岐と同じ、共有ヘルパーは存在せず
各呼び出し箇所でインライン算出する既存の書き方に合わせた)し、
`handle_checkout_session_completed()`呼び出しに`event_time=checkout_event_time`を
渡す配線を追加した。

## 3. スコープ外

- `checkout.session.completed`同士の重複配信(同一event_id)は既に`event_id_store`
  による`route.duplicate`判定で別途扱われており、本ガードは同一user_idに対する
  「複数の異なるCheckout Session完了イベント」間の順序入れ替わりのみを対象とする。

## 4. テスト

`test_stripe_webhook.py`に`HandleCheckoutSessionCompletedEventOrderGuardTest`
(5件: event_time省略時の無条件適用・記録なし時の無条件適用・正常順序の適用・
stale時のスキップ・同時刻はstale扱いの確認)を追加した。

venture全体`python3 -m unittest discover -s prototype -p "test_*.py"`(682件、
677→682)・schema検証`python3 schema/validate_test_cases.py`(21件、変更なし)いずれも
パスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: 他venture・アイデア領域の前進。
