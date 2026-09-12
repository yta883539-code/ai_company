# サブスク課金データモデルの配置設計(フェーズ46)

作成日: 2026-09-08(フェーズ46)

## 背景・気付いた未整理点

pricing-plan.md(初回メモ)で月額3プラン(ライト/スタンダード/複数職人)・従量課金・
無料トライアル条件までは仮決めしたが、実際にStripeサブスクリプションと紐付ける際に
「どのドキュメントにどの課金関連フィールドを持たせるか」というデータモデルが本venture
では一度も設計されていなかった。他3venture(aircon-pasha・course-set-pasha・
line-reservation-ai)はいずれも「1事業者=1LINEアカウント=1契約者」の構造のため、
`user_profile/{user_id}`に`stripe_customer_id`・`subscription_status`等を直接持たせて
問題ない。しかし本ventureは「複数職人プラン」で複数のuser_idが1つの
`craftsman_workshop/{workshop_id}`を共同利用し、支払い名義人は
`contractor_user_id`一人に限定される(subscription-cancellation-flow-design.md
「複数職人プラン固有の論点」)。この構造の違いを反映しないまま他venture同様に
`user_profile`側へ課金フィールドを持たせると、契約者交代(contractor-transfer-design.md)
発生時に決済情報をどちらのuser_idへ引き継ぐかという整合性問題が生じる。本ファイルは
この配置を確定する。

## 1. 配置の確定: 課金フィールドは`craftsman_workshop`側に持たせる

`user_profile/{user_id}`ではなく`craftsman_workshop/{workshop_id}`に以下を追加する。

```
craftsman_workshop/{workshop_id}:
  ...(既存: contractor_user_id, member_user_ids, plan_id, pending_member_reduction_effective_at, pending_contractor_transfer 等)
  stripe_customer_id: Optional[str]       # 未契約(トライアル中含む)はNone
  subscription_status: str                # "trialing" | "active" | "past_due" | "canceled" のいずれか
  trial_start_at: Optional[datetime]      # pricing-plan.md「無料トライアル条件」の起算点
  current_period_end: Optional[datetime]  # 次回請求日・トライアル終了予定日の判定に使用
```

根拠:

- 決済主体はworkshopそのもの(複数職人が共同利用する1つの契約)であり、個々の
  `user_id`ではない。aircon-pasha等の「1事業者=1契約」構造と異なり、本ventureは
  最初から「1workshop=1契約」構造(craftsman-account-linking-design.md 5節)である
  ため、課金フィールドもworkshop単位で持つほうがモデルとして自然である。
- 契約者交代(contractor-transfer-design.md)が発生しても、`stripe_customer_id`等は
  workshop側のフィールドであるため**何も変更する必要がない**。`contractor_user_id`が
  指し示すuser_idが変わるだけで、Stripe側の顧客・サブスクリプション自体は
  workshopに紐づいたまま継続する。これはaircon-pashaのフェーズ199・200で発見・
  横断確認された「`resolve_linking_code()`の再連携時に`UserProfile`を丸ごと上書きし
  決済関連フィールドが消える」バグと同種の問題を、本ventureでは構造的に発生させない
  設計上の利点でもある(課金情報がuser_profile側に無ければ、そもそも user_profile の
  再生成・上書きの影響を受けない)。
- 複数職人プランの共同利用者(`member_user_ids`)は誰も個別のStripe顧客を持たない。
  Checkout SessionもCustomer Portalも常に`contractor_user_id`が操作主体となる
  (subscription-cancellation-flow-design.md「複数職人プラン固有の論点」の権限モデルと
  一貫する)。

## 2. `user_profile`側に残すもの

`user_profile/{user_id}`には引き続き`workshop_id`のみを持たせ、課金関連フィールドは
一切追加しない。LINEのfollow/unfollow状態(`is_following`相当)は個々のuser_idに
紐づく属性のため、実装時にはuser_profile側に追加する想定だが、これはunfollow時の
メッセージ送達可否の判定に使うものであり課金状態そのものではない
(unfollow-billing-faq.md「複数職人プラン固有の論点」参照: 共同利用者がunfollowしても
契約自体は他メンバー・契約者の下で継続しうるため、courseの課金判定はworkshop側の
`subscription_status`のみを見る設計とする)。

## 3. `resolve_user_id`の解決先の違い

他3venture(course-set-pasha/stripe-webhook-http-entry-point-design.md等)は
Stripe Webhookの`customer.subscription.*`イベントを`stripe_customer_id → user_id`で
解決していたが、本ventureでは`stripe_customer_id → workshop_id`として解決する。
Webhook受信時に更新すべきドキュメントも`user_profile/{user_id}`ではなく
`craftsman_workshop/{workshop_id}`になる点が、他venture設計を移植する際の唯一の
構造的な差異になる。

## 4. 未検証・残課題

- (対応済み 2026-09-08 21:00 UTC・フェーズ49): `WorkshopStoreProtocol`への
  `get_stripe_customer_id`/`set_stripe_customer_id`/`get_subscription_status`/
  `set_subscription_status`メソッド追加は`prototype/usage_counter_workshop.py`に実装した。
  `subscription_status`は未契約(トライアル中)workshopの初期値を`"trialing"`とし、
  `SUBSCRIPTION_STATUSES`(4値)以外を設定しようとした場合は`InvalidSubscriptionStatusError`
  を送出する。テスト4件追加、全101件パス。
- (対応済み 2026-09-12 12:00 UTC・フェーズ91訂正): Checkout Session発行フロー
  (checkout-initiation-flow-design.md、フェーズ50)、Stripe Webhookの署名検証・
  イベントディスパッチの実装(stripe-webhook-checkout-completed-design.md、フェーズ51、
  `prototype/stripe_webhook.py`の`verify_stripe_signature()`・`receive_stripe_webhook()`)は
  本項目作成の数時間後には完了していたが、本ファイル側の「次の課題として残す」記載が
  未更新のまま残っていた記載漏れだった。`is_trial_period_over`の生成一時停止への配線も
  trial-end-condition-design.md(フェーズ52)で完了済みであることを確認した。
- `current_period_end`フィールドの読み書きメソッド(`WorkshopStoreProtocol`への
  `get_current_period_end`/`set_current_period_end`相当)は引き続き未着手(`prototype/
  stripe_webhook.py`はStripeイベントの`current_period_end`をその場で読み取り解約予約
  通知の文面生成に渡すのみで、永続化はしていないことを確認した)。
- トライアル条件(pricing-plan.md「無料トライアル条件(仮)」: 初回生成成功から1回無料、
  または30日間のいずれか早い方)を`trial_start_at`起算でどう判定するかの具体的な関数設計
  (他venture`trial-end-condition-a-*-design.md`相当)は、実際にはtrial-end-condition-
  design.md(フェーズ52、`is_trial_period_over`)として対応済みであることを確認した
  (これも本ファイル側の記載漏れだった)。
- 実際のStripeアカウント接続・Webhookエンドポイントのデプロイは引き続きオーナー承認待ちの
  範囲(pending-approval.md参照)。

最終更新: 2026-09-12 12:00 UTC(フェーズ91: 記載漏れ訂正)
