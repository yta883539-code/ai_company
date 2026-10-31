# find_by_email必要性の再検討(フェーズ41)

フェーズ40の次回候補(2)「`email`を使った検索(`find_by_email`)の必要性再検討」に対応する。
fan-pass-store-protocol-design.md 3節が「優先度を下げてメソッド化を見送った」としていた
論点を、再発行フロー(monthly-pass-identity-design.md 3節)の具体的な処理順序に沿って
再検証する。

## 1. `email`が登場する場面の再確認

本venture内で`email`が関わる処理は、monthly-pass-identity-design.md 3節の
「アクセストークンを失った場合の再発行(クロスデバイス対応)」フローのみである。

1. 利用者が「アクセスURLを再送する」ページにメールアドレスを入力する。
2. サーバー側がStripe APIの顧客検索(`customers.list(email=...)`)で該当顧客
   (`stripeCustomerId`)を特定する。
3. 該当`fan_pass`ドキュメントの`accessToken`を新しい値で上書きする(3節3項)。

## 2. 手順2→3の間の接続方法(未記述だった空白の補完)

monthly-pass-identity-design.md 3節は手順2(Stripe顧客特定)から手順3
(`fan_pass`ドキュメントの更新)への接続方法を明記していなかった。考えられる経路は
次の2通り。

- (a) Firestore側で`email`フィールドをキーに`fan_pass`ドキュメントを直接検索する
  (`find_by_email`相当のメソッドが必要)。
- (b) Stripe側で顧客特定後、その顧客の有効なサブスクリプションをStripe API
  (`subscriptions.list(customer=...)`)で取得して`stripeSubscriptionId`を得て、
  既存の`get_by_stripe_subscription_id`(fan-pass-store-protocol-design.md 2節)で
  `fan_pass`ドキュメントを特定する。

(b)であれば、Firestore側に`email`検索用の新規メソッドを追加せずに手順3へ到達できる。

## 3. 結論: (b)を採用し、`find_by_email`はメソッド化しない

以下の理由から(b)を正式な接続方法として確定する。

- `monthly-pass-identity-design.md`2節・3節は一貫して「`email`は識別子そのものには
  使わない」方針を明記しており、Firestore側の検索キーとして`email`を昇格させる(b)案の
  (a)は、その方針と整合しない。
- (b)であれば、`email`に対応する正の照合キーはStripe側の`stripeCustomerId`
  →`stripeSubscriptionId`の経路に閉じ、Firestore側は既存の`get_by_stripe_subscription_id`
  1メソッドのみで再発行フローの手順3を実現できる。`FanPassStoreProtocol`
  (fan-pass-store-protocol-design.md 2節)のメソッド構成に変更は不要。
- `email`フィールド自体は`fan_pass`ドキュメントに記録済み(firestore-data-model.md 1.1節)
  だが、その用途は「決済完了時に収集した参考情報の保持」に限定され、再発行フロー自体は
  Stripe API側の検索で完結する。

一方、(b)の前提として、同一Stripe顧客が有効な月額フリーパスのサブスクリプションを
複数持つことはない(本venture全体がStripe Checkoutの`mode=subscription`を単一プランで
発行する設計のため)という仮定に依拠している。将来複数プラン化する場合は
`subscriptions.list(customer=..., status="active")`の結果が複数件になる可能性を
再検討する必要がある(現状は未着手の仮説のまま)。

## 4. 残課題

- venue-master-draft.mdの各会場アクセス情報精査・会場名表記揺れの名寄せ方法の検討
  (README.md既出の残課題、本フェーズでは対応せず)。
- 本フェーズの結論((b)採用)はmonthly-pass-identity-design.md 3節の処理順序の再確認・
  文書化であり、再発行フロー自体のAPIエンドポイント設計・実コード化は未着手のまま残る。
- 実Stripe API接続・実Firestoreアダプタの作成はオーナー承認が必要なアクションに該当する
  ため(pending-approval.md既存の承認待ち事項の範囲内)、本フェーズでは行わない。

コード実装・外部サービスへの接続は一切行っていない。承認が必要なアクション(支払い・
アカウント作成・外部公開・送信等)は本フェーズでは発生していないためpending-approval.mdへの
新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

最終更新: 2026-10-31 21:00 UTC(フェーズ41: `find_by_email`の必要性を再検討し、再発行フローは
Stripe API側の顧客検索→サブスクリプション検索経路((b))で完結させる方針を確定、Firestore側
への新規メソッド追加は不要と結論した)
