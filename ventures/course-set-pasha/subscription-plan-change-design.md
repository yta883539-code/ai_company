# サブスクリプションプラン変更(アップグレード/ダウングレード)時のplan更新設計

作成日: 2026-09-03(フェーズ153)

## 0. 発見された経緯(残課題棚卸し)

checkout-session-plan-selection-design.md(フェーズ152)「残課題」に、以下の記載が
残っていた。

> ダウングレード・アップグレード時(`subscription-cancellation-flow-design.md`が扱う
> プラン変更フロー)に`user_profile/{user_id}.plan`を更新する経路は未設計のまま残る
> (現状は`checkout.session.completed`、すなわち新規契約時のみ書き込む設計)。
> Stripeの`customer.subscription.updated`イベント(プラン変更時に発火)からの`plan`
> 更新は次回以降の課題として残す。

フェーズ152時点では`checkout.session.completed`(新規契約)受信時のみ`user_profile_store.
set_plan()`を書き込んでおり、契約中のユーザーがStripeカスタマーポータル(`portal_session.py`、
フェーズ148・149)経由でプランを変更しても、`user_profile`側の`plan`フィールドは古い値の
ままになってしまうギャップがあった。`prototype/stripe_webhook.py`の`dispatch_stripe_event()`
は既に`customer.subscription.updated`イベントを受信して`_REACTIVATED_STATUSES`
(`active`/`trialing`)判定による削除候補クリアを行っているため、本ドキュメントはこの
既存の受信経路にプラン更新ロジックを追加する設計・実装を記録する。

## 1. 方針

1. Stripeの`customer.subscription.updated`イベントの`data.object`(Subscriptionオブジェクト)
   には、`items.data[].price.id`として現在契約中のPrice IDがそのまま含まれる
   (Stripeの標準レスポンスに含まれるフィールドであり、`line_items`のexpand等、
   `checkout.session.completed`のときのような追加API呼び出しは不要)。
2. `checkout_session.PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`(フェーズ152)を反転させた
   `STRIPE_PRICE_ID_TO_PLAN_PLACEHOLDER`を新設し、Price IDから既知のプラン名
   ("ライト"/"スタンダード"/"セッター複数")へ逆引きする。
3. pricing-plan.mdの3プランはいずれも単一line item構成が前提のため、
   `items.data`の先頭要素のみを見る(複数line item構成への対応は本ventureの現行の
   料金設計上不要であり、必要になった時点で別途設計する)。
4. `dispatch_stripe_event()`の`customer.subscription.updated`分岐において、
   `user_profile_store`が渡されている場合のみプラン更新を試み、`items`欠落・
   `price.id`が未知の値の場合は何も書き込まない(安全側。既存の削除候補クリア判定
   〈ステータスによる分岐〉には影響を与えない独立した処理とする)。
5. プラン更新自体は、既存のステータス判定(`_REACTIVATED_STATUSES`によるactive/trialing
   限定の削除候補クリア)より前に、ステータスに関係なく評価する。契約中のプラン変更は
   通常ステータスが`active`のまま行われる一方、将来的にステータス遷移と同時にプランが
   変わるイベントが来ても取りこぼさないようにするため。
6. 新規契約時(`checkout.session.completed`)の書き込み経路(フェーズ152)とは完全に独立した
   経路とする。両者とも最終的に`user_profile_store.set_plan()`という同じ書き込み先へ
   収束するため、`user_profile/{user_id}.plan`は「直近に処理されたイベントの値」を保持する
   単純な仕様のままで一貫性が保たれる。

## 2. 実装

- `prototype/checkout_session.py`: `STRIPE_PRICE_ID_TO_PLAN_PLACEHOLDER`
  (`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の反転辞書、機械的に生成)を新設。
- `prototype/stripe_webhook.py`:
  - `checkout_session.STRIPE_PRICE_ID_TO_PLAN_PLACEHOLDER`をimport。
  - `_resolve_plan_from_subscription_updated(data_object)`を新設。`items.data[0].
    price.id`を取り出し、既知のPrice IDであればプラン名を、そうでなければ`None`を返す
    (`items`欠落・非dict・空配列・`price`欠落等はいずれも`None`、例外を送出しない)。
  - `StripeDispatchResult`に`plan_updated_user_ids`フィールドを追加。
  - `dispatch_stripe_event()`の`customer.subscription.updated`分岐冒頭で、
    `user_profile_store`指定時に上記関数でプランを解決し、解決できた場合のみ
    `user_profile_store.set_plan(user_id, plan)`を呼び出し`plan_updated_user_ids`に
    `user_id`を追加する。既存のステータス判定による削除候補クリア処理はそのまま残す。

## 3. 残課題

- 実Stripe Price ID確定(`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の実値差し替え)は、
  フェーズ152から引き続き実Stripeアカウント接続(オーナー承認待ち、pending-approval.md
  参照)後の課題として残る。実Price IDが確定するまでは、本設計の逆引きマップも
  プレースホルダ値のまま連動して更新する必要がある。
- 実際のStripeカスタマーポータルでのプラン変更操作によるイベント配信(`items`の実際の
  形状・複数line item化の有無を含む)は、実Stripe接続後の検証課題として残る
  (本ドキュメントの設計・実装はあくまで机上検証)。
- (解消済み・フェーズ続き154: `customer.subscription.updated`が「プラン変更を伴わない」
  更新(支払い方法変更・試用期間延長等、Price IDが変わらないケース)で届いた場合に
  `set_plan()`が無駄に呼ばれる件は、`user_profile_store.get_plan(user_id)`と解決した
  `plan`を比較する差分チェックを`dispatch_stripe_event()`の`customer.subscription.updated`
  分岐に追加して解消した。値が一致する場合は`set_plan()`を呼び出さず、
  `plan_updated_user_ids`にも含めない。テスト1件追加
  〈`test_subscription_updated_with_unchanged_plan_skips_write`〉、venture全体518件
  全件パス・schema検証9件パスを確認済み。実運用での実際の書き込み頻度・
  `customer.subscription.updated`の実発火頻度自体は引き続き実Stripe接続後の検証課題
  として残る)
