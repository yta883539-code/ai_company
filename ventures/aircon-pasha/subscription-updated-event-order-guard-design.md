# customer.subscription.updated配信順序保証ガード設計

course-set-pashaフェーズ267・kura-pashaフェーズ198(2026-09-28 21:00 UTC台の定例更新)が、
`customer.subscription.updated`ハンドラに配信順序入れ替わりガードが一度も実装されて
いなかったことを発見・是正した際、両venture共に「他venture(aircon-pasha・
line-reservation-ai)の`customer.subscription.updated`相当ハンドラに同種のガード欠落が
残っていないかの横断確認」を次回候補として申し送っていた。本フェーズ(286、2026-09-28
23:00 UTC台の定例更新)でaircon-pasha自身を点検したところ、同型の欠落が存在することを
確認し是正した記録。

## 1. 検討したシナリオ

`stripe_dispatch.py`の`customer.subscription.deleted`/`.created`分岐(フェーズ280)・
`invoice.payment_failed`/`invoice.payment_succeeded`分岐(フェーズ281)はいずれも
`event_time`ベースの配信順序入れ替わりガード(stale-eventガード)を持つ一方、
`customer.subscription.updated`分岐(`_SUBSCRIPTION_UPDATED`)にはこのガードが一度も
実装されていなかった。

Stripeカスタマーポータル経由で短期間に複数回プラン変更が行われた場合、または
`cancel_at_period_end`が複数回連続で変化する`customer.subscription.updated`が発生した
場合、Stripeの「at least once」配信・非同期配送により後発のイベントが先に、先発の
イベントが後から遅延配信されるケースが理論上あり得る。この場合、従来コードでは
無条件で最新の`data_object`を反映してしまうため、以下3点が影響を受ける。

- `plan_store`指定時の`sync_current_plan_on_subscription_event()`(`current_plan_id`
  同期): 既に新しいイベントで確定済みのプランを、遅延配信された古いイベントの値で
  誤って上書きしてしまう。
- `cancellation_push_client`指定時の`handle_subscription_cancellation_update()`
  (解約予約受理・解約取り消し通知): 遅延配信された古いイベントの`previous_attributes`
  と現在の状態を比較してしまうと、既に解約取り消し済み(または解約予約確定済み)の
  契約者へ矛盾した通知を誤って送信するおそれがある。
- `status`が`_REACTIVATED_STATUSES`(active/trialing)の場合の削除候補クリア
  (`clear_deletion_candidate_on_subscription_reactivated()`): これ自体は冪等な操作
  だが、古いイベント由来の実行は不要な副作用であり、他フィールドと合わせて「丸ごと
  スキップ」対象に含める(course-set-pasha/kura-pashaと同じ方針)。

## 2. 対応

`UserProfileStoreProtocol`(user_id_linking.py)に`get_subscription_updated_event_time()`/
`set_subscription_updated_event_time()`(`UserProfile.subscription_updated_event_time`
フィールド、既存の`customer.subscription.deleted`/`.created`用`subscription_state_event_
time`とは独立)を新設し、`InMemoryUserProfileStore`にも実装した。`stripe_dispatch.py`に
`_is_stale_subscription_updated_event()`/`_record_subscription_updated_event_time()`を
追加し(`_is_stale_subscription_state_event()`と同じ`hasattr`後方互換方針)、
`_SUBSCRIPTION_UPDATED`分岐の先頭でstale判定を行い、staleの場合はreactivated状態
クリア・plan同期・解約予約受理/取り消し通知のいずれも行わず`return`する「丸ごとスキップ」
方針を採用した(他ハンドラと同じ考え方)。非staleの場合は分岐の最後で`event_time`を記録
する。

`event_time`は`event.get("created")`から算出する(既存の`_SUBSCRIPTION_DELETED`/
`_SUBSCRIPTION_CREATED`分岐と同じ方式)。`created`が数値でない/存在しない場合、
`payment_store`が未指定、または`payment_store`が対応メソッドを持たない場合は判定不能
として従来通り無条件適用する(既存の他ガードと同じ後方互換方針)。

再リンク時(`relink`相当の内部コピー処理)の既存プロフィールからのフィールド引き継ぎにも
`subscription_updated_event_time`を追加し、`subscription_state_event_time`・
`payment_failure_state_event_time`と同じ扱いとした。

## 3. スコープ外

- `customer.subscription.updated`同士の重複配信(同一event_id)への対応は本ガードの
  対象外(他venture同様、別途event_id単位の重複排除があれば別レイヤーで扱う想定)。
- `subscription_status`自体は`_SUBSCRIPTION_DELETED`/`_SUBSCRIPTION_CREATED`で扱う
  ため、`subscription_state_event_time`とは独立した専用フィールドとした(共有した場合、
  `.updated`同士の順序入れ替わりを正しく検知できないため、kura-pashaフェーズ198と
  同じ理由)。

## 4. テスト

`test_stripe_dispatch.py`(`DispatchSubscriptionUpdatedTest`)に4件追加した(stale時に
plan同期・reactivated状態クリアの双方がスキップされることの確認、非stale時に適用され
`event_time`が記録されることの確認、`payment_store`未指定時の無条件適用の確認)。

venture全体`python3 -m unittest discover -s prototype -p "test_*.py"`(653件、649→653)・
schema検証`python3 schema/validate_test_cases.py`(25件、変更なし)いずれもパスを確認した。

line-reservation-aiの`customer.subscription.updated`相当ハンドラに同種のガード欠落が
残っていないかの横断確認は、次回以降の棚卸し候補として申し送る(本フェーズはaircon-pasha
自身の是正のみを対象とした)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: line-reservation-aiの`customer.subscription.updated`ハンドラに同種のガード
欠落がないかの横断確認。または他venture・アイデア領域の前進、launch-readiness-
checklist.mdとpending-approval.mdの記載齟齬の定期棚卸し。
