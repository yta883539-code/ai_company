#!/usr/bin/env python3
"""
trial-end-scheduler-design.mdで設計した「Cloud Function D: send_trial_end_notifications」の
うち、条件(B)「trial_start_atから14日経過」の対象ユーザーを抽出する判断ロジックを、
実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信、およびstripe_webhook.py側の
  upgraded_at書き込み配線は、いずれもオーナー承認待ち(pending-approval.md参照)か
  次回以降の実装課題(trial-end-scheduler-design.md 5節)であり、本モジュールの範囲外。
- 本モジュールは「いつ・どのユーザーにトライアル終了通知を送るべきか」という
  判定ロジックのみを実クラウド接続なしで検証可能にしたもの。メッセージ整形・実送信は
  trial-end-notification-design.md 3節の文言・cloud_function_webhook.pyのLLM連携とは
  別の領分とする。

設計の参照元: trial-end-scheduler-design.md, trial-end-notification-design.md,
trial-start-anchor-decision.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

# trial-end-notification-design.md 2節(B): トライアル開始から14日でトライアル終了。
DEFAULT_TRIAL_PERIOD_DAYS = 14


@dataclass(frozen=True)
class TrialUserState:
    """trial-end-scheduler-design.md 3節が参照する、ユーザー1件分のusage_counter状態。

    trial_start_at・trial_end_notified_atはInMemoryUsageCounter(cloud_function_webhook.py)
    に既存のフィールドをそのまま反映する。upgraded_atはtrial-end-scheduler-design.md
    2節で新規に提案したフィールドで、実際の書き込み配線(stripe_webhook.py側)は
    本モジュールの範囲外のため、未接続の間は常にNoneとして扱われる想定。
    """

    user_id: str
    trial_start_at: Optional[datetime]
    trial_end_notified_at: Optional[datetime] = None
    upgraded_at: Optional[datetime] = None


def select_due_trial_end_notifications(
    users: Sequence[TrialUserState],
    now: datetime,
    trial_period_days: int = DEFAULT_TRIAL_PERIOD_DAYS,
) -> list[TrialUserState]:
    """trial-end-scheduler-design.md 3節の抽出条件をそのままコード化したもの。

    以下すべてを満たすユーザーのみを対象として返す(順序はusersの入力順を維持する)。
    - trial_start_atが設定済み
    - trial_end_notified_atが未設定(条件A側で既に送信済みなら対象外になる想定)
    - upgraded_atが未設定(2節の暫定的な既知の限界: 配線未接続の間は常にNoneのため
      この条件は事実上素通りする)
    - now - trial_start_at >= trial_period_days日
      (「ちょうど」の時刻一致ではなく「以上」の範囲条件とすることで、日次実行の
      遅延・欠落に自然に耐える。reminder-scheduler-design.mdの
      select_due_initial_reminders()と同じ設計判断)
    """

    threshold = timedelta(days=trial_period_days)
    due: list[TrialUserState] = []
    for user in users:
        if user.trial_start_at is None:
            continue
        if user.trial_end_notified_at is not None:
            continue
        if user.upgraded_at is not None:
            continue
        if now - user.trial_start_at >= threshold:
            due.append(user)
    return due


def _demo() -> None:
    now = datetime(2026, 8, 23, 4, 0, 0)
    users = [
        # 14日ちょうど経過: 対象
        TrialUserState(user_id="u1", trial_start_at=now - timedelta(days=14)),
        # 13日しか経過していない: 対象外
        TrialUserState(user_id="u2", trial_start_at=now - timedelta(days=13)),
        # 既に通知済み: 対象外(条件Aで先に送信済み等を想定)
        TrialUserState(
            user_id="u3",
            trial_start_at=now - timedelta(days=20),
            trial_end_notified_at=now - timedelta(days=1),
        ),
        # 既に有料転換済み: 対象外
        TrialUserState(
            user_id="u4",
            trial_start_at=now - timedelta(days=20),
            upgraded_at=now - timedelta(days=2),
        ),
        # トライアル未開始(trial_start_at未設定): 対象外
        TrialUserState(user_id="u5", trial_start_at=None),
    ]
    due = select_due_trial_end_notifications(users, now)
    print([u.user_id for u in due])


if __name__ == "__main__":
    _demo()
