# Stripe Webhookイベントのべき等性(重複配信)対策設計(フェーズ77)

作成日: 2026-09-11(フェーズ77)

stripe-webhook-checkout-completed-design.md(フェーズ51)「4. 未検証・残課題」
最後の項目に残っていた「イベントID(`event.id`)によるべき等性チェック
(course-set-pashaフェーズ151・aircon-pashaフェーズ177が実装済み)は、本ventureでは
`checkout.session.completed`がworkshop_idごとに複数回届いても`set_subscription_status`の
上書きで実害が無いため当面省略した。将来`invoice.payment_failed`等の非べき等な通知処理を
追加する際に改めて必要性を検討する」に対応する。`invoice.payment_failed`
(payment-failure-dunning-design.md フェーズ56)・`customer.subscription.deleted`
(subscription-canceled-webhook-design.md フェーズ53)・`customer.subscription.updated`
(subscription-cancellation-scheduled-notification-design.md フェーズ55)がいずれも
既に実装済みとなった現時点で、当時「将来検討する」としていた条件が揃ったため着手する。
aircon-pashaのstripe-event-idempotency-design.md(フェーズ177)の設計・実装
(`StripeEventIdStoreProtocol`・`InMemoryStripeEventIdStore`・エントリポイント層での
一括判定)を、本venture固有のディスパッチ構造へ翻案する。

## 1. 背景・問題の再確認

Stripeは同一イベントを複数回配信することがある(公式ドキュメント上も「at least once」
配信であり、受信側の200応答が遅延・タイムアウトした場合等に再送されうる)。
現状の`receive_stripe_webhook()`は署名検証さえ通れば毎回対応するハンドラを呼び出しており、
同一イベントが2回届いた場合の挙動はハンドラごとにまちまちである。

- `handle_checkout_session_completed()`: `set_stripe_customer_id`は既存値がある場合
  書き込まない設計(フェーズ51)、`set_subscription_status(workshop_id, "active")`は
  同じ値を再度書き込むだけで実害がない。**べき等**。
- `handle_customer_subscription_deleted()`(フェーズ53・54): `set_subscription_status`
  はべき等だが、`push_client`指定時は毎回`handle_subscription_cancelled()`を無条件で
  呼び出し、解約完了通知を送信する。同一イベントの再配信で契約者へ同じ内容の通知が
  複数回届く。**べき等ではない**。
- `handle_customer_subscription_updated()`(フェーズ55): `cancel_at_period_end`の
  前後比較(`before`/`after`)から分類し通知するが、状態変更を一切伴わないため
  (design 6節)再配信のたびに全く同じ`before`/`after`が得られ、同じ通知が
  再送されてしまう。**べき等ではない**。
- `handle_invoice_payment_failed()`(フェーズ56): 毎回`payment_failure_detected_at`を
  イベントの`created`(または`now`)で**上書き**し、`push_client`指定時は毎回
  `PAYMENT_FAILURE_DETECTED_MESSAGE`を送信する。同一イベントが再配信されると、
  (1)決済失敗検知通知が二重に届く、(2)猶予期間の起算点が再配信のたびに後ろへ
  ずれ続ける、という2つの実害がある。**べき等ではなく、他の3ハンドラより実害が大きい**。
- `handle_invoice_payment_succeeded()`(フェーズ56): `payment_failure_notification.
  handle_payment_succeeded()`のdocstringが明記する通り、通知送信後に
  `payment_failure_detected_at`をクリアするため、再配信時は`classify_payment_recovery()`
  が`OUTCOME_NOT_APPLICABLE`(検知状態なし)に落ち、通知は送られない。状態そのものから
  べき等性が自然に担保されている数少ない例。**実質べき等**。

このように、通知送信を伴うハンドラ(特に`invoice.payment_failed`)を中心に、
イベント単位でのべき等性チェックが必要であることを再確認した。

## 2. 設計方針(aircon-pashaフェーズ177と同一)

