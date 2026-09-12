#!/usr/bin/env python3
"""subscription-plan-sync-design.md(フェーズ93)。Stripe `customer.subscription.updated`
受信のたびに`craftsman_workshop/{workshop_id}.plan_id`を実際のプランへ同期する処理。

位置づけ:
- `usage_counter_workshop.py`の`get_plan_id()`は`checkout.session.completed`受信時に
  `workshop_store.set_plan()`(stripe_webhook.py 186行目)で一度書き込まれた値をそのまま
  読むだけで、Stripeカスタマーポータル経由のプラン変更(アップグレード/ダウングレード)を
  一度も反映しない配線漏れが本フェーズまで残っていた。subscription-cancellation-flow-
  design.md「ダウングレード(プラン変更)フロー」は「上限判定にのみ新プラン(下位プラン)の
  上限値を即時適用する」と確定済みだったが、この「即時適用」を実現する同期処理自体が
  実装されていなかった。
- aircon-pashaがフェーズ177(user-account-linking-design.md 4節)で発見・実装した
  `current_plan_id`未配線と同種のギャップであり、aircon-pashaフェーズ208の申し送り
  (「kura-pasha・line-reservation-aiへの横展開要否は次回以降の棚卸し候補」)を受けて
  本venture側を確認した結果、aircon-pasha側の対応(フェーズ208、差分チェックによる
  無駄な書き込み回避)よりも手前の段階、すなわち同期処理そのものが未実装という
  より根本的なギャップだったと判明した。本フェーズでは同期処理を新設し、差分チェック
  (aircon-pashaフェーズ208の教訓)も最初から組み込む。
- 本ventureは`WorkshopStoreProtocol.get_plan_id()`が`Optional[str]`ではなく`str`を返す
  (未契約状態が存在しない、workshop作成時に必ず暫定plan_idが設定される設計、
  craftsman-account-linking-design.md フェーズ66追記7節)ため、aircon-pashaの
  `CurrentPlanStoreProtocol`(`Optional[str]`)とは異なり、`get_plan_id()`が
  `KeyError`を送出する可能性(plan_id未設定のworkshop)も差分判定の一部として扱う
  (未設定は「異なる」とみなし常に書き込む)。
- 本ventureは`customer.subscription.deleted`受信時に`plan_id`を特別な値へ戻す必要はない
  (解約後もworkshop自体は残り、次回契約時にcheckout.session.completedが新たな
  plan_idを設定し直すため。subscription_cancellation_notification.pyの解約処理は
  `subscription_status`のみを変更し`plan_id`には触れない、design 3節参照)。したがって
  aircon-pashaの`clear_current_plan_on_subscription_deleted()`に相当する処理は
  本ventureには不要と判断し、実装しない。

設計の参照元: subscription-plan-sync-design.md、subscription-cancellation-flow-design.md
「ダウングレード(プラン変更)フロー」節。
"""

from __future__ import annotations

from typing import Optional, Protocol

# pricing-plan.md「料金プラン」表準拠(usage_counter_workshop.pyのPLAN_LIMITSと同じ
# plan_id表記)。Price作成時にこのlookup_keyを設定する想定の仮称であり、実アカウント
# 接続時に実際の値を確定させる(実接続自体はオーナー承認待ちの範囲、pending-approval.md
# 参照)。aircon-pashaの命名規則(`<venture>_<plan>`)にそのまま揃えた。
LOOKUP_KEY_TO_PLAN_ID = {
    "kura_pasha_light": "light",
    "kura_pasha_standard": "standard",
    "kura_pasha_multi_craftsman": "multi_craftsman",
}


class PlanStoreProtocol(Protocol):
    """`craftsman_workshop/{workshop_id}.plan_id`への読み書きを表す薄いインターフェース
    (`usage_counter_workshop.WorkshopStoreProtocol`のうちplan_id関連の2メソッドのみを
    要求する部分集合。`InMemoryWorkshopStore`が構造的に(duck typing)満たす)。"""

    def get_plan_id(self, workshop_id: str) -> str:
        ...

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        ...


def resolve_plan_id_from_subscription(data_object: dict) -> Optional[str]:
    """Stripe `customer.subscription.created`/`.updated`イベントの`data.object`から
    プランID(`"light"`/`"standard"`/`"multi_craftsman"`のいずれか)を解決する。

    `items.data[0].price.lookup_key`が既知のキーの場合のみ解決し、以下はいずれもNoneを
    返す(呼び出し元は`plan_id`を変更せず現状維持する安全側の設計):
    - `items`・`data`(配列)・`price`・`lookup_key`のいずれかが欠落・想定外の型
    - `lookup_key`が`LOOKUP_KEY_TO_PLAN_ID`に存在しない未知の値

    aircon-pasha/prototype/subscription_plan_sync.pyの同名関数と同一アルゴリズム
    (lookup_keyの辞書のみがventure固有)。
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


def sync_plan_on_subscription_event(
    store: PlanStoreProtocol, workshop_id: str, data_object: dict
) -> Optional[str]:
    """`customer.subscription.created`/`.updated`受信時に呼ぶ。プランIDを解決できた
    場合は解決できたplan_idを返す(呼び出し元が同期の成否を区別できるようにする)。
    解決できない場合は`store`に一切触れず、既存の`plan_id`をそのまま維持してNoneを
    返す。解決できたplan_idが既存の`plan_id`と同じ場合は、支払い方法変更等
    price.lookup_keyが変わらない`.updated`イベントでの無駄な書き込みを避けるため
    `set_plan`を呼ばない(aircon-pashaフェーズ208と同種の差分チェック)。

    `get_plan_id`が`KeyError`を送出する場合(plan_id未設定のworkshop、通常発生しない
    想定だが安全側として扱う)は「既存値と異なる」とみなし、常に書き込む。
    """
    plan_id = resolve_plan_id_from_subscription(data_object)
    if plan_id is None:
        return None
    try:
        current_plan_id: Optional[str] = store.get_plan_id(workshop_id)
    except KeyError:
        current_plan_id = None
    if current_plan_id != plan_id:
        store.set_plan(workshop_id, plan_id)
    return plan_id
