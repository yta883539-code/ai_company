# Stripe Webhookイベントのべき等性(重複配信)対策設計(フェーズ99)

stripe-webhook-signature-verification-design.md(フェーズ99)2-2節の設計を受け、
`event.id`単位のエントリポイント層での重複配信対策を整理する。aircon-pasha/stripe-
event-idempotency-design.md(フェーズ177)と同じ問題意識(Stripeは「at least once」
配信であり、受信側の200応答遅延・タイムアウト時に同一イベントが再送されうる)だが、
本venture固有の事情により設計の一部が異なる。

## 1. 他ventureとの違い

aircon-pasha等の継続課金モデルは、通知送信(LINE Push)を伴う一部ハンドラが非べき等
であるため`event_id_store`が必須級の対策だった。本venture(単発決済モデル)は
`checkout.session.completed`の1種類のみを扱い、かつ`one_time_draft`のステータス遷移
自体が「`awaiting_payment`から一度しか進まない」設計(stripe-webhook-signature-
verification-design.md 2-2節)のため、ハンドラ側の業務ロジックだけでも重複配信に対して
概ね安全ではある。

しかし次の2点から、本ventureでも`event_id_store`によるエントリポイント層でのチェックを
併設する方針とする。

1. 生成処理(LLM API呼び出し)はコストを伴う副作用であり、`awaiting_payment`判定から
   実際のステータス書き込みまでの間(Firestoreの読み取り→生成→書き込みという複数ステップ)
   に同一イベントの2回目の配信が割り込んだ場合、理論上は生成処理が二重実行されうる
   (`one_time_draft`のステータス更新自体はべき等でも、更新前の生成呼び出しまでは
   べき等が保証されない、いわゆるTOCTOU的な隙間)。`event_id_store`はこの隙間を
   Firestoreへのいかなる読み書きよりも手前、エントリポイントの入口で弾くため、
   当該リスクを実質的に無くす。
2. Stripe公式ドキュメントが冪等性チェックの実装を一般的な推奨事項としており、
   他6venture全てで同じ対策を導入済みの中で本ventureだけ未導入のままにしておくと、
   将来本venture側のハンドラが複雑化した際(例: 返金フロー〈ttl-expiry-result-
   delivery-refund-design.mdフェーズ12 3-2節〉の自動トリガー実装時)に非べき等な
   副作用が増える可能性があり、その時点で後追い導入するより今のうちに揃えておく方が
   安全である。

## 2. 設計方針(aircon-pasha版を踏襲)

- `event.id`を処理済みイベントIDの集合として保持し、2回目以降の同一`event.id`受信時は
  ハンドラを一切呼び出さずに(副作用ゼロで)200を返す。
- `StripeEventIdStoreProtocol`(`has_processed(event_id) -> bool`・
  `mark_processed(event_id) -> None`)を本venture独自に定義する(他ventureのクラスを
  importするのではなく、venture間の依存を作らない既存方針〈各venture独立のprototype/
  ディレクトリ〉を踏襲)。
- `event.id`が欠落・非文字列の場合はチェックをスキップし従来通り処理する(安全側)。
- チェック位置: 署名検証・JSONパース成功後、イベント種別分岐より前。
- 記録タイミング: ハンドラ呼び出し「後」(`mark_processed()`)。

## 3. InMemory実装

`InMemoryStripeEventIdStore`: `set[str]`を内部に持つだけの最小実装。プロセス起動ごとに
初期化されるため実Cloud Functions環境では呼び出しをまたいで保持されない(既存の各種
InMemoryストアと同じ既知の限界)。実Firestore接続時は`processed_stripe_events/{event_id}`
コレクション(aircon-pasha版と同じ想定)への書き込みで代替する。

## 4. `handle_checkout_session_completed()`側の多層防御との役割分担

| 層 | 防ぐ対象 | 実装箇所 |
|---|---|---|
| `event_id_store`(本設計) | 同一`event.id`の再送による生成処理の二重実行 | `receive_stripe_webhook()`入口 |
| ドラフトステータスチェック | `event_id_store`が未配線・未指定の場合でも、既に`awaiting_payment`から進んだドラフトへの再生成を防ぐ | `handle_checkout_session_completed()` |
| TTL失効チェック | 期限切れドラフトへの生成試行(ttl-expiry-result-delivery-refund-design.mdフェーズ12 1節) | `handle_checkout_session_completed()` |

3層とも独立して機能し、いずれか1つが欠けても残り2層が安全側に働く設計とする。

## 5. 残課題

- 実Firestore接続(3節の`processed_stripe_events`コレクション実装)は、実Stripe/実GCP
  プロジェクト接続後(オーナー承認待ち)の課題として残る。
- 返金フロー(ttl-expiry-result-delivery-refund-design.mdフェーズ12 3-2節)の自動トリガー
  実装自体は本フェーズの範囲外(本設計は受信口の冪等性に限定する)。
