# デポジット決済(将来オプション)とサブスク課金の決済代行サービス一本化検討

作成日: 2026-09-07

## 背景
subscription-billing-cost-estimate.md「結論・次のステップ候補」に残っていた課題
「deposit-payment-research.md(顧客からのデポジット徴収)と本ドキュメント(オーナーからの
サブスク徴収)は課金の方向・対象者が異なる別経路であるため、将来同一の決済代行サービスに
一本化できるかの検討」に対応する。checkout-initiation-flow-design.md・stripe-webhook-*.md
群により、サブスク課金(オーナー→本サービス)の決済代行サービスは既にStripe
(Stripe Checkout `mode=subscription` + Stripe Billing)に確定していることを確認した。
本ドキュメントでは、deposit-payment-research.mdが候補に挙げていたLINE Pay/Stripe/PAY.JP・
komoju等のうち、Stripeへの一本化が可能かを検討する。

## 資金の流れの違い(核心の論点)
両者は「同じStripeを使えるか」以前に、資金の受取人が異なる。

| 経路 | 支払う人 | 受け取る人 | 性質 |
|---|---|---|---|
| サブスク課金 | 店舗オーナー | 本サービス(プラットフォーム運営者) | 本サービスの売上そのもの |
| デポジット | 来店客(エンドカスタマー) | 各店舗オーナー | 店舗の売上(施術料金の一部前受け)。本サービスは仲介するだけで受取人ではない |

サブスク課金は「本サービスが加盟店契約したStripeアカウントで、自分自身への支払いを
受ける」通常のStripe Checkout/Billingで完結するのに対し、デポジットは
「本サービスのLINEアプリ上の導線で決済を発生させつつ、資金は各店舗オーナーの口座へ
着金させる」必要があり、単純に同じStripeアカウント・同じ`stripe.checkout.Session.create()`
呼び出しを流用することはできない。

## 一本化の技術的な選択肢
デポジットを「本サービスと同じStripe」に一本化する場合、Stripe Connect(プラットフォーム
向けマルチアカウント機能)の導入が必要になる。

| 方式 | 概要 | 店舗オーナー側の追加手続き | 本サービスの開発負荷 |
|---|---|---|---|
| Stripe Connect (Standard) | 各店舗オーナーが自分のStripeアカウントを持ち、本サービスはCheckout Session作成時に`transfer_data[destination]`等で送金先を指定するのみ。 | 店舗オーナー自身がStripeアカウント開設・本人確認(KYC)を行う必要がある。 | サブスク課金の既存Stripe実装(checkout-initiation-flow-design.md)と決済APIの型が共通のため、Connect用パラメータの追加のみで済み、追加の実装負荷は比較的小さい。 |
| Stripe Connect (Express/Custom) | 本サービスが店舗オーナーのオンボーディング画面まで用意し、KYCの一部を代行。 | 店舗オーナー側の手続きは簡略化されるが、必要書類提出自体は必須。 | オンボーディングUI・本人確認フロー・Connectアカウントの状態管理(審査中/有効/停止等)を本サービス側で新たに実装する必要があり、開発負荷は大きい。 |
| 別決済代行サービス(PAY.JP/komoju等)を店舗ごとに契約 | deposit-payment-research.mdの原案どおり、店舗オーナーが個別に契約。 | 店舗オーナーが自分で決済代行サービスと契約(業種によってはStripeより審査が通りやすいとされる場合がある)。 | 本サービスはサブスク課金用Stripeとは別の決済代行サービスのAPI・Webhookを新たに実装する必要があり、保守対象の決済基盤が2系統に増える。 |

## 結論
- 技術的には Stripe Connect (Standard) を採用すれば、決済代行サービス自体をStripe1系統に
  一本化することは可能。サブスク課金と同じStripe API・同じWebhook基盤
  (stripe-webhook-event-dispatch-design.md等)の知見を流用できる分、保守対象を1系統に
  絞れるメリットは大きい。
- ただし一本化のメリットは「決済代行サービスの契約先・API・Webhook基盤を1つにまとめられる」
  という開発・運用面の話にとどまり、店舗オーナー側の負担(Stripeアカウント開設・KYC)は
  デポジット機能導入時に新たに発生する点はStripe Connectを使っても他の決済代行サービスを
  使っても避けられない。したがって一本化の可否は決済代行サービスの選定基準としては有利な
  材料になるが、「デポジット機能自体をMVPに含めるかどうか」の判断(現時点では見送り、
  precheck-strengthening.md・deposit-payment-research.mdの結論を維持)には影響しない。
- deposit-payment-research.mdの決済方式比較表に「Stripe Connect (Standard)採用によりサブスク
  課金と決済代行サービスを一本化可能。ただし店舗オーナー側のStripeアカウント開設・KYCは
  別途必要」という補足を追記した。

## 残る課題
- Stripe Connectの加盟店契約・店舗オーナーへのオンボーディング案内は、実際のStripeアカウント
  接続・契約行為であり、オーナー承認が必要なアクションに該当するため、デポジット機能自体を
  MVPに含める判断が下された後の課題として残る。
- 店舗オーナーが個人事業主である場合のStripe Connect KYC要件(本人確認書類の種類等)の詳細は
  未調査のまま残る。
