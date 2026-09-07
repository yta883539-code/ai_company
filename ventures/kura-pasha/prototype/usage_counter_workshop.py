#!/usr/bin/env python3
"""
usage-counter-workshop-key-design.md(フェーズ26)2節で確定した、生成リクエスト受信時の
月間生成回数カウント処理(user_id→workshop_id→usage_counter参照の3ステップ)を
実行可能なコードに落とし込んだもの。

位置づけ:
- README.md「次にやること」1点目(本venture未着手だった生成リクエスト処理の
  プロトタイプコード)に対応する、本venture初のprototype/コード。
- course-set-pasha/prototype/post_generation_checks.py・
  aircon-pasha同等モジュールと同じ位置づけで、実Firestore接続なしにロジックのみを
  検証可能にする。実LINE Messaging API・実Firestore・実Stripe接続はいずれもオーナー
  承認待ちの範囲(pending-approval.md参照)で、本モジュールでは行わない。
- craftsman-account-linking-design.md(フェーズ25)で確定した`craftsman_workshop`・
  `user_profile.workshop_id`・usage-counter-workshop-key-design.md(フェーズ26)で
  確定した`usage_counter/{workshop_id}`のデータ構造を前提とする。
- 未検証・残課題(usage-counter-workshop-key-design.md末尾)だった
  「`user_profile.workshop_id`が未設定(workshop未作成)のエッジケース」は、本モジュールで
  `WorkshopNotLinkedError`として明示的に扱う形で解消した。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol


# pricing-plan.md確定値(プラン名→月間生成回数上限・超過分の従量単価)。
PLAN_LIMITS = {
    "light": {"monthly_limit": 3, "overage_price_jpy": 250},
    "standard": {"monthly_limit": 8, "overage_price_jpy": 200},
    "multi_craftsman": {"monthly_limit": 20, "overage_price_jpy": 150},
}


class WorkshopNotLinkedError(Exception):
    """送信元user_idにworkshop_idが未設定(workshop未作成)の場合に送出する。

    craftsman-account-linking-design.md 2節の通り、LINE友だち追加時点ではまだ
    連携コードが未解決でworkshopが作られていない状態がありうる。呼び出し側は
    この例外を「まだ新規契約フローが完了していません」という案内に変換する想定。
    """


class UnknownPlanError(Exception):
    """workshopのplan_idがPLAN_LIMITSに存在しない場合に送出する(データ不整合)。"""


class UserProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}.workshop_id`への読み取りを表す。"""

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        ...


class WorkshopStoreProtocol(Protocol):
    """`craftsman_workshop/{workshop_id}.plan_id`への読み取りを表す。"""

    def get_plan_id(self, workshop_id: str) -> str:
        ...


class UsageCounterStoreProtocol(Protocol):
    """`usage_counter/{workshop_id}`(month・count)への読み書きを表す。"""

    def get(self, workshop_id: str) -> Optional[tuple[str, int]]:
        """(month, count)を返す。ドキュメント未作成の場合はNone。"""
        ...

    def set(self, workshop_id: str, month: str, count: int) -> None:
        ...


class InMemoryUserProfileStore:
    def __init__(self) -> None:
        self._workshop_id_by_user: dict[str, str] = {}

    def link(self, user_id: str, workshop_id: str) -> None:
        self._workshop_id_by_user[user_id] = workshop_id

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        return self._workshop_id_by_user.get(user_id)


class InMemoryWorkshopStore:
    def __init__(self) -> None:
        self._plan_id_by_workshop: dict[str, str] = {}

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        self._plan_id_by_workshop[workshop_id] = plan_id

    def get_plan_id(self, workshop_id: str) -> str:
        return self._plan_id_by_workshop[workshop_id]


class InMemoryUsageCounterStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, int]] = {}

    def get(self, workshop_id: str) -> Optional[tuple[str, int]]:
        return self._entries.get(workshop_id)

    def set(self, workshop_id: str, month: str, count: int) -> None:
        self._entries[workshop_id] = (month, count)


def _current_month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


@dataclass
class UsageCheckResult:
    workshop_id: str
    plan_id: str
    month: str
    count_after_increment: int
    monthly_limit: int
    within_limit: bool
    overage_price_jpy: int


def check_and_increment_usage(
    user_id: str,
    now: datetime,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
    usage_counter_store: UsageCounterStoreProtocol,
) -> UsageCheckResult:
    """usage-counter-workshop-key-design.md 2節の3ステップを実行する。

    1. user_id→workshop_idを引く(未設定ならWorkshopNotLinkedError)。
    2. usage_counter/{workshop_id}を読み、monthが当月でなければcount=0でリセットしてから
       加算する(subscription-cancellation-flow-design.mdが踏襲済みのダウングレード時の
       count維持方針とは独立に、月替わりのリセットのみここで扱う)。
    3. plan_idをcraftsman_workshopから取得し、pricing-plan.mdの上限と突き合わせて
       上限超過(従量課金要否)を判定する。
    """
    workshop_id = user_profile_store.get_workshop_id(user_id)
    if workshop_id is None:
        raise WorkshopNotLinkedError(
            f"user_id={user_id!r}にworkshop_idが未設定です(新規契約フロー未完了)"
        )

    plan_id = workshop_store.get_plan_id(workshop_id)
    if plan_id not in PLAN_LIMITS:
        raise UnknownPlanError(f"workshop_id={workshop_id!r}のplan_id={plan_id!r}が不明です")

    current_month = _current_month_key(now)
    existing = usage_counter_store.get(workshop_id)
    if existing is None or existing[0] != current_month:
        count_before = 0
    else:
        count_before = existing[1]

    count_after = count_before + 1
    usage_counter_store.set(workshop_id, current_month, count_after)

    limits = PLAN_LIMITS[plan_id]
    return UsageCheckResult(
        workshop_id=workshop_id,
        plan_id=plan_id,
        month=current_month,
        count_after_increment=count_after,
        monthly_limit=limits["monthly_limit"],
        within_limit=count_after <= limits["monthly_limit"],
        overage_price_jpy=limits["overage_price_jpy"],
    )
