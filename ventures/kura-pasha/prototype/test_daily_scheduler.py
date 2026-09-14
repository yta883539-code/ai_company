#!/usr/bin/env python3
"""daily_scheduler.pyの検証用テスト。
`python3 test_daily_scheduler.py`で実行する。"""

from datetime import datetime, timedelta

from daily_scheduler import (
    PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END,
    WorkshopPaymentFailureState,
    WorkshopTrialEndState,
    is_payment_failure_reminder_due,
    is_trial_end_report_due,
    select_due_payment_failure_reminders,
    select_due_trial_end_reports,
)
from usage_counter_workshop import PAYMENT_FAILURE_GRACE_PERIOD_DAYS, TRIAL_PERIOD_DAYS

NOW = datetime(2026, 9, 14, 4, 0, 0)

PASS = 0
FAIL = 0


def check(label, condition):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"OK   {label}")
    else:
        FAIL += 1
        print(f"FAIL {label}")


def test_trial_end_report_due_when_thirty_days_elapsed_without_generation():
    state = WorkshopTrialEndState(
        workshop_id="W1",
        trial_start_at=NOW - timedelta(days=TRIAL_PERIOD_DAYS),
        trial_generation_used=False,
        trial_end_notified_at=None,
    )
    check("ちょうど30日経過・未生成はTrue", is_trial_end_report_due(state, NOW) is True)


def test_trial_end_report_not_due_before_thirty_days():
    state = WorkshopTrialEndState(
        workshop_id="W2",
        trial_start_at=NOW - timedelta(days=TRIAL_PERIOD_DAYS - 1),
        trial_generation_used=False,
        trial_end_notified_at=None,
    )
    check("29日経過はFalse", is_trial_end_report_due(state, NOW) is False)


def test_trial_end_report_not_due_when_generation_already_used():
    state = WorkshopTrialEndState(
        workshop_id="W3",
        trial_start_at=NOW - timedelta(days=TRIAL_PERIOD_DAYS + 5),
        trial_generation_used=True,
        trial_end_notified_at=None,
    )
    check(
        "(A)経路で既に生成済みなら30日超でも(B)はFalse",
        is_trial_end_report_due(state, NOW) is False,
    )


def test_trial_end_report_not_due_when_already_notified():
    state = WorkshopTrialEndState(
        workshop_id="W4",
        trial_start_at=NOW - timedelta(days=TRIAL_PERIOD_DAYS + 5),
        trial_generation_used=False,
        trial_end_notified_at=NOW - timedelta(days=1),
    )
    check("既に通知済みならFalse(二重送信防止)", is_trial_end_report_due(state, NOW) is False)


def test_trial_end_report_not_due_when_trial_start_at_missing():
    state = WorkshopTrialEndState(
        workshop_id="W5",
        trial_start_at=None,
        trial_generation_used=False,
        trial_end_notified_at=None,
    )
    check("trial_start_at未設定はFalse", is_trial_end_report_due(state, NOW) is False)


def test_select_due_trial_end_reports_filters_and_preserves_order():
    due = WorkshopTrialEndState(
        workshop_id="DUE",
        trial_start_at=NOW - timedelta(days=TRIAL_PERIOD_DAYS + 1),
        trial_generation_used=False,
        trial_end_notified_at=None,
    )
    not_due = WorkshopTrialEndState(
        workshop_id="NOT_DUE",
        trial_start_at=NOW - timedelta(days=1),
        trial_generation_used=False,
        trial_end_notified_at=None,
    )
    result = select_due_trial_end_reports([not_due, due], NOW)
    check("対象workshopのみ抽出される", [s.workshop_id for s in result] == ["DUE"])


def test_payment_failure_reminder_due_at_boundary_four_days():
    threshold_days = PAYMENT_FAILURE_GRACE_PERIOD_DAYS - PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END
    state = WorkshopPaymentFailureState(
        workshop_id="W6",
        payment_failure_detected_at=NOW - timedelta(days=threshold_days),
        payment_failure_reminder_sent_at=None,
    )
    check(
        f"ちょうど{threshold_days}日経過はTrue",
        is_payment_failure_reminder_due(state, NOW) is True,
    )


def test_payment_failure_reminder_not_due_before_boundary():
    threshold_days = PAYMENT_FAILURE_GRACE_PERIOD_DAYS - PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END
    state = WorkshopPaymentFailureState(
        workshop_id="W7",
        payment_failure_detected_at=NOW - timedelta(days=threshold_days - 1),
        payment_failure_reminder_sent_at=None,
    )
    check(
        f"{threshold_days - 1}日経過(境界未満)はFalse",
        is_payment_failure_reminder_due(state, NOW) is False,
    )


def test_payment_failure_reminder_not_due_once_grace_period_fully_elapsed():
    state = WorkshopPaymentFailureState(
        workshop_id="W8",
        payment_failure_detected_at=NOW - timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS),
        payment_failure_reminder_sent_at=None,
    )
    check(
        "猶予期間7日ちょうど経過(既に制限モード相当)はFalse",
        is_payment_failure_reminder_due(state, NOW) is False,
    )


def test_payment_failure_reminder_not_due_when_already_sent():
    state = WorkshopPaymentFailureState(
        workshop_id="W9",
        payment_failure_detected_at=NOW - timedelta(days=5),
        payment_failure_reminder_sent_at=NOW - timedelta(days=1),
    )
    check("既に送信済みならFalse(1回のみ送信)", is_payment_failure_reminder_due(state, NOW) is False)


def test_payment_failure_reminder_not_due_when_not_detected():
    state = WorkshopPaymentFailureState(
        workshop_id="W10",
        payment_failure_detected_at=None,
        payment_failure_reminder_sent_at=None,
    )
    check(
        "payment_failure_detected_at未設定はFalse",
        is_payment_failure_reminder_due(state, NOW) is False,
    )


def test_select_due_payment_failure_reminders_filters_and_preserves_order():
    due = WorkshopPaymentFailureState(
        workshop_id="DUE",
        payment_failure_detected_at=NOW - timedelta(days=5),
        payment_failure_reminder_sent_at=None,
    )
    not_due = WorkshopPaymentFailureState(
        workshop_id="NOT_DUE",
        payment_failure_detected_at=NOW - timedelta(days=1),
        payment_failure_reminder_sent_at=None,
    )
    result = select_due_payment_failure_reminders([not_due, due], NOW)
    check("対象workshopのみ抽出される", [s.workshop_id for s in result] == ["DUE"])


if __name__ == "__main__":
    test_trial_end_report_due_when_thirty_days_elapsed_without_generation()
    test_trial_end_report_not_due_before_thirty_days()
    test_trial_end_report_not_due_when_generation_already_used()
    test_trial_end_report_not_due_when_already_notified()
    test_trial_end_report_not_due_when_trial_start_at_missing()
    test_select_due_trial_end_reports_filters_and_preserves_order()
    test_payment_failure_reminder_due_at_boundary_four_days()
    test_payment_failure_reminder_not_due_before_boundary()
    test_payment_failure_reminder_not_due_once_grace_period_fully_elapsed()
    test_payment_failure_reminder_not_due_when_already_sent()
    test_payment_failure_reminder_not_due_when_not_detected()
    test_select_due_payment_failure_reminders_filters_and_preserves_order()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
