# checkout.session.completed(plan書き込み)配信順序保証ガード設計

course-set-pashaフェーズ265(checkout-session-completed-event-order-guard-design.md、
元はline-reservation-aiフェーズ続き285からの横展開)が`stripe_webhook.
handle_checkout_session_completed()`の`stripe_customer_id`・`plan`双方の無条件上書きに
event_timeベースの配信順序入れ替わりガードを追加した一方、kura-pasha自身にはこの横展開が
未反映のまま残っていたため、フェーズ197(2026-09-28 12:00 UTC台の定例更新)で是正した記録。

## 1. 検討したシナリオ

kura-pashaの`handle_checkout_session_completed()`は`checkout.session.completed`受信の
たびに`metadata.plan_id`が既知の値であれば`workshop_store.set_plan()`で無条件に上書き
する。course-set-pashaと同じく、同一workshop_idが短期間に2回以上Checkout Sessionを
完了させるケース(例: 一度プランを変更した直後に、Stripe側の再送等で最初のイベントが
大幅に遅延配信された場合)で配信順序が入れ替わると、新しいCheckout Sessionで反映済みの
planを古いイベントの値で誤って上書きしてしまう欠落が理論上存在する
(subscription-status-event-order-guard-design.mdの「ケースA/B」と同種)。

なお`stripe_customer_id`の書き込みは、本venture既存コードで既に`workshop_store.
get_stripe_customer_id(workshop_id) is None`による「一度きり書き込み」(未設定時のみ
書き込み、以降は上書きしない)で保護されており、course-set-pasha側の無条件上書きとは
実装が異なるため、配信順序が入れ替わってもstripe_customer_idが誤って古い値へ戻ることは
ない。よって本ガードは`plan`の書き込みのみを対象とする(course-set-pasha・
line-reservation-ai側は両方を「丸ごとスキップ」する設計だが、kura-pashaはstripe_
customer_id側の対策が既に別方式で完了しているため対象外とする差異がある)。

`plan`は「多人数プランへの変更」等、実運用上変わり得るフィールドであり、古いplanでの
誤上書きは月間コースセット数上限等(usage_counter_workshop.pyの利用制限)を実際の契約と
異なる値にしてしまう実害がある。

## 2. 対応

`WorkshopStoreProtocol`(usage_counter_workshop.py)に
`get_checkout_session_completed_event_time()`/`set_checkout_session_completed_event_
time()`(workshop_idキー、既存の`get/set_subscription_status_event_time`と同じ設計)を
追加した。`stripe_webhook.py`に`_is_stale_checkout_session_completed_event()`/
`_record_checkout_session_completed_event_time()`を新設し、`handle_checkout_session_
completed()`の`plan`書き込み分岐(`plan_id`が`VALID_PLAN_IDS`に含まれる場合)へ、記録済み
の`event_time`以下(同時刻含む)ならスキップする「丸ごとスキップ」方針のガードを配線した。
適用成功時のみ`checkout_session_completed_event_time`を更新する(subscription_status側の
`_record_subscription_status_event_time()`と同じ、スキップ時は記録を更新しない)。

`event_time`省略時、`store`が対応メソッドを持たない場合(hasattr未対応の簡易スタブ等)、
または記録済みの時刻が未設定(本ガード導入前からの既存workshop等)の場合はチェックを
行わず従来通り無条件適用する(既存の他ガードと同じ後方互換方針)。

`receive_stripe_webhook()`から`handle_checkout_session_completed()`へは、既に
`subscription_status`ガード用に算出済みの`event_time`(`_event_time_from_created()`)を
そのまま渡す配線となっているため、呼び出し側(`receive_stripe_webhook()`)の変更は不要
だった。

## 3. スコープ外

- `stripe_customer_id`の書き込みは前述の通り既存の一度きり書き込みで保護済みのため、
  本ガードの対象に含めない。
- `checkout.session.completed`同士の重複配信(同一event_id)は既に`event_id_store`による
  `route.duplicate`判定で別途扱われており、本ガードは同一workshop_idに対する「複数の
  異なるCheckout Session完了イベント」間の順序入れ替わりのみを対象とする。

## 4. テスト

`test_stripe_webhook.py`に6件追加した(event_time省略時の無条件適用・記録なし時の
無条件適用・正常順序の適用と記録更新確認・stale時のスキップ・同時刻はstale扱いの
確認・store未対応時の無条件適用)。

venture全体`python3 prototype/run_all_tests.py`(16ファイルOK、
`test_stripe_webhook.py`単体は166→172件)・schema検証`python3
schema/validate_test_cases.py`(32件、変更なし)いずれもパスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: 他venture・アイデア領域の前進、またはlaunch-readiness-checklist.mdと
pending-approval.mdの記載齟齬の定期棚卸し。
