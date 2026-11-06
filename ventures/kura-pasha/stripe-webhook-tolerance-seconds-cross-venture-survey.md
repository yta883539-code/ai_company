# Stripe Webhook 署名検証タイムスタンプ許容範囲(`tolerance_seconds`)横断棚卸し

- フェーズ: kura-pashaフェーズ285
- 日時: 2026-11-06 20:00 UTC台定例更新
- 発端: フェーズ284次回候補(3)「署名検証のタイムスタンプ許容範囲`tolerance_seconds`の
  各venture間の値の揃いについて同様の横断棚卸しが有用か検討する」への対応。

## 調査方法

Stripe Webhookの署名検証(`verify_stripe_signature`相当関数)を実装している
全venture配下の`prototype/stripe_webhook.py`を対象に、`tolerance_seconds`の
デフォルト値・用途をgrepで横断確認した。

## 結果

| venture | 実装有無 | `tolerance_seconds`デフォルト値 |
|---|---|---|
| aircon-pasha | 実装済み | 300秒 |
| course-set-pasha | 実装済み | 300秒 |
| forklift-pasha | 実装済み | 300秒 |
| kura-pasha(本venture) | 実装済み | 300秒 |
| line-reservation-ai | 実装済み | 300秒 |
| event-komiguai-pasha | 未実装(`handle_stripe_webhook`自体が結合実装待ち、`prototype/`に
  webhook関連ファイルなし) | 対象外 |
| oshien-pasha | 未実装(Stripe Webhookエントリポイント自体が未実装、フェーズ283で確認済み) | 対象外 |

Stripeの公式推奨値(5分=300秒)と一致する値を、webhookを実装済みの5venture全てが
デフォルト値として揃って採用していることを確認した。値のズレ・欠落は見つからなかった。

## 結論

今回の棚卡では是正が必要な欠落は発見されなかった(全5venture一致)。
`event.id`重複配信対策(フェーズ284)・配信順序ガード(`customer.subscription.updated`
等、フェーズ283以前)に続き、本設計パターンについても横断的な揃いが取れていることを
確認できた。

## 次回候補

1. 承認待ち事項(「承認待ち事項」節)がオーナーから承認された場合はその着手を最優先
2. フェーズ266次回候補(2)「4節のログ出力側(`event`構造化フィールド)への実装反映を
   結合実装フェーズで行う」(引き続き結合実装フェーズ待ち)
3. 他の共通設計パターン(例: Webhookエンドポイントのレスポンスタイムアウト設定、
   Idempotency-Keyヘッダのクライアント側送信有無)について同様の横断棚卸しが有用か検討する
4. 他venture・アイデア領域の前進
