# checkout.session.completed 配信順序入れ替わりガード設計(フェーズ287)

## 1. 経緯

course-set-pashaフェーズ265(checkout-session-completed-event-order-guard-design.md)・
kura-pashaフェーズ197(checkout-session-completed-plan-event-order-guard-design.md)が
それぞれ自venture固有の対象フィールドに「配信順序入れ替わりガード」(Stripe Webhookは
`at least once`配信かつ配信順序が保証されないため、`event.created`ベースで古いイベントの
反映をスキップする方式)を横展開していた。本venture(aircon-pasha)の
`stripe_webhook.handle_checkout_session_completed()`にはこのガードが未反映のまま
残っていたことが判明したため、本フェーズで是正した。

kura-pashaの`stripe_customer_id`は「未設定時のみ書き込み」(一度きり方式)で既に
配信順序に依存しない形で保護されていたためガード対象外とされていたが、本venture
(aircon-pasha)の`stripe_customer_id`書き込みはそのような一度きりガードを持たず、
`checkout.session.completed`受信のたびに無条件で上書きしていた。同一利用者が複数回
Checkout Sessionを作成した場合(再契約等)に古いイベントが遅延配信されると、より新しい
イベントで書き込み済みの`stripe_customer_id`を古い値へ巻き戻してしまい、以降の
Webhook(`customer.subscription.*`等)が`get_user_id_by_stripe_customer_id()`で
正しく逆引きできなくなるおそれがあった。

## 2. 対応内容

- `UserProfile`に`checkout_session_completed_event_time`フィールドを追加
  (`subscription_state_event_time`等と同じ位置づけ)。
- `user_id_linking.py`の`UserProfileStoreProtocol`/`InMemoryUserProfileStore`に
  `get_checkout_session_completed_event_time()`/`set_checkout_session_completed_event_time()`を追加。
- `stripe_webhook.py`に`_is_stale_checkout_session_completed_event()`/
  `_record_checkout_session_completed_event_time()`を追加し、
  `handle_checkout_session_completed()`の`stripe_customer_id`書き込みをこの判定で
  ガードした(`upgraded_at`は「一度きり」判定のため対象外、従来通り)。
- `receive_stripe_webhook()`の`checkout.session.completed`分岐で、イベント全体の
  `created`(Unixタイムスタンプ)から`event_time`を算出し`handle_checkout_session_completed()`へ
  渡す配線を追加(`dispatch_stripe_event()`側の`_SUBSCRIPTION_CREATED`分岐等と同じ方式)。
- `event_time`省略時・store未対応・未記録時は従来通り無条件適用する後方互換を維持。

## 3. 検証

- `test_stripe_webhook.py`にテスト4件追加(stale判定でのスキップ・同時刻判定・
  `event_time`省略時の後方互換・staleでも`upgraded_at`は書き込まれることの確認)。
- `python3 -m unittest discover -s prototype -p "test_*.py"`: 650件パス。
- `python3 schema/validate_test_cases.py`: 25件パス。

## 4. スコープ外・残課題

- 他venture(course-set-pasha・kura-pasha・line-reservation-ai)は本フェーズ時点で
  対応済みであることを確認済み(横断確認完了)。
- 実Stripeアカウント接続はオーナー承認待ちのため未検証(InMemoryStubによる検証のみ)。
