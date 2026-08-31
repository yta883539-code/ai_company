#!/usr/bin/env python3
"""user-account-linking-design.md 4節・subscription-cancellation-flow-design.md
「当月生成回数上限の適用方法」で設計した、Stripe `customer.subscription.*`イベント受信の
たびに`user_profile/{user_id}.current_plan_id`を最新のプランへ同期する処理。

位置づけ:
- `UserProfile.current_plan_id`フィールド自体は既にuser_id_linking.pyに追加済みだったが
  (design記載どおり「未契約時はnull」の既定値`None`)、実際にどこからも書き込まれない
  まま放置されていた配線漏れを本フェーズで発見・解消した。user-account-linking-design.md
  4節は「`customer.subscription.*`受信のたびに更新する」、subscription-cancellation-flow-
  design.mdは「`usage_counter`の上限値参照先をStripe Webhookで受信した最新のプランIDに
  紐づける」とそれぞれ確定済みだったが、`stripe_dispatch.py`の`dispatch_stripe_event()`は
  `customer.subscription.created/updated`受信時に削除候補フラグの解除のみを行い、
  プランIDの同期は一度も実装されていなかった(deletion_candidate.pyと同じ「Protocol/
  Callableの差し替えで実接続を後回しにする」パターンを踏襲した薄いモジュールとして
  本フェーズで新規実装する)。
- Stripeのsubscription objectはプラン識別に`items.data[].price.id`(Stripe側が採番する
  実際のPrice ID)を持つが、本ventureは実Stripeアカウント未接続のため実際のPrice IDは
  存在しない。Stripeは`lookup_key`という自由に設定できる識別子をPriceに付与できるため、
  本ventureのPrice作成時(実アカウント接続後)にpricing-plan.mdの3プランへ固定の
  lookup_keyを割り当てる前提で設計する(lookup_key自体の命名は実アカウント接続なしでも
  机上で確定できる、実接続を要する作業ではない)。
- `customer.subscription.deleted`受信時(解約確定)は、subscription-cancellation-flow-
  design.md「解約フロー」の「次回生成リクエスト時は無料プラン相当(生成不可)として扱う」
  という結論に合わせ、`current_plan_id`を`None`(未契約)へ戻す
  `clear_current_plan_on_subscription_deleted()`を用意する。deletion_candidate.pyの
  削除候補化ロジックとは独立した処理であり、互いに依存しない。

設計の参照元: user-account-linking-design.md 4節、subscription-cancellation-flow-design.md
「当月生成回数上限の適用方法」節。
"""

from __future__ import annotations

from typing import Optional, Protocol

# pricing-plan.md「料金プラン」表準拠(cloud_function_webhook.pyのPLAN_MONTHLY_LIMITS等と
# 同じプラン名表記)。Price作成時にこのlookup_keyを設定する想定の仮称であり、実アカウント
# 接続時に実際の値を確定させる(実接続自体はオーナー承認待ちの範囲、pending-approval.md参照)。
LOOKUP_KEY_TO_PLAN_ID = {
    "aircon_pasha_small": "スモール",
    "aircon_pasha_standard": "スタンダード",
    "aircon_pasha_busy": "繁忙期対応",
}


class CurrentPlanStoreProtocol(Protocol):
    """`user_profile/{user_id}.current_plan_id`への書き込みのみを表す薄いインターフェース
    (payment_failure.pyの`PaymentFailureStoreProtocol`と同じ位置づけ)。専用のInMemoryストアは
    新設せず、`user_id_linking.InMemoryUserProfileStore`が構造的に(duck typing)満たす。"""

    def set_current_plan_id(self, user_id: str, plan_id: Optional[str]) -> None:
        ...


def resolve_plan_id_from_subscription(data_object: dict) -> Optional[str]:
    """Stripe `customer.subscription.created`/`.updated`イベントの`data.object`から
    プランID(pricing-plan.mdの「スモール」「スタンダード」「繁忙期対応」のいずれか)を
    解決する。

    `items.data[0].price.lookup_key`が既知のキーの場合のみ解決し、以下はいずれもNoneを
    返す(呼び出し元は`current_plan_id`を変更せず現状維持する安全側の設計):
    - `items`・`data`(配列)・`price`・`lookup_key`のいずれかが欠落・想定外の型
    - `lookup_key`が`LOOKUP_KEY_TO_PLAN_ID`に存在しない未知の値
    """
    items = data_object.get("items")
    if not isinstance(items, dict):
        return None
    item_list = items.get("data")
    if not isinstance(item_list, list) or not item_list:
        return None
    first_item = item_list[0]
    if not isinstance(first_item, dict):
        return None
    price = first_item.get("price")
    if not isinstance(price, dict):
        return None
    lookup_key = price.get("lookup_key")
    if not isinstance(lookup_key, str):
        return None
    return LOOKUP_KEY_TO_PLAN_ID.get(lookup_key)


def sync_current_plan_on_subscription_event(
    store: CurrentPlanStoreProtocol, user_id: str, data_object: dict
) -> Optional[str]:
    """`customer.subscription.created`/`.updated`受信時に呼ぶ。プランIDを解決できた
    場合のみ`current_plan_id`へ書き込み、解決できたplan_idを返す(呼び出し元が同期の
    成否を区別できるようにする)。解決できない場合は`store`に一切触れず、既存の
    `current_plan_id`をそのまま維持してNoneを返す。"""
    plan_id = resolve_plan_id_from_subscription(data_object)
    if plan_id is None:
        return None
    store.set_current_plan_id(user_id, plan_id)
    return plan_id


def clear_current_plan_on_subscription_deleted(
    store: CurrentPlanStoreProtocol, user_id: str
) -> None:
    """`customer.subscription.deleted`受信時に呼ぶ。design「解約フロー」の結論(解約確定後は
    無料プラン相当=未契約扱い)に沿って`current_plan_id`を`None`へ戻す。既に`None`の場合も
    そのまま`None`を書き込むだけの冪等な操作。"""
    store.set_current_plan_id(user_id, None)
