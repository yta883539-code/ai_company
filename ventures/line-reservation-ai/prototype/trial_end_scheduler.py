#!/usr/bin/env python3
"""
trial-end-scheduler-design.md 3節で設計した、トライアル終了時利用実績レポートの
送信要否判定(期間条件・件数条件のOR判定)を、実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler定期実行・Firestoreからの集計値取得・LINE Push Message API
  接続は、GCPプロジェクト作成・LINE公式アカウント開設を伴うため引き続きオーナー承認待ち
  (pending-approval.md参照)。
- 本モジュールはtrial_end_report_scheduler.py/dormant_mode_scheduler.pyと同じ役割分担
  (判断ロジックのみを切り出す)で、集計済みの状態値を受け取って送信要否を判定する部分のみを
  担う。

設計の参照元: trial-end-scheduler-design.md 3節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

# trial-start-anchor-decision.md「無料トライアル条件(仮)」で確定した閾値。
TRIAL_PERIOD_DAYS = 14
TRIAL_BOOKING_THRESHOLD = 20


@dataclass(frozen=True)
class StoreTrialState:
    """1店舗ぶんのトライアル関連状態(firestore-data-model.md `stores/{storeId}`から
    抜粋)。booking_countは`InMemoryBookingRecordStore.count_confirmed_bookings()`相当の
    集計済みの値を渡す想定で、集計処理自体(Firestoreクエリ)は本モジュールのスコープ外
    (trial_end_report_scheduler.py`TrialUsageSummary`と同じ方針)。
    """

    store_id: str
    trial_start_at: Optional[datetime]
    trial_end_report_sent_at: Optional[datetime]
    booking_count: int

    def __post_init__(self) -> None:
        if self.booking_count < 0:
            raise ValueError("booking_count must not be negative")


def is_trial_end_report_due(
    state: StoreTrialState,
    now: datetime,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
    trial_booking_threshold: int = TRIAL_BOOKING_THRESHOLD,
) -> bool:
    """トライアル終了時利用実績レポートを送信すべきタイミングかどうかを判定する。

    trial-start-anchor-decision.md「無料トライアル条件(仮)」の「初回の予約確定から
    14日間、または初回の予約確定を含め予約20件到達のいずれか早い方まで無料」を、
    期間条件と件数条件のOR判定として実装したもの。
    """
    if state.trial_start_at is None:
        return False
    if state.trial_end_report_sent_at is not None:
        return False
    if now - state.trial_start_at >= timedelta(days=trial_period_days):
        return True
    return state.booking_count >= trial_booking_threshold


def select_due_trial_end_reports(
    states: list[StoreTrialState],
    now: datetime,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
    trial_booking_threshold: int = TRIAL_BOOKING_THRESHOLD,
) -> list[StoreTrialState]:
    """`states`のうち、今回の実行でレポート送信対象となるものだけを抽出する。
    course-set-pasha/trial_end_scheduler.py`select_due_trial_end_notifications()`と
    同じ役割分担(選定ロジックの一覧版ラッパー)。
    """
    return [
        state
        for state in states
        if is_trial_end_report_due(state, now, trial_period_days, trial_booking_threshold)
    ]


def _demo() -> None:
    now = datetime(2026, 9, 1, 19, 0, 0)

    # 1) 期間条件で到達(14日以上前に開始、件数はまだ少ない)
    store_a = StoreTrialState(
        store_id="store-a",
        trial_start_at=datetime(2026, 8, 15, 10, 0, 0),
        trial_end_report_sent_at=None,
        booking_count=3,
    )
    # 2) 件数条件で到達(期間はまだ短いが20件到達)
    store_b = StoreTrialState(
        store_id="store-b",
        trial_start_at=datetime(2026, 8, 30, 10, 0, 0),
        trial_end_report_sent_at=None,
        booking_count=20,
    )
    # 3) いずれの条件も未到達
    store_c = StoreTrialState(
        store_id="store-c",
        trial_start_at=datetime(2026, 8, 30, 10, 0, 0),
        trial_end_report_sent_at=None,
        booking_count=5,
    )
    # 4) 到達済みだが送信済みのため対象外(冪等性)
    store_d = StoreTrialState(
        store_id="store-d",
        trial_start_at=datetime(2026, 8, 1, 10, 0, 0),
        trial_end_report_sent_at=datetime(2026, 8, 20, 4, 0, 0),
        booking_count=30,
    )

    due = select_due_trial_end_reports([store_a, store_b, store_c, store_d], now)
    print("送信対象:", [state.store_id for state in due])


if __name__ == "__main__":
    _demo()