`event.id`(Stripeイベントオブジェクトの一意なID、例: `evt_1NxxxAB...`)を処理済み
イベントIDの集合として保持し、2回目以降の同一`event.id`受信時はハンドラを一切
呼び出さずに(副作用ゼロで)200を返す方式とする。

- 個別ハンドラごとにべき等性を作り込む(例: 送信前に送信済みフラグを見る)のではなく、
  `receive_stripe_webhook()`のエントリポイント層で一括して弾く方式を採用する。
  理由はaircon-pasha版と同じ: (1)将来ハンドラが増えるたびに個別対応が必要になる構造を
  避けたい、(2)署名検証と同じ「エントリポイント層での一括処理」という既存の設計思想
  (design 3節)と一貫する。
- `event_id_store`は新規のProtocol(`StripeEventIdStoreProtocol`)として独立させる。
  本ventureの唯一のドキュメントストアである`WorkshopStoreProtocol`が構造的に
  (duck typing)満たす設計にはしない(キーが`workshop_id`ではなく`event_id`であり
  性質が異なるため、同じストアに混在させると将来のFirestoreコレクション設計上
  わかりにくくなる。aircon-pasha design 2節と同じ理由)。
- Protocol定義:
  - `has_processed(event_id: str) -> bool`: 既に処理済みなら`True`。
  - `mark_processed(event_id: str) -> None`: 処理済みとして記録する。
- `event_id_store`は`receive_stripe_webhook()`の新規キーワード専用引数(デフォルト
  `None`)とし、未指定時は従来通りべき等性チェックを一切行わない(既存呼び出し経路への
  後方互換措置)。
- `event.id`が欠落している、または文字列でない場合はべき等性チェックをスキップし
  従来通り処理する(Stripeの実イベントでは通常発生しないが、テスト用の最小イベント
  dict等では省略されることがあるため、安全側〈処理を止めない〉に倒す)。
- チェック位置: 署名検証・JSONパース成功後、イベント種別による分岐(対応イベント種別か
  無視するかを含む)より前に行う(いずれの分岐でも重複排除が効くようにするため)。
- 記録タイミングと条件: 各ハンドラ呼び出し「後」に`mark_processed()`を呼ぶ
  (ハンドラ内で例外が飛んだ場合〈現状のハンドラは例外を投げない設計だが、将来の変更に
  備えて〉に未処理のまま処理済み扱いになってしまう事故を避けるため、aircon-pasha版と
  同じ考え方)。ただし本venture固有の追加判断として、ハンドラの結果が`invalid`
  (400、`customer`欠落等の不正なイベント)の場合は記録しない。Stripe側に本物の不具合
  (データ欠落した不正イベント)がある場合、処理済みとして記録してしまうと2回目以降
  常に`duplicate_event=True`(200)を返すようになり、Stripeダッシュボード上で
  Webhookエラーとして可視化され続けるべき異常が1回しか見えなくなってしまうため、
  あえて対象外とした。`unresolved`(逆引き失敗、200)はアプリケーション側では正常な
  「該当workshopなし」という結果であり実害の無い重複のため、記録対象に含める。

aircon-pashaのProtocol/InMemory実装は`typing.Protocol`を継承しない素のクラス
(メソッド本体`raise NotImplementedError`)だったが、本venture既存の各Protocol
(`WorkshopStoreProtocol`・`UserProfileStoreProtocol`・`LinePushClient`等、いずれも
`typing.Protocol`継承・メソッド本体`...`)の記法と揃え、`StripeEventIdStoreProtocol`も
同じ記法で定義した(venture内の一貫性を優先し、翻案元と完全に同一の記法にはしなかった)。

## 3. InMemory実装

`InMemoryStripeEventIdStore`: `set[str]`を内部に持つだけの最小実装。既存の
`InMemoryWorkshopStore`等と同じく、プロセス起動ごとに初期化されるため実Cloud
Functions環境では呼び出しをまたいで保持されない(実Firestore接続後に解消される
既知の限界)。

