# Stripe Webhookイベントのべき等性(重複配信)対策設計

フェーズ177。stripe-webhook-signature-verification-design.md「残課題」に残っていた
「Stripeイベントの重複配信対策(`event.id`によるべき等性チェック)は、エンドポイント
本体側の設計課題として次回以降に持ち越す」に対応する。line-reservation-ai・
course-set-pashaの同ドキュメントにも同種の記載が残っており(2026-09-03フェーズ177
時点でいずれも未着手)、3venture共通の未解決事項だったことを確認した。

## 1. 背景・問題

Stripeは同一イベントを複数回配信することがある(公式ドキュメント上も「at least once」
配信であり、受信側の200応答が遅延・タイムアウトした場合等に再送されうる)。
現状の`receive_stripe_webhook()`は署名検証さえ通れば毎回`dispatch_stripe_event()`/
`handle_checkout_session_completed()`を呼び出しており、同一イベントが2回届いた場合の
挙動はハンドラごとにまちまちである:

- `mark_deletion_candidate_on_subscription_deleted()`・`clear_...`系: 同じ値を
  再度書き込むだけで実害はない(べき等)。
- `handle_checkout_session_completed()`の`upgraded_at`書き込み: 既に設定済みなら
  上書きしない設計(フェーズ135)のため、こちらもべき等。
- `handle_payment_failure_detected()`(決済失敗検知通知の送信、フェーズ147)・
  `handle_payment_succeeded()`(復旧通知の送信、フェーズ148): **べき等ではない**。
  同一の`invoice.payment_failed`/`invoice.payment_succeeded`イベントが2回配信
  されると、LINE Push通知が2回送信されてしまう(オーナーが同じ内容の通知を
  複数回受け取ることになり、実運用上の混乱を招く)。

このため、通知送信を伴うハンドラを中心に、イベント単位でのべき等性チェックが必要。

## 2. 設計方針

`event.id`(Stripeイベントオブジェクトの一意なID、例: `evt_1NxxxAB...`)を処理済み
イベントIDの集合として保持し、2回目以降の同一`event.id`受信時はハンドラを一切
呼び出さずに(副作用ゼロで)200を返す方式とする。

- 個別ハンドラごとにべき等性を作り込む(例: 通知送信前に送信済みフラグを見る)
  のではなく、`receive_stripe_webhook()`のエントリポイント層で一括して弾く方式を
  採用する。理由: (1)将来ハンドラが増えるたびに個別対応が必要になる構造を避けたい、
  (2)署名検証と同じ「エントリポイント層での一括処理」という既存の設計思想
  (stripe-webhook-http-entry-point-design.md)と一貫する。
- `event_id_store`は新規のProtocol(`StripeEventIdStoreProtocol`)として独立させる。
  既存の`payment_store`/`plan_store`/`blocked_but_billing_store`のように
  `UserProfileStoreProtocol`が構造的に(duck typing)満たす設計にはしない
  (キーが`user_id`ではなく`event_id`であり性質が異なるため、同じストアに
  混在させると将来のFirestoreコレクション設計上わかりにくくなる)。
- Protocol定義:
  - `has_processed(event_id: str) -> bool`: 既に処理済みなら`True`。
  - `mark_processed(event_id: str) -> None`: 処理済みとして記録する。
- `event_id_store`は`receive_stripe_webhook()`の新規オプション引数(デフォルト
  `None`)とし、未指定時は従来通りべき等性チェックを一切行わない(既存呼び出し
  経路への後方互換措置、`payment_store`等と同じ方針)。
- `event.id`が欠落している、または文字列でない場合はべき等性チェックをスキップし
  従来通り処理する(Stripeの実イベントでは通常発生しないが、テスト用の最小
  イベントdict等では省略されることがあるため、安全側〈処理を止めない〉に倒す)。
- チェック位置: 署名検証・JSONパース成功後、`checkout.session.completed`か
  それ以外かの分岐より前に行う(どちらの分岐でも重複排除が効くようにするため)。
- 記録タイミング: ハンドラ呼び出し「後」に`mark_processed()`を呼ぶ。ハンドラ内で
  例外が飛んだ場合(現状のハンドラは例外を投げない設計だが、将来の変更に備えて)に
  未処理のまま処理済み扱いになってしまう事故を避けるため。

## 3. InMemory実装

`InMemoryStripeEventIdStore`: `set[str]`を内部に持つだけの最小実装。
`deletion_candidate.py`等の既存InMemoryストアと同じく、プロセス起動ごとに
初期化されるため実Cloud Functions環境では呼び出しをまたいで保持されない
(実Firestore接続後に解消される既知の限界、`get_stripe_runtime_dependencies()`の
既存コンポーネントと同じ制約)。

実Firestore接続時は、`event_id`をドキュメントIDとするコレクション(例:
`processed_stripe_events/{event_id}`)に、書き込み時刻とともに1件書き込む方式を
想定する(TTL付きコレクションでの自動削除も将来検討課題とするが、本フェーズの
範囲外)。

## 4. `get_stripe_runtime_dependencies()`への追加

新規の`InMemoryStripeEventIdStore()`を1つ生成し、`event_id_store`キーとして
辞書に追加する。既存の`user_profile_store`とは独立したインスタンスとする
(3節のとおりキーの性質が異なるため使い回さない)。

## 5. 残課題

- 実Firestore接続(3節の`processed_stripe_events`コレクション実装)は、実Stripe/
  実GCPプロジェクト接続後(オーナー承認待ち)の課題として残る。
- line-reservation-ai・course-set-pashaへの同種対応の横展開は、本ドキュメントの
  範囲外(各venture側で必要になった際に本ドキュメントを参照して展開する)。
