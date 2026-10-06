# 決済時の本人確認方式の検討(LIFF非依存)

作成日: 2026-10-06 23:00 UTC(フェーズ95)

launch-readiness-checklist.md(フェーズ94)「次回候補」(3)で残課題として記録されていた
「LIFF非依存の決済時本人確認方式の検討」に着手する。

## 1. 問題設定

course-set-pasha・kura-pashaはStripe Checkout Session発行時に`client_reference_id`へ
LINE友だち追加時に発行された内部`user_id`を埋め込み、Webhook受信時(`checkout.session.
completed`)に`client_reference_id`と`customer`(stripe_customer_id)を紐付ける設計
(stripe-customer-id-linking-design.md参照)を採用している。この方式が成立する前提は、
`user_id`自体がLINEプラットフォーム側で認証済み(LIFF ID トークン検証、またはLINE
Messaging APIのWebhook配信元として保証される)という点にある。つまり「誰がCheckout
Sessionを起票したか」をLINEというプラットフォームが保証してくれる。

本venture(forklift-pasha)はtech-stack.md(フェーズ70)で入力チャネルを汎用Webフォーム
(LINE非依存)に暫定決定したため、このLINE側の保証が存在しない。firestore-data-model.md
(フェーズ70)は`operator_id`の軸を「メールアドレス(またはフォーム入力時に発行する
ランダムなoperator_id)」の両論のまま未確定にしていたが、素朴にメールアドレスそのものを
`client_reference_id`に使う方式には次の問題がある。

- 入力されたメールアドレスの到達性(本人がそのアドレスを実際に使えるか)を一度も確認せずに
  `fleet_operator`ドキュメントを特定・課金紐付けしてしまうと、第三者が他人のメール
  アドレスを入力してCheckout Sessionを起票できてしまう(なりすまし)。
- メールアドレス文字列は推測・総当たりが可能な識別子であり、Stripe側の`client_reference_id`
  に生のメールアドレスを渡す設計は、他venture(LINE `user_id`)が持つ「推測不能な識別子」
  という性質を欠く。

## 2. 方針: アクセストークン方式

LINEの`user_id`が持つ「推測不能で、プラットフォームが発行した識別子」という性質を、
メールアドレスではなく**サーバー側で発行するランダムなアクセストークン**で代替する。
firestore-data-model.md(フェーズ70)が両論としていた`operator_id`の軸は、本フェーズで
**ランダム発行方式に確定**する(メールアドレスはあくまで配布先の連絡手段として
`fleet_operator`ドキュメント内に保持するが、識別子そのものには使わない)。

1. **初回登録**: Webフォームの初回利用時にメールアドレスの入力を求める。サーバー側で
   推測不能なランダム文字列(UUID等)を`operator_id`として新規発行し、
   `fleet_operator/{operator_id}`を作成する(`email`フィールドに入力値を保持。
   pricing-plan.mdの無料トライアル開始もこの時点)。
2. **アクセスURLの配布**: `https://<ドメイン>/f/{operator_id}`形式のアクセスURLを、
   入力されたメールアドレス宛に送信する(以降の点検メモ入力・プラン確認・申込はすべて
   このURL経由とし、ログインID/パスワードは発行しない設計。aircon-pasha等の既存シリーズと
   同様、本venture固有の運用負荷を増やさないシンプルな方針を踏襲)。
3. **到達性確認の設計判断**: 本venture単体では明示的な「確認リンクのクリック」ステップは
   設けない簡易設計とする。入力されたメールアドレスが実在せず誤記だった場合、アクセスURLが
   届かず本人がそもそも本venture を使い始められない(=実質的に到達性が利用開始の前提条件に
   なっている)ため、line-reservation-ai等のような明示的なダブルオプトイン確認ステップを
   追加するコストに対し効果が薄いと判断した。なお本判断は机上のものであり、実際のメール
   送信・配布自体はメール連携接続後の運用(送信直前の毎回オーナー確認を含む、既存の承認済み
   運用方針。pending-approval.md記載の既存事例と同型であり、本設計は新たな承認種別を追加
   するものではない)に従う前提は変わらない。

## 3. Checkout Session発行・Webhook紐付け

course-set-pasha/stripe-customer-id-linking-design.md(フェーズ97)と同型の設計を、
`user_id`を`operator_id`(本venture発行のアクセストークン)に置き換えて踏襲する。

- Checkout Session作成時、`client_reference_id = operator_id`・`customer_email`に
  `fleet_operator.email`を設定する(`customer_email`はStripe Checkout画面上で本人への
  確認表示として使うのみで、識別子としては使わない)。
- Webhook側は`checkout.session.completed`の`client_reference_id`(=operator_id)と
  `customer`(=stripe_customer_id)を`fleet_operator/{operator_id}`へ書き込む。
  `operator_id`自体がアクセスURL経由でのみ渡される推測不能な識別子であるため、
  「第三者が他人のoperator_idを類推してCheckout Sessionを起票する」リスクはLINEの
  `user_id`方式と同程度まで低減される。

## 4. 残課題

- アクセストークン(`operator_id`)が漏洩した場合の再発行機能は未設計(実装時の課題)。
- メールアドレス変更時の再送・旧トークン失効の扱いは未設計(実装時の課題)。
- 実際のメール送信実装(アクセスURLの配布)自体はメール連携接続後の作業であり、
  本フェーズでは机上設計のみ(pending-approval.mdへの新規追記は不要。既存のメール送信
  運用方針〈接続後、送信直前確認〉の範囲内)。
- Firestoreデータモデルの実ファイル化時、firestore-data-model.mdの該当箇所
  (`operator_id`の割り振り方針)を本設計に合わせて更新する必要がある(次回候補)。

最終更新: 2026-10-06 23:00 UTC(フェーズ95: launch-readiness-checklist.md次回候補(3)
「LIFF非依存の決済時本人確認方式の検討」に着手し、アクセストークン方式を設計。
course-set-pasha/stripe-customer-id-linking-design.mdと同型のclient_reference_id紐付けを
踏襲しつつ、operator_idの軸をランダム発行方式に確定した。コード変更なし)
