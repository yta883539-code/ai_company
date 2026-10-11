#!/usr/bin/env python3
"""stripe-checkout-plan-id-design.md(フェーズ124)で設計した、plan_id
("light"/"standard"/"fleet"、overage_notifications.PLAN_VEHICLE_LIMIT等と同一の
キー集合)をStripe側のイベントデータから解決し、FleetOperatorStoreへ書き込むための
純粋関数群。実Stripe接続・実Webhookエンドポイント(本venture未着手)は行わない。
"""

from overage_notifications import PLAN_VEHICLE_LIMIT

KNOWN_PLAN_IDS = frozenset(PLAN_VEHICLE_LIMIT.keys())  # 単一の正をoverage_notifications側に置く

# course-set-pasha/checkout-session-plan-selection-design.mdの方式(metadata.plan)を
# 本venture向けに踏襲する。Checkout Session作成時にWebフォームのプラン選択UI(未実装)が
# 付与する`metadata.plan`の値として、そのまま"light"/"standard"/"fleet"を使う想定
# (他ventureのような日本語プラン名の別表記は導入しない。overage_notifications.pyが
# 既に英語キーを正としているため、変換を1段省略できる)。

# line-reservation-ai/subscription-plan-sync-design.mdの方式(Stripe Priceのlookup_key)を
# 踏襲し、カスタマーポータル経由のプラン変更(customer.subscription.updated、metadataが
# 引き継がれないケース)の解決に用いる。実Price作成時にこのlookup_keyを設定する作業自体は
# オーナー承認後の範囲(pending-approval.md参照)。
LOOKUP_KEY_TO_PLAN_ID = {
    "forklift_pasha_light": "light",
    "forklift_pasha_standard": "standard",
    "forklift_pasha_fleet": "fleet",
}


def write_plan_id_from_checkout_session_metadata(store, internal_id: str, metadata: dict) -> bool:
    """checkout.session.completed受信時の初回plan_id記録(design 3節)。
    `metadata`はStripe Checkout Sessionオブジェクトのmetadataフィールドをそのまま渡す想定。
    未知の値・`plan`キー欠落の場合は書き込まない(course-set-pashaの安全側方針を踏襲)。
    書き込みを行ったかどうかをboolで返す。
    """
    plan_id = metadata.get("plan") if metadata else None
    if plan_id not in KNOWN_PLAN_IDS:
        return False
    store.set_plan_id(internal_id, plan_id)
    return True


def resolve_plan_id_from_subscription(data_object: dict) -> "str | None":
    """customer.subscription.updated等のdata.objectからplan_idを解決する(design 4節)。
    line-reservation-ai/subscription_plan_sync.pyのresolve_plan_from_subscription()と
    同型: items.data[0].price.lookup_keyをLOOKUP_KEY_TO_PLAN_IDで解決し、未知のlookup_key・
    欠落時は常にNoneを返す(呼び出し元は既存値を維持する)。
    """
    try:
        lookup_key = data_object["items"]["data"][0]["price"]["lookup_key"]
    except (KeyError, IndexError, TypeError):
        return None
    return LOOKUP_KEY_TO_PLAN_ID.get(lookup_key)


def sync_plan_id_on_subscription_event(store, internal_id: str, data_object: dict) -> bool:
    """design 4節: 解決できたplan_idが既存値と異なる場合のみset_plan_id()を呼ぶ
    (差分チェックをaircon-pasha/kura-pasha/line-reservation-aiの教訓を踏まえ最初から
    組み込む)。書き込みを行ったかどうかをboolで返す。
    """
    resolved = resolve_plan_id_from_subscription(data_object)
    if resolved is None:
        return False
    if store.get_plan_id(internal_id) == resolved:
        return False
    store.set_plan_id(internal_id, resolved)
    return True
