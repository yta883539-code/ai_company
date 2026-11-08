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

## 6. 横展開の棚卸し(フェーズ222、2026-11-08 17:00 UTC)

oshien-pashaがフェーズ97〜99(2026-11-08 04:00〜12:00 UTC)で`prototype/stripe_webhook.py`
を実コード化し、本ドキュメント1節で「Webhookエントリポイント自体が未実装のため対象外」と
していた前提条件が変わったため、本ventureのパターン(本ファイル)を横展開すべきか改めて
確認した。

- 対象4イベント種別(`checkout.session.completed`・`customer.subscription.deleted`・
  `customer.subscription.created`・`customer.subscription.updated`)のハンドラを
  `ventures/oshien-pasha/prototype/stripe_webhook.py`・`fan_pass_store.py`で直接確認した。
  - `_handle_checkout_session_completed()`が呼ぶ`FanPassStore.create()`は、
    `fan_pass_store.py`のdocstring(フェーズ40)が明記する通り、同一
    `stripe_subscription_id`で再度呼ばれた場合は新規発行せず既存の
    `(internal_id, access_token)`を返す設計であり、**`create()`自身が既にStripeの
    重複配信に対応したべき等関数**になっている。
  - 残り3ハンドラ(`customer.subscription.*`)が呼ぶ`update_subscription_status()`は、
    同じ値を再度書き込むだけで実害が無い(べき等)上、`event_time`引数による配信順序
    入れ替わりガード(フェーズ88・96、本venture2節と同型のevent_timeベースガード)も
    既に備えている。
  - 本venture・kura-pasha・aircon-pashaでevent_id_store導入の決め手となった「通知送信の
    重複」という実害は、oshien-pasha側には存在しない(design記載の通りWeb単体・会員登録
    なしでLINE Push等の通知送信を一切行わない構成のため)。
  - `invoice.payment_failed`/`invoice.payment_succeeded`(本ventureでevent_id_storeが
    実際に防いでいる「猶予期間起算点のずれ」という実害の発生源)はoshien-pasha側では
    未実装(2節参照の`subscription-updated-past-due-grace-period-reconsideration.md`も
    Stripe自身のスマートリトライに委ねる設計であり、本venture同様の専用タイムスタンプ
    フィールドは新設していない)。
- 以上により、oshien-pashaの現行4ハンドラはいずれも実害の無いべき等な設計であることを
  確認し、**現時点でevent_id_storeの横展開は不要**と判断した。1節の「対象外」判断は
  当時「Webhook未実装」を理由としていたが、実装後の今も結論(対象外)自体は変わらない
  (理由のみ「未実装」から「実装済みだがいずれもべき等」に更新)。
- 継続監視条件: oshien-pashaが将来`invoice.payment_failed`等の非べき等なハンドラ(通知
  送信・タイムスタンプ上書きを伴うもの)を追加した場合は、本ventureフェーズ215と同じ
  実害が生じうるため、その時点で本ドキュメントを再度参照して横展開要否を確認する
  (次回候補として持ち越す)。

コード変更なし(本ventureの既存実装はフェーズ215時点から変更不要と判明したため)。
既存テスト(unittest discover 114件・run_all_tests.py 24ファイル・schema検証11件・
browser_mockup_checks.js 49件)いずれも変更なしでパス(回帰なし)。承認が必要なアクション
(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。
