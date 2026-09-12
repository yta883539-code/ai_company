#!/usr/bin/env python3
"""subscription-plan-sync-design.md(フェーズ続き220)で設計した、Stripe
`customer.subscription.updated`イベント受信のたびに`stores/{storeId}.plan`
(store_profile_store.pyの`get_plan()`/`set_plan()`)を最新のプランへ同期する処理。

位置づけ:
- aircon-pasha/prototype/subscription_plan_sync.py(フェーズ177・208)・
  kura-pasha/prototype/subscription_plan_sync.py(フェーズ93)と同じ「Stripe
  Webhookイベントからプランを解決し、差分がある場合のみ書き込む」設計をkura-pashaが
  棚卸しで残した「line-reservation-aiへの横展開要否(店舗単位で複数プランを持つか
  自体を要確認)」に応えて翻案したもの。line-reservation-aiはpricing-plan.mdの
  3プラン(スタータープラン/スタンダードプラン/プロプラン)を店舗単位の契約に持つため
  横展開の前提が成立すると確認できた(3節参照)。
- `store.get_plan()`/`set_plan()`は既にcheckout-session-plan-selection-design.md
  (フェーズ続き181)で実装済みで、`checkout.session.completed`受信時
  (`store_profile_store.handle_checkout_session_completed()`)にのみ書き込まれる。
  Stripeカスタマーポータル経由のプラン変更(アップグレード/ダウングレード)後に
  `customer.subscription.updated`が届いても、`plan`フィールドは一度も更新されない
  配線漏れが残っていた。monthly-booking-limit-notification-design.mdの「予約件数
  通知しきい値」はこの`plan`から`resolve_monthly_booking_limit()`経由で決まるため、
  プラン変更後もオーナーには旧プランのしきい値で通知が届き続ける実害がある
  (同機能は「通知のみ」で予約自体はブロックしない設計〈同design 56行目〉のため、
  実害は通知しきい値のズレにとどまる)。

Stripeのsubscription objectはプラン識別に`items.data[].price.id`を持つが、
line-reservation-aiは実Stripeアカウント未接続で実際のPrice IDが存在しない。
aircon-pasha/kura-pashaと同じく、Priceに付与できる`lookup_key`を使う設計とする
(lookup_key自体の命名は実アカウント接続なしでも机上で確定できる)。
`checkout_session.py`の`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`はCheckout Session作成時に
Price IDを直接指定する既存の仕組みであり、本モジュールが使うlookup_keyとは独立
(実アカウント接続後、同じPriceにPrice ID・lookup_keyの両方を設定すればよい)。

`customer.subscription.deleted`受信時に`plan`を`None`へ戻す処理(aircon-pashaの
`clear_current_plan_on_subscription_deleted()`相当)は本ventureでは実装しない。
`plan`が`None`になると`resolve_monthly_booking_limit()`は`monthly_booking_limit=None`
(通知しきい値機能そのものが無効)を返すだけで、予約受付や会話応答自体は
`suspension_reason`(blocked-but-billing-detection-design.md、本処理とは独立の別
フィールド)側で制御されるため、解約後に`plan`を残しても「無制限扱いになり
サービスが使い続けられてしまう」実害が生じない。次回契約時は`checkout.session.
completed`が新たなplanを設定し直す。

設計の参照元: checkout-session-plan-selection-design.md、monthly-booking-limit-
notification-design.md、customer-subscription-updated-event-routing-design.md、
aircon-pasha/subscription-plan-sync-design.md、kura-pasha/subscription-plan-sync-
design.md
"""

from __future__ import annotations

from typing import Optional, Protocol

# pricing-plan.md「料金プラン」表準拠(store_profile_store.PLAN_MONTHLY_BOOKING_LIMITSの
# キーと同一集合)。Price作成時(実アカウント接続後)にこのlookup_keyを設定する想定の
# 仮称であり、実接続自体はオーナー承認待ちの範囲(pending-approval.md参照)。
LOOKUP_KEY_TO_PLAN = {
    "line_reservation_ai_starter": "スタータープラン",
    "line_reservation_ai_standard": "スタンダードプラン",
    "line_reservation_ai_pro": "プロプラン",
}


class PlanStoreProtocol(Protocol):
    """`stores/{storeId}.plan`への読み書きを表す薄いインターフェース。
    `store_profile_store.StoreProfileStoreProtocol`の`get_plan`/`set_plan`部分のみを
    要求する(duck typing、専用のInMemoryストアは新設しない)。"""

    def get_plan(self, store_id: str) -> Optional[str]:
        ...

    def set_plan(self, store_id: str, plan: str) -> None:
        ...


def resolve_plan_from_subscription(data_object: dict) -> Optional[str]:
    """Stripe `customer.subscription.created`/`.updated`イベントの`data.object`から
    プラン名(pricing-plan.mdの「スタータープラン」「スタンダードプラン」「プロプラン」の
    いずれか)を解決する。

    `items.data[0].price.lookup_key`が既知のキーの場合のみ解決し、以下はいずれもNoneを
    返す(呼び出し元は既存の`plan`を変更せず現状維持する安全側の設計):
    - `items`・`data`(配列)・`price`・`lookup_key`のいずれかが欠落・想定外の型
    - `lookup_key`が`LOOKUP_KEY_TO_PLAN`に存在しない未知の値
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
    return LOOKUP_KEY_TO_PLAN.get(lookup_key)


def sync_plan_on_subscription_event(
    store: PlanStoreProtocol, store_id: str, data_object: dict
) -> Optional[str]:
    """`customer.subscription.created`/`.updated`受信時に呼ぶ。プラン名を解決できた
    場合は解決できたplanを返す(呼び出し元が同期の成否を区別できるようにする)。
    解決できない場合は`store`に一切触れず、既存の`plan`をそのまま維持してNoneを返す。
    解決できたplanが既存の`get_plan(store_id)`と同じ場合は、支払い方法変更等
    price.lookup_keyが変わらない`.updated`イベントでの無駄な書き込みを避けるため
    `set_plan`を呼ばない(aircon-pashaフェーズ208・kura-pashaフェーズ93の教訓を
    踏まえ、本ventureは最初から差分チェックを組み込む)。"""
    plan = resolve_plan_from_subscription(data_object)
    if plan is None:
        return None
    if store.get_plan(store_id) != plan:
        store.set_plan(store_id, plan)
    return plan
