#!/usr/bin/env python3
"""
daily-scheduler-design.md(フェーズ112)で設計した「Cloud Function G:
run_daily_workshop_checks」のうち、選定ロジック(どのworkshopに何を送るべきかの判定)を
実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信・WorkshopStoreProtocolからの
  全workshop走査(Firestore相当の集計クエリ)はいずれもオーナー承認待ち(pending-
  approval.md参照)。本モジュールはそれとは別に、「いつ・どのworkshopに(B)トライアル
  30日到達報告・決済失敗3日前リマインドを送るべきか」の判定ロジック(design 3節)を
  実クラウド接続なしで検証可能にしたもの(他venture3件のtrial_end_scheduler.py・
  payment_failure_reminder_scheduler.pyと同じ位置づけ・同じ構成)。
- (B)トライアル30日到達報告の通知文言(trial-end-notification-design.md 3節)の
  組み立てはusage_counter_workshop.pyのformat_trial_end_notification_message()相当を
  本venture側でまだ実装していないため対象外とし、本モジュールは選定ロジックのみを扱う。

設計の参照元: daily-scheduler-design.md, trial-end-notification-design.md,
payment-failure-dunning-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

from usage_counter_workshop import PAYMENT_FAILURE_GRACE_PERIOD_DAYS, TRIAL_PERIOD_DAYS

# payment-failure-dunning-design.md 3節: 猶予期間は7日、そのうち3日前(=検知から4日後)に
# リマインドを1回だけ送る(daily-scheduler-design.md 3.2節)。
PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END = 3

# daily-scheduler-design.md 4節: 決済失敗3日前リマインドの文言(プレーンテキスト。
# 本venture固有のPortalLinkProvider相当が未実装のため、他venture3件のようなFlex Message・
# ボタンではなく他の通知〈payment-failure-dunning-design.md 4節〉と同じ形式に揃える)。
PAYMENT_FAILURE_REMINDER_MESSAGE = (
    "【鞍パシャッと】お支払いのご確認まもなく期限です\n"
    "\n"
    "いつもご利用ありがとうございます。\n"
    "お支払い手続きが完了できないまま、まもなく一時停止の期限を迎えます。\n"
    "このままお支払い方法のご確認・更新がない場合、受注内容整理メモ・納品案内・\n"
    "お手入れ案内の生成を一時停止させていただきます。\n"
    "\n"
    "お手数ですが、ご利用中の決済手続き時にご案内した画面からお支払い方法をご確認\n"
    "いただけますようお願いします。"
)


@dataclass(frozen=True)
class WorkshopTrialEndState:
    """design 3.1節が参照する、workshop 1件分のトライアル終了関連状態。

    trial_start_at・trial_generation_used・trial_end_notified_atは
    usage_counter_workshop.pyのWorkshopStoreProtocolが持つ同名フィールドをそのまま反映する。
    """

    workshop_id: str
    trial_start_at: Optional[datetime]
    trial_generation_used: bool
    trial_end_notified_at: Optional[datetime] = None


def is_trial_end_report_due(
    state: WorkshopTrialEndState,
    now: datetime,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> bool:
    """trial-end-notification-design.md 2節(B)経路の抽出条件をそのままコード化したもの。

    以下すべてを満たす場合のみTrueを返す。
    - trial_start_atが設定済み
    - trial_generation_usedがFalse((A)経路〈生涯最初の生成完了時に便乗送信〉が既に
      発生済みならこの(B)経路の対象外)
    - trial_end_notified_atが未設定(二重送信防止。(A)(B)共通の同一フィールド)
    - now - trial_start_at >= trial_period_days日(「ちょうど」ではなく「以上」の範囲条件
      とすることで、日次実行の遅延・欠落に自然に耐える)
    """

    if state.trial_start_at is None:
        return False
    if state.trial_generation_used:
        return False
    if state.trial_end_notified_at is not None:
        return False
    return now - state.trial_start_at >= timedelta(days=trial_period_days)


def select_due_trial_end_reports(
    states: Sequence[WorkshopTrialEndState],
    now: datetime,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> list[WorkshopTrialEndState]:
    """statesのうちis_trial_end_report_due()がTrueのものだけを、入力順を維持して返す。"""

    return [s for s in states if is_trial_end_report_due(s, now, trial_period_days)]


@dataclass(frozen=True)
class WorkshopPaymentFailureState:
    """design 3.2節が参照する、workshop 1件分の決済失敗関連状態。

    payment_failure_detected_at・payment_failure_reminder_sent_atは
    usage_counter_workshop.pyのWorkshopStoreProtocolが持つ同名フィールドをそのまま反映する。
    """

    workshop_id: str
    payment_failure_detected_at: Optional[datetime]
    payment_failure_reminder_sent_at: Optional[datetime] = None


def is_payment_failure_reminder_due(
    state: WorkshopPaymentFailureState,
    now: datetime,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END,
) -> bool:
    """daily-scheduler-design.md 3.2節の抽出条件をそのままコード化したもの。

    以下すべてを満たす場合のみTrueを返す。
    - payment_failure_detected_atが設定済み
    - payment_failure_reminder_sent_atが未設定(1回のみ送信)
    - now - payment_failure_detected_at >= (grace_period_days - reminder_days_before_end)日
    - now - payment_failure_detected_at < grace_period_days日(既に制限モードに達している
      workshopには今更「まもなく期限」のリマインドを送らない。本ventureは
      payment_suspended_atのような別立てフラグを持たず経過日数の都度算出方式のため、
      aircon-pasha版の`payment_suspended_at is None`条件の代わりにこの上限で表現する)
    """

    if state.payment_failure_detected_at is None:
        return False
    if state.payment_failure_reminder_sent_at is not None:
        return False
    elapsed = now - state.payment_failure_detected_at
    if elapsed < timedelta(days=grace_period_days - reminder_days_before_end):
        return False
    return elapsed < timedelta(days=grace_period_days)


def select_due_payment_failure_reminders(
    states: Sequence[WorkshopPaymentFailureState],
    now: datetime,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END,
) -> list[WorkshopPaymentFailureState]:
    """statesのうちis_payment_failure_reminder_due()がTrueのものだけを、入力順を維持して
    返す。"""

    return [
        s
        for s in states
        if is_payment_failure_reminder_due(s, now, grace_period_days, reminder_days_before_end)
    ]
