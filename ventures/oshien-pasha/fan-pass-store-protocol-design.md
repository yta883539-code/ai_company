# FanPassStoreProtocol設計(フェーズ39)

フェーズ38の次回候補(2)「fan_passドキュメント自体のストア(`FanPassStoreProtocol`相当、
`accessToken`・`subscriptionStatus`等firestore-data-model.mdフィールドの読み書き)の
プロトタイプコード化」に対応する。usage-counter-store-protocol-design.md(フェーズ37)の
`UsageCounterStoreProtocol`と同じ位置づけで、実Firestore接続なしにインターフェースのみを
確定する。

## 1. 対象フィールド

firestore-data-model.md 1.1節`fan_pass/{internal_id}`のうち、本プロトコルが読み書きする
のは次の5フィールド(`currentMonthGenerationCount`・`generationCountMonth`は
UsageCounterStoreProtocol側の責務のため対象外)。

- `accessToken` / `email` / `stripeCustomerId` / `stripeSubscriptionId` / `subscriptionStatus`

`currentPeriodEnd`は表示用の参考値のみ(同1.1節)のため、本フェーズでは読み書きメソッドを
設けず次回以降の課題として残す。

## 2. メソッド構成

```
class FanPassStoreProtocol(Protocol):
    def create(
        self, *, email: str, stripe_customer_id: str, stripe_subscription_id: str,
    ) -> tuple[str, str]:
        """新規internal_id発行とaccessToken初回発行を行い、(internal_id, accessToken)を返す。
        subscriptionStatusは"active"で初期化する
        (Checkout Session完了=customer.subscription.created相当のタイミングで呼ばれる想定)。
        """
        ...

    def get_by_access_token(self, access_token: str) -> FanPass | None:
        """`/m/{accessToken}`アクセス時のドキュメント特定(monthly-pass-identity-design.md
        2節)。見つからない場合はNone(例外にしない。アクセスURL自体が無効なケースは
        正常系として呼び出し側で「無効なURL」表示に分岐させるため)。
        """
        ...

    def get_by_stripe_subscription_id(self, stripe_subscription_id: str) -> FanPass | None:
        """`customer.subscription.*`系Webhook受信時の照合(firestore-data-model.md 1.1節
        `stripeSubscriptionId`コメント)。見つからない場合はNone。
        """
        ...

    def update_subscription_status(self, internal_id: str, status: str) -> None:
        """`subscriptionStatus`を更新する("active"|"canceled"のみ許可、fan-pass-canceled-
        access-block-design.md 4節の状態遷移に対応)。internal_id不明時は
        UnknownInternalIdErrorを送出する(usage-counter-store-protocol-design.mdと同じ契約)。
        """
        ...

    def reissue_access_token(self, internal_id: str, *, new_access_token: str) -> None:
        """`accessToken`を新しい値で上書きし、旧トークンを即時失効させる
        (monthly-pass-identity-design.md 3節)。新トークン自体の生成(ランダム文字列生成)は
        呼び出し側の責務とし、本メソッドは上書き保存のみを行う。internal_id不明時は
        UnknownInternalIdErrorを送出する。
        """
        ...
```

`status`・`new_access_token`の値そのものの妥当性検証(形式チェック)は呼び出し側
(API/Webhookハンドラ)の責務とし、本プロトコルは永続化のみを担う方針とした
(usage-counter-store-protocol-design.mdの役割分担方針を踏襲)。

## 3. 未確定・残課題

- ~~`create`の`stripe_customer_id`/`stripe_subscription_id`が既存ドキュメントと重複する場合の
  挙動(Webhookの重複配信対策、冪等性)は未検討。~~ → フェーズ40で対応済み(下記4節)。
- ~~`email`を使った検索(`find_by_email`)はクロスデバイス再発行フローの入口として必要になる
  可能性があるが、`monthly-pass-identity-design.md`3節が「識別子そのものには使わない」と
  明記しているため、本フェーズでは優先度を下げてメソッド化を見送った。~~ → フェーズ41で
  再検討済み(email-lookup-necessity-review.md)。再発行フローはStripe API側の顧客検索
  (`customers.list(email=...)`)→サブスクリプション検索(`subscriptions.list(customer=...)`)
  経路で`stripeSubscriptionId`を得て、既存の`get_by_stripe_subscription_id`で`fan_pass`
  ドキュメントを特定する方針を確定した。Firestore側への`find_by_email`追加は不要と結論。
- 実Firestoreアダプタの作成、実Stripe/GCPプロジェクトの開設はいずれもオーナー承認が必要な
  アクションに該当するため(pending-approval.md既存の承認待ち事項の範囲内)、本フェーズでは
  行わない。

## 4. create()の冪等性(フェーズ40)

`stripe_subscription_id`をdedupキーとし、既に同一`stripe_subscription_id`で登録済みの
ドキュメントが存在する場合は新規発行を行わず、既存の`(internal_id, accessToken)`を
そのまま返す。Stripe Webhookの`customer.subscription.created`相当イベントが重複配信
された場合でも、同一サブスクリプションに対して複数の`fan_pass`ドキュメント・複数の
`accessToken`が発行されてしまう不整合を防ぐ。

`stripe_customer_id`単体(同一顧客が解約後に新規サブスクリプションで再加入した場合等)は
dedup対象としない。この場合`stripe_subscription_id`が新しい値になるため、意図的に
新規ドキュメントとして扱う(再加入時に新しい`accessToken`を発行する想定、
fan-pass-canceled-access-block-design.mdの再加入フローと整合)。

実コード化はprototype/fan_pass_store.pyの`create()`冒頭で
`_internal_id_by_subscription_id`を先に引く形で行った
(test_fan_pass_store.pyに`test_create_is_idempotent_on_duplicate_webhook_delivery`を追加、
3アサーション追加・全16件PASS)。

最終更新: 2026-10-31 19:00 UTC(フェーズ40: `create`のWebhook重複配信時の冪等性を
stripe_subscription_idキーで実装、3節の残課題を解消)

追記(フェーズ41、2026-10-31 21:00 UTC): 3節の`find_by_email`要否を再検討し、Firestore側への
メソッド追加は不要と結論した。詳細はemail-lookup-necessity-review.md参照。
