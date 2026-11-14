# event-komiguai-pasha 公開までのチェックリスト(フェーズ119時点)

目的: 設計・実装・テストは完了しているが、実際の稼働にはオーナー承認が必要な外部サービス
設定が複数残っている。オーナーがpending-approval.mdを一つずつ確認する際に迷わないよう、
本ventureに関わる承認待ち事項を依存順に並べ、承認後すぐ着手できる作業内容を1箇所にまとめる。
aircon-pasha(フェーズ289)・kura-pasha(フェーズ196)・course-set-pasha(フェーズ266)・
line-reservation-ai(フェーズ続き286)・forklift-pasha・oshien-pashaと同型の整理であり、
7venture中これまで本checklistが未作成だった唯一のventureだったため今回新規作成した
(INDEX.mdにも追記)。

## 現状(実装・検証済み、追加作業不要)

- 申込フォーム(event-information/organizer入力)・問い合わせフォームのHTTPエントリポイント
  (inquiry-form-http-entry-point-design.md・submit-event-form-http-entry-point-design.md)、
  都度決済(one-time-checkout-no-account-design.md)のCheckout Session発行・Stripe Webhook
  受信/署名検証/イベントディスパッチ(stripe-checkout-session-params-design.md・
  stripe-webhook-signature-verification-design.md・stripe-event-idempotency-design.md)、
  結果ページのTTL付きアクセス制御・配信失敗時の返金判定(result-page-ttl-access-design.md・
  ttl-expiry-result-delivery-refund-design.md)、冪等性キーの重複検出・書き込み競合制御
  (idempotency-key-duplicate-detection-firestore-query-design.md・
  idempotency-key-write-conflict-control-design.md)はいずれも設計・プロトタイプコード
  (prototype/)・InMemory相当のモック/スタブによるテスト184件・schema検証22件まで完了。
- LLMによるイベント告知文生成(llm-system-prompt-draft.md)・出力品質検証方針
  (llm-quality-verification-plan.md・output-samples-validation.md)、料金プラン
  (pricing-plan.md、月間開催件数ベース3プラン)・単価試算(unit-economics-estimate.md)は
  机上設計まで完了。
- 顧客ヒアリング候補研究: 候補1(奈良NEVER LAND、オーナー兼店長 岩城吉映氏)の初回コンタクト
  文面案A・B(initial-contact-message-draft.md、フェーズ33)まで作成済み。候補2(那覇市、
  中山一朗氏)は屋号未特定のため対象外。
- Billing Budget安全策(billing-budget-cap-safeguard-design.md、月間予算500円)は
  フェーズ118で設定済み(本venture自体の都度決済モデルとGCP側コスト監視が独立した別軸で
  あることを確認済み)。

## 承認待ち事項(依存順、pending-approval.md記載の要約)

1. **実GCPプロジェクト作成 + Firestoreデータベース新規作成**(2026-10-28 06:00 UTC記載)
   `one_time_draft`コレクション(TTL24時間自動失効)・`inquiry`コレクション・
   `idempotency_key_index`コレクション等、tech-stack.md・one-time-checkout-no-account-
   design.md・ttl-expiry-result-delivery-refund-design.md・inquiry-handling-design.md・
   idempotency-key-write-conflict-control-design.mdで設計済みの実コレクション・ドキュメント
   構造のデプロイ先。本venture自体の稼働に必須の前提。
   → 承認後: 実GCPプロジェクトの作成、Firestoreデータベースの新規作成、各設計文書で
   確定済みのコレクション構造の実デプロイ・結合実装から着手。

2. **実Stripeアカウント開設**(1.と同一エントリ内に記載、本venture自体の稼働に必須)
   本人確認・銀行口座登録、本番用APIキー・Webhook署名シークレット取得、Stripe側Webhook
   エンドポイント登録(mode=paymentの都度決済Checkout Session発行先)。
   → 承認後: 実APIキー・Webhookシークレットの設定、Webhookエンドポイント登録から着手。

3. **顧客ヒアリングの実施**(2026-10-21 03:00 UTC記載)
   候補1(奈良NEVER LAND)への初回コンタクト・ヒアリング協力依頼。公式サイト
   (nara-neverland.com)に問い合わせフォーム・電話番号等の窓口が実在するかはWebSearch経由
   では未確認のままで、承認後も「窓口確認→文面確定→送信」の順になる見込み。
   → 承認後: 電話での実連絡はオーナー自身が行うか、メール送信はGmail連携接続後に送信直前の
   毎回確認を経てのみ行う。

## 次回候補

上記1〜3のいずれかがオーナーから承認された場合、その着手を最優先とする。承認が得られる
までの間は、他venture・アイデア領域の前進を優先し、本venture側の軽微な記載漏れ・陳腐化
記載の棚卸しは実質的な変更が必要になった時点まで保留する(aircon-pashaフェーズ293の
「重複作業の抑制方針」と同じ考え方を踏襲)。
