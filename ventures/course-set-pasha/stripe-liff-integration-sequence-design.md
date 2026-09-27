# Stripe/LINE LIFF結合構成の実施順序整理(stripe-liff-integration-sequence-design.md)

作成日: 2026-09-27(フェーズ260)

## 1. 目的

フェーズ259の「次回候補」に挙がった「LIFFアプリ登録案件と合わせたStripe/LINE結合構成の
整理」に対応する。実Stripeアカウント接続(2026-09-27 03:00 UTC pending-approval.md記載)、
LIFFアプリ登録(checkout-initiation-flow-design.md 残課題)は、いずれもオーナー承認待ちで
未着手だが、承認が得られた際に手戻りなく着手できるよう、複数の外部サービス接続案件の
間にある依存関係を本ドキュメントで先に整理する。設計・実装済みのロジックの変更は行わない。

## 2. 現状棚卸し: 未着手の外部サービス接続案件

| 案件 | pending-approval.md記載 | 依存する設計doc |
|---|---|---|
| LINE公式アカウント開設(Basic ID確定) | 2026-08-18 20:00 UTC(旧・申込フォーム案件内)| line-user-id-linking-design.md |
| Googleフォーム+GAS Webhook(申込受付) | 2026-08-18 20:00 UTC / 2026-08-20 21:00 UTC(仕様変更) | application-form-submission-flow-design.md |
| LIFFアプリ登録 | 未記録(本ドキュメントで記載漏れと判明、4節参照) | checkout-initiation-flow-design.md |
| Stripeアカウント開設・本番APIキー・Webhook | 2026-09-27 03:00 UTC | checkout-session-endpoint-design.md / checkout-session-cloud-function-entry-point-design.md |

## 3. 依存関係グラフ

```
LINE公式アカウント開設(Basic ID確定)
  └─ LIFFアプリ登録(LINE Developersコンソールで、既存の公式アカウントのチャネルに紐づけて作成する)
        └─ IDトークン検証実装(/oauth2/v2.1/verify)
              └─ create_checkout_session()の実接続(3節の`_verify_id_token_not_implemented`解消)
                    └─ Stripeアカウント開設・本番APIキー取得(LIFF側と並行して進められる、相互依存なし)
                          └─ Webhookエンドポイント登録(Cloud Functionのデプロイ先URLが確定して初めて登録可能)
                                └─ stripe_webhook.pyへの実キー・署名シークレット設定
Googleフォーム+GAS Webhook(申込受付、上記とは独立した経路)
  └─ line-user-id-linking-design.mdの連携コード方式(フォーム送信→LINE初回メッセージでコード送付)
        └─ LINE公式アカウント開設が前提(上記と合流)
```

要点: **LINE公式アカウント開設が最初の前提**であり、LIFFアプリ登録・連携コード送付の
いずれもこれに依存する。Stripeアカウント開設はLINE側と相互依存が無く並行して進められるが、
**Webhookエンドポイント登録はCloud FunctionのデプロイURLが先に確定している必要がある**ため、
「Stripeアカウント開設」→「Cloud Functionデプロイ」→「Webhookエンドポイント登録」の順を
守る必要がある。

## 4. 記載漏れの発見: LIFFアプリ登録がpending-approval.mdに未記録

フェーズ259で「実Stripeアカウント接続」がpending-approval.mdへの記載漏れだったことを
発見・是正したが、本フェーズで棚卸しした結果、**LIFFアプリ登録自体も同様に記載漏れ**で
あることが判明した(checkout-initiation-flow-design.md「残課題」1点目に「オーナー承認待ち」
と記述されて以来、フェーズ98から一度もpending-approval.mdへの記録が行われていなかった)。
本フェーズでpending-approval.mdへ新規記録した。

## 5. 承認が得られた場合の着手順序(提案)

1. LINE公式アカウント開設(Basic ID確定)
2. LIFFアプリ登録(1に依存)、Googleフォーム+GAS Webhook(1に依存、LIFFとは並行可)
3. IDトークン検証実装、連携コード送付処理のデプロイ(2の完了後)
4. Stripeアカウント開設・本番APIキー取得(1〜3と並行して進めてよい)
5. Cloud Functions(`create_checkout_session`・`stripe_webhook`)の実デプロイ
6. StripeダッシュボードでのWebhookエンドポイント登録(5のデプロイURL確定後)
7. 結合テスト(LIFF経由の決済開始→Stripe Checkout→Webhook受信→LINEへの結果通知)

## 6. 残課題

- 実際の着手はオーナー承認後。本ドキュメントは順序整理のみで、コード変更は無い。
- `success_url`/`cancel_url`の実LPドメイン確定(別途承認待ち)も5の前に必要になるが、
  LP実装自体は本ventureの範囲外のため、着手順序への影響は本ドキュメントでは扱わない。
