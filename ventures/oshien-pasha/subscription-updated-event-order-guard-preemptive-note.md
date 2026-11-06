# customer.subscription.updated 配信順序入れ替わりガード: 先行メモ(フェーズ88)

kura-pashaフェーズ282の横断棚卸し(subscription-updated-event-order-guard-design.md、
フェーズ198由来)で、他venture(aircon-pasha・course-set-pasha・line-reservation-ai・
kura-pasha自身・forklift-pasha)の`customer.subscription.updated`相当ハンドラにおける
配信順序入れ替わりガードの実装状況が横断確認された。kura-pashaフェーズ282の次回候補(3)を
受けて、本venture(oshien-pasha)についても同種の欠落がないかを確認した。

## 1. 現状確認

- 本venture側でStripeのサブスクリプション状態を更新する処理は
  `prototype/fan_pass_store.py`の`InMemoryFanPassStore.update_subscription_status()`
  のみであり、`internal_id`と`status`のみを受け取り`subscription_status`を無条件で
  上書きする(100〜106行目)。イベントのタイムスタンプ(`event.created`相当)を比較する
  パラメータ・ガード処理は存在しない。
- ただし本venture側には、Stripe Webhookを受信して`update_subscription_status()`を
  呼び出すCloud Function/Webhookエントリポイントの設計・実装自体がまだ存在しない
  (`fan-pass-canceled-access-block-design.md`28行目で言及される「webhook」は
  LINE Webhook受信の話であり、Stripe Webhookの受信フローはschema/prototypeの
  いずれにも未着手)。
- したがって、他5venture(aircon-pasha・course-set-pasha・line-reservation-ai・
  kura-pasha・forklift-pasha)で見つかった「Webhookハンドラは実装済みだがevent_time
  ベースのガードが欠落している」という状態とは異なり、本ventureはまだWebhookハンドラ
  自体が存在しないため、現時点で修正すべき「欠落」は存在しない(対象外)。

## 2. 先行メモとして残す理由

本venture側で将来Stripe Webhookエントリポイントを実装する際に、他5venture同様の
ガード欠落を新たに生んでしまうことを防ぐため、採用すべきパターンを先行して記録する。

## 3. 採用すべきガードパターン(他venture実装からの踏襲)

他ventureの`subscription-updated-event-order-guard-design.md`系ドキュメントが
共通して採用している方針は以下の通り。

1. `FanPass`ドキュメントに、直近で適用済みのStripeイベント時刻を保持するフィールド
   (例: `subscriptionStatusUpdatedAt`、Stripeの`event.created`〈Unixエポック秒〉を
   そのまま保持)を追加する。
2. `update_subscription_status()`相当のメソッドに`event_time: int`引数を追加し、
   `event_time <= 既存のsubscriptionStatusUpdatedAt`の場合は更新をスキップする
   (遅延配信された古いイベントによる上書きを防ぐ)。
3. 初回(`subscriptionStatusUpdatedAt`が未設定)の場合は無条件に適用する。

## 4. 残課題・次回候補

- 本メモはStripe Webhookエントリポイント自体の設計着手を意味しない。
  `venture_matcher.py`のCloud Functions実エントリポイント結線(README.mdフェーズ87
  次回候補(1))が優先され、Stripe決済・Webhook受信フローの設計自体はまだ本venture内で
  着手されていない(pricing-plan.md・payment-method-design.md時点では都度プラン
  〈mode=payment〉が主軸で、月額フリーパス〈mode=subscription〉のWebhook受信設計は
  今後の課題として残っている)。
- 本venture側でStripe Webhookエントリポイント(course-set-pasha等の
  `webhook-event-dispatch-design.md`相当)を設計する段階に至った際に、本メモの
  3節のパターンを`FanPassStore`の`update_subscription_status()`シグネチャに
  反映することを次回候補とする。
- event-komiguai-pashaについてもkura-pashaフェーズ282の次回候補(3)で横断確認対象
  とされたが、同ventureは`one-time-checkout-no-account-design.md`の設計通り単発
  決済(`mode=payment`)のみでサブスクリプション(`customer.subscription.updated`)
  の概念自体を持たないため、本件は対象外であることを確認した(kura-pasha側README
  参照)。

コード変更は行っていない(ドキュメントのみ)。回帰確認として既存の
`python3 -I -m unittest discover -s prototype -p "test_*.py"`(22件)・
`python3 -I validate_test_cases.py`(9件)・
`python3 -I schema/check_venue_master_parity.py`(36件)・
`python3 prototype/test_venue_matcher.py`(21アサーション)はいずれも変更なしで
パスすることを確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は本フェーズでは発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-11-06 05:00 UTC(フェーズ88: kura-pashaフェーズ282の横断棚卸しを受けて
本venture側のStripe Webhook実装状況を確認。Webhookエントリポイント自体が未実装のため
現時点でのガード欠落修正は対象外と判断し、将来実装時に採用すべきガードパターンを
先行メモとして記録)
