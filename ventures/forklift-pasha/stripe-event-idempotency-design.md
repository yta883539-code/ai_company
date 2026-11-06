# Stripe Webhookイベントのべき等性(重複配信)対策設計(フェーズ215)

作成日: 2026-11-06(フェーズ215)

kura-pashaフェーズ283「次回候補(3)」(`customer.subscription.updated`配信順序入れ替わり
ガードの横断棚卸しが完了したため、他の共通設計パターン(例: 冪等性キー・重複配信耐性)に
ついて同様の横断棚卸しが有用か検討する)に対応して実施した横断棚卸しにより発見した欠落に
対応する。

## 1. 横断棚卸しの結果

aircon-pasha(フェーズ177)・course-set-pasha・kura-pasha(フェーズ77)・
line-reservation-aiの4ventureは、いずれも`stripe-event-idempotency-design.md`として
`event.id`単位の処理済み記録による重複配信対策(`StripeEventIdStoreProtocol`・
`InMemoryStripeEventIdStore`・エントリポイント層での一括判定)を設計・実装済みであることを
確認した。event-komiguai-pashaは`checkout.session.completed`の`one_time_draft`書き込みが
同一値の再書き込みのみでべき等であり(かつ`handle_stripe_webhook`自体は結合実装待ちで
`prototype/`に未着手)、現時点で対象外と判断した。oshien-pashaはStripe Webhookエントリ
ポイント自体が未実装(都度プラン主軸の決済フロー設計が先行中、kura-pashaフェーズ283で
確認済み)のため対象外とした。

一方、本venture(forklift-pasha)の`stripe_webhook.py`(フェーズ127〜214)には、
`checkout.session.completed`・`customer.subscription.updated`・
`customer.subscription.deleted`・`customer.subscription.created`・
`invoice.payment_failed`・`invoice.payment_succeeded`の6イベント種別すべてに対応した
ハンドラが実装されているにもかかわらず、`event.id`単位の重複配信対策が一度も実装されて
いない欠落を発見した。

## 2. 実害の確認: `handle_invoice_payment_failed()`

既存6ハンドラのうち5つ(`handle_checkout_session_completed()`・
`handle_customer_subscription_updated()`・`handle_customer_subscription_deleted()`・
`handle_customer_subscription_created()`・`handle_invoice_payment_succeeded()`)は、
フェーズ213・214のevent_timeベース配信順序ガード、または状態そのものの性質(フェーズ130の
「一度きり」判定・フェーズ167の「検知状態なしなら何もしない」設計)により、同一イベントの
再配信を受けても実害が無い(べき等)。

一方`handle_invoice_payment_failed()`(フェーズ167、`payment_failure.py`の
`mark_payment_failure_detected()`)は、受信するたびに`payment_failure_detected_at`を
イベントの`event_time`で**無条件に上書き**する設計である(docstring自身が「Stripeスマート
リトライによる複数回の失敗連続通知でも、既に設定済みなら最新の失敗日時で上書きする」と
明記する、aircon-pasha/kura-pasha同名関数と同じ「安全側」判断)。この設計はStripeスマート
リトライ(失敗後に日数を空けて再試行する正規の再試行)を想定したものだが、**同一の
`invoice.payment_failed`イベントがStripeのat-least-once配信により単純に再配信された
場合も区別なく上書きが発生する**ため、猶予期間(payment-failure-dunning-design.md)の
起算点が再配信のたびに後ろへずれ続けてしまう。これはkura-pashaフェーズ77・aircon-pasha
フェーズ177が同型のハンドラについて指摘した実害と同一である。

(本venture側では通知送信自体〈design 6節「残課題」〉は未配線のため、重複通知という
実害は現時点では発生しないが、猶予期間の起算点のずれという実害は既に発生し得る。)

## 3. 設計方針(aircon-pashaフェーズ177・kura-pashaフェーズ77と同一)

`event.id`を処理済みイベントIDの集合として保持し、2回目以降の同一`event.id`受信時は
対応するハンドラを一切呼び出さずに(副作用ゼロで)200を返す方式とする。

- 個別ハンドラごとにべき等性を作り込むのではなく、`receive_stripe_webhook()`のエントリ
  ポイント層で一括して弾く方式を採用する(将来ハンドラが増えるたびに個別対応が必要になる
  構造を避けるため)。
- `StripeEventIdStoreProtocol`(`has_processed(event_id)`・`mark_processed(event_id)`)を
  新規Protocolとして独立させる。本ventureの唯一のドキュメントストアである
  `FleetOperatorStoreProtocol`(キーが`internal_id`)とは性質が異なるため混在させない。
- `event_id_store`は`receive_stripe_webhook()`の新規キーワード専用引数(デフォルト
  `None`)とし、未指定時は従来通りべき等性チェックを一切行わない(既存呼び出し経路への
  後方互換措置)。
- `event.id`が欠落・非文字列の場合はべき等性チェックをスキップし従来通り処理する(安全側)。
- チェック位置: 署名検証・JSONパース成功後、イベント種別による分岐より前に行う(いずれの
  分岐でも重複排除が効くようにするため)。
- 記録タイミング: 各ハンドラ呼び出し「後」に`mark_processed()`を呼ぶ(本venture未着手の
  イベント種別〈いずれのハンドラも呼ばれない最終分岐〉は記録しない)。

## 4. 実装(`InMemoryStripeEventIdStore`)

`set[str]`を内部に持つだけの最小実装。プロセス起動ごとに初期化されるため、実Cloud
Functions環境では呼び出しをまたいで保持されない(他venture・既存の各種InMemoryストアと
同じ既知の限界、実Firestore接続後に`processed_stripe_events/{event_id}`コレクションで
解消する想定も他venture同様)。`get_stripe_runtime_dependencies()`に`store`とは独立した
インスタンスとして追加した。

## 5. 残課題

- 実Firestore接続後の`processed_stripe_events`コレクション実装は、実Stripe/実GCP
  プロジェクト接続後(オーナー承認待ち)の課題として残る。
- event-komiguai-pasha(結合実装待ち)・oshien-pasha(Webhook未実装)は、各venture側で
  実装着手時に本ドキュメントを参照して横展開する。
