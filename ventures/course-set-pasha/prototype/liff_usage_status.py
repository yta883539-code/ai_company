#!/usr/bin/env python3
"""liff-plan-selection-ui-wireframe.md「現在のご利用状況」欄が参照する残回数・残日数の
実際の取得ロジック(フェーズ163で「次のステップ候補」として未設計のまま残っていた部分)。

設計の参照元:
- liff-plan-selection-ui-wireframe.md「設計判断」節: get_plan()未設定(トライアル中)なら
  残回数・残日数、設定済みなら現在のプラン名を出し分ける。
- trial-start-anchor-decision.md: トライアルは「初回生成成功時点」(trial_start_at)を起点と
  するため、trial_start_at未設定(まだ一度も生成していない)ユーザーは満額の残回数・残日数を
  表示する。
- cloud_function_webhook.PLAN_MONTHLY_LIMITS / trial_end_scheduler.TRIAL_GENERATION_LIMIT・
  DEFAULT_TRIAL_PERIOD_DAYSを単一の正とし、本モジュールでは値を再定義しない。

実LIFF SDK接続・実Firestore接続はいずれもオーナー承認後の課題として引き続き未着手。
本モジュールはuser_profile_store/usage_counterから読み取った値を画面表示用の辞書に
組み立てる部分のみを実接続なしで検証可能にしたもの。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from cloud_function_webhook import PLAN_MONTHLY_LIMITS
from trial_end_scheduler import DEFAULT_TRIAL_PERIOD_DAYS, TRIAL_GENERATION_LIMIT


class UsageStatusProfileStoreProtocol(Protocol):
    def get_plan(self, user_id: str) -> Optional[str]:
        ...


class UsageStatusUsageCounterProtocol(Protocol):
    def get_trial_start_at(self, user_id: str) -> Optional[datetime]:
        ...

    def get_trial_generation_count(self, user_id: str) -> int:
        ...

    def get_count(self, user_id: str, month: str) -> int:
        ...


@dataclass(frozen=True)
class TrialUsageStatus:
    """トライアル中(get_plan()未設定)の「現在のご利用状況」欄の表示内容。"""

    remaining_generations: int
    remaining_days: int


@dataclass(frozen=True)
class PaidUsageStatus:
    """有料プラン選択済み(get_plan()設定済み)の「現在のご利用状況」欄の表示内容。"""

    plan: str
    monthly_count: int
    monthly_limit: int


def get_current_usage_status(
    user_id: str,
    profile_store: UsageStatusProfileStoreProtocol,
    usage_counter: UsageStatusUsageCounterProtocol,
    now: datetime,
    current_month: str,
) -> "TrialUsageStatus | PaidUsageStatus":
    """liff-plan-selection-ui-wireframe.md「現在のご利用状況」欄の表示内容を組み立てる。

    - `profile_store.get_plan(user_id)`が設定済みなら`PaidUsageStatus`(現在のプラン名・
      今月の生成回数・プラン上限)を返す。
    - 未設定(トライアル中)なら`TrialUsageStatus`を返す。残回数は
      `TRIAL_GENERATION_LIMIT - get_trial_generation_count(user_id)`を0未満に落ちないよう
      クランプする(上限到達後もマイナス表示にしないため、build_usage_notice()の
      「上限超過」表現とは別の単純化)。残日数は`trial_start_at`未設定(まだ一度も生成して
      いない、trial-start-anchor-decision.mdの起点未到達)の場合は満額の
      `DEFAULT_TRIAL_PERIOD_DAYS`を返し、設定済みなら経過日数を差し引いた残り日数を
      0未満に落ちないようクランプして返す。
    """
    plan = profile_store.get_plan(user_id)
    if plan is not None:
        monthly_limit = PLAN_MONTHLY_LIMITS[plan]
        monthly_count = usage_counter.get_count(user_id, current_month)
        return PaidUsageStatus(
            plan=plan, monthly_count=monthly_count, monthly_limit=monthly_limit
        )

    trial_generation_count = usage_counter.get_trial_generation_count(user_id)
    remaining_generations = max(0, TRIAL_GENERATION_LIMIT - trial_generation_count)

    trial_start_at = usage_counter.get_trial_start_at(user_id)
    if trial_start_at is None:
        remaining_days = DEFAULT_TRIAL_PERIOD_DAYS
    else:
        elapsed_days = (now - trial_start_at).days
        remaining_days = max(0, DEFAULT_TRIAL_PERIOD_DAYS - elapsed_days)

    return TrialUsageStatus(
        remaining_generations=remaining_generations, remaining_days=remaining_days
    )


def format_usage_status_line(status: "TrialUsageStatus | PaidUsageStatus") -> str:
    """liff-plan-selection-ui-wireframe.mdのワイヤーフレーム文言をそのまま再現する。"""
    if isinstance(status, PaidUsageStatus):
        return f"現在のプラン: {status.plan}"
    return (
        f"トライアル残り: {status.remaining_generations}回 / "
        f"{status.remaining_days}日"
    )