実Firestore接続時は、`event_id`をドキュメントIDとするコレクション(例:
`processed_stripe_events/{event_id}`)に、書き込み時刻とともに1件書き込む方式を
想定する(aircon-pasha design 3節と同じ想定。TTL付きコレクションでの自動削除も
将来検討課題とするが、本フェーズの範囲外)。

## 4. 実装

`prototype/stripe_webhook.py`に`StripeEventIdStoreProtocol`・
`InMemoryStripeEventIdStore`を新設し、`receive_stripe_webhook()`に`event_id_store`
キーワード引数を追加した。`StripeWebhookReceiverResult`に`duplicate_event: bool = False`
フィールドを追加し、重複検知時はこのフラグとともに`status_code=200`を返す。
`checkout.session.completed`/`customer.subscription.updated`/
`customer.subscription.deleted`/`invoice.payment_failed`/`invoice.payment_succeeded`の
全5分岐に、2節の条件(`invalid`以外)で`mark_processed()`呼び出しを追加した。

新規テスト12関数・check()単位で19件(`test_stripe_webhook.py`)を追加し、以下を検証した。

- `InMemoryStripeEventIdStore`単体の`has_processed`/`mark_processed`基本動作(2関数、
  計3件)。
- `event_id_store`指定時、同一`event.id`の2回目の`invoice.payment_failed`が
  (1)`duplicate_event=True`・`status_code=200`を返す、(2)`payment_failure_detected_at`を
  上書きしない(1回目の値のまま)、(3)通知を再送しない、ことを確認する統合テスト
  (3関数、計6件)。これが2節で最も実害が大きいと整理したケースへの直接的な回帰
  テストになる。
- 同様に`customer.subscription.deleted`(解約完了通知の二重送信防止、1関数)・
  `customer.subscription.updated`(解約予約受理通知の二重送信防止、1関数)についても
  重複時に通知が再送されないことを確認する統合テスト(計2件)。
- `event.id`欠落時・非文字列時はチェックをスキップし従来通り処理されることの確認
  (2関数、計3件)。
- `event_id_store`省略時(`None`)は同一`event.id`を2回送っても重複判定されず、
  従来通り毎回処理される(後方互換)ことの確認(1関数、1件)。
- `unresolved`(逆引き失敗)は処理済みとして記録され2回目はduplicate扱いになる一方、
  `invalid`(400)は記録されず2回目も400のままであることの確認(design 2節の
  記録条件、2関数、計4件)。

## 5. 残課題

- 実Firestore接続(3節の`processed_stripe_events`コレクション実装)は、実Stripe/実GCP
  プロジェクト接続後(オーナー承認待ち)の課題として残る。
- `get_stripe_runtime_dependencies()`相当の依存関係組み立てファクトリ(他venture既存)は
  本venture側にまだ存在しない(HTTPエントリポイント〈Cloud Functionsへのデプロイ〉自体が
  オーナー承認待ちのため未着手)。実装時は`InMemoryStripeEventIdStore()`を
  `workshop_store`とは独立に1つ生成する想定。
- line-reservation-ai・course-set-pasha・aircon-pashaへの追加対応は本ドキュメントの
  範囲外(各venture側で必要になった際に検討する)。

最終更新: 2026-09-11 02:00 UTC(フェーズ77: stripe-webhook-checkout-completed-design.md
「4. 未検証・残課題」に残っていたevent.idべき等性チェックを実装。aircon-pashaフェーズ177の
設計を翻案し`StripeEventIdStoreProtocol`・`InMemoryStripeEventIdStore`を新設、
`receive_stripe_webhook()`のエントリポイント層で一括判定する方式とした。特に
`invoice.payment_failed`の再配信時に猶予期間の起算点が後ろへずれ続け通知も二重送信される
実害を解消した。新規テスト19件追加、venture全体569件→588件全件・schema検証27件
いずれもパス)
