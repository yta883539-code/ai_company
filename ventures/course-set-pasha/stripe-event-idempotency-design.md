# Stripe Webhookイベントのべき等性(重複配信)対策設計

フェーズ151。stripe-webhook-signature-verification-design.md「残課題」に残っていた
「Stripeイベントの重複配信対策(`event.id`によるべき等性チェック)は、エンドポイント
本体側の設計課題として次回以降に持ち越す」に対応する。aircon-pashaがフェーズ177で
先行実装した設計(stripe-event-idempotency-design.md)をそのまま本venture向けに横展開する
(aircon-pasha側ドキュメントで「line-reservation-ai・course-set-pashaにも同種の未着手記載が
あることを確認、3venture共通の未解決事項だった」と記録されていた対応の1件目)。

## 1. 背景・問題

Stripeは同一イベントを複数回配信することがある(公式ドキュメント上も「at least once」
配信であり、受信側の200応答が遅延・タイムアウトした場合等に再送されうる)。
現状の`receive_stripe_webhook()`は署名検証さえ通れば毎回`dispatch_stripe_event()`/
`handle_checkout_session_completed()`を呼び出しており、同一イベントが2回届いた場合の
挙動はハンドラごとにまちまちである:

- `mark_deletion_candidate_on_subscription_deleted()`・`clear_deletion_candidate_on_
  subscription_reactivated()`系: 同じ値を再度書き込むだけで実害はない(べき等)。
- `handle_checkout_session_completed()`の`upgraded_at`書き込み: 既に設定済みなら
  上書きしない設計(usage_counter.set_upgraded_at_if_unset())のため、こちらもべき等。
- `handle_payment_failure_detected()`・`handle_payment_succeeded()`
  (payment_recovery_notification.py、決済失敗検知・復旧通知の送信): **べき等ではない**。
  同一の`invoice.payment_failed`/`invoice.payment_succeeded`イベントが2回配信
  されると、LINE Push通知が2回送信されてしまう(オーナーが同じ内容の通知を
  複数回受け取ることになり、実運用上の混乱を招く)。aircon-pasha版と同じ問題構造。

このため、通知送信を伴うハンドラを中心に、イベント単位でのべき等性チェックが必要。

## 2. 設計方針(aircon-pasha版を踏襲、venture固有の差異なし)

`event.id`(Stripeイベントオブジェクトの一意なID、例: `evt_1NxxxAB...`)を処理済み
イベントIDの集合として保持し、2回目以降の同一`event.id`受信時はハンドラを一切
呼び出さずに(副作用ゼロで)200を返す方式とする。

- `receive_stripe_webhook()`のエントリポイント層で一括して弾く方式を採用する
  (個別ハンドラごとのべき等性作り込みは避ける。aircon-pasha版と同じ理由)。
- `event_id_store`は新規のProtocol(`StripeEventIdStoreProtocol`)として独立させる。
  既存の`user_profile_store`/`usage_counter`のように構造的型付けで共有する設計には
  しない(キーが`user_id`ではなく`event_id`であり性質が異なるため)。
  - `has_processed(event_id: str) -> bool`
  - `mark_processed(event_id: str) -> None`
- `event_id_store`は`receive_stripe_webhook()`の新規オプション引数(デフォルト
  `None`)とし、未指定時は従来通りべき等性チェックを一切行わない(既存呼び出し
  経路への後方互換措置)。
- `event.id`が欠落している、または文字列でない場合はべき等性チェックをスキップし
  従来通り処理する(安全側〈処理を止めない〉に倒す)。
- チェック位置: 署名検証・JSONパース成功後、`checkout.session.completed`か
  それ以外かの分岐より前に行う(どちらの分岐でも重複排除が効くようにするため)。
- 記録タイミング: ハンドラ呼び出し「後」に`mark_processed()`を呼ぶ
  (例外発生時に未処理のまま処理済み扱いになる事故を避けるため)。

## 3. InMemory実装

`InMemoryStripeEventIdStore`: `set[str]`を内部に持つだけの最小実装
(aircon-pasha版と同一)。プロセス起動ごとに初期化されるため実Cloud Functions環境
では呼び出しをまたいで保持されない(既存の各種InMemoryストアと同じ既知の限界)。

実Firestore接続時は、`event_id`をドキュメントIDとするコレクション(例:
`processed_stripe_events/{event_id}`)に、書き込み時刻とともに1件書き込む方式を
想定する(aircon-pasha版と同じ、TTL付き自動削除は将来検討課題)。

## 4. `get_stripe_runtime_dependencies()`への追加

新規の`InMemoryStripeEventIdStore()`を1つ生成し、`event_id_store`キーとして
辞書に追加する。`store`・`user_profile_store`とは独立したインスタンスとする。

## 5. 残課題

- 実Firestore接続(3節の`processed_stripe_events`コレクション実装)は、実Stripe/
  実GCPプロジェクト接続後(オーナー承認待ち)の課題として残る。
- line-reservation-aiへの同種対応の横展開は、本ドキュメントの範囲外
  (aircon-pasha版と同じく、必要になった際に本ドキュメントを参照して展開する)。
