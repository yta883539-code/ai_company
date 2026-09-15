#!/usr/bin/env python3
"""daily_scheduler.pyの検証用テスト。
`python3 test_daily_scheduler.py`で実行する。"""

from datetime import datetime, timedelta

from daily_scheduler import (
    PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END,
    PAYMENT_FAILURE_REMINDER_MESSAGE,
    WorkshopPaymentFailureState,
    WorkshopTrialEndState,
    build_payment_failure_states,
    build_trial_end_states,
    is_payment_failure_reminder_due,
    is_trial_end_report_due,
    run_daily_workshop_checks,
    select_due_payment_failure_reminders,
    select_due_trial_end_reports,
    send_payment_failure_reminders,
    send_trial_end_reports,
)
from subscription_cancellation_notification import InMemoryLinePushClient, LinePushDeliveryError
from usage_counter_workshop import (
    PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    TRIAL_PERIOD_DAYS,
    InMemoryWorkshopStore,
)

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


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


def _make_store() -> InMemoryWorkshopStore:
    store = InMemoryWorkshopStore()
    store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])
    store.set_members("w2", contractor_user_id="u2", member_user_ids=["u2"])
    return store


def test_build_trial_end_states_reflects_store_fields_in_workshop_id_order():
    store = _make_store()
    store.set_trial_start_at("w2", NOW - timedelta(days=TRIAL_PERIOD_DAYS))
    store.set_trial_start_at("w1", NOW - timedelta(days=1))
    states = build_trial_end_states(store)
    check(
        "workshop_id昇順で組み立てられる",
        [s.workshop_id for s in states] == ["w1", "w2"],
    )
    check(
        "trial_start_atがstoreの値をそのまま反映する",
        states[1].trial_start_at == NOW - timedelta(days=TRIAL_PERIOD_DAYS),
    )


def test_build_payment_failure_states_reflects_store_fields():
    store = _make_store()
    store.set_payment_failure_detected_at("w1", NOW - timedelta(days=5))
    states = build_payment_failure_states(store)
    check(
        "payment_failure_detected_atがstoreの値をそのまま反映する",
        [s.payment_failure_detected_at for s in states if s.workshop_id == "w1"][0]
        == NOW - timedelta(days=5),
    )
    check(
        "未検知のworkshopはNoneのまま",
        [s.payment_failure_detected_at for s in states if s.workshop_id == "w2"][0] is None,
    )


def test_send_trial_end_reports_sends_only_to_due_workshop_and_marks_notified():
    store = _make_store()
    store.set_trial_start_at("w1", NOW - timedelta(days=TRIAL_PERIOD_DAYS))
    store.set_trial_start_at("w2", NOW - timedelta(days=1))
    push = InMemoryLinePushClient()

    result = send_trial_end_reports(NOW, store, push)

    check("30日到達したworkshopのみ送信対象", result.sent == ["w1"])
    check("送信失敗は無し", result.failed == [])
    check("trial_end_notified_atが書き込まれる", store.get_trial_end_notified_at("w1") == NOW)
    check("未到達workshopは書き込まれない", store.get_trial_end_notified_at("w2") is None)
    check("送信先は契約者user_id", push.sent[0][0] == "u1")
    check(
        "生成実績0回の文言(浮いた時間の行を含まない)",
        "生成: 0回" in push.sent[0][1] and "浮いた事務作業時間の目安" not in push.sent[0][1],
    )


def test_send_trial_end_reports_delivery_failure_is_not_marked_notified():
    store = _make_store()
    store.set_trial_start_at("w1", NOW - timedelta(days=TRIAL_PERIOD_DAYS))
    push = _FailingLinePushClient()

    result = send_trial_end_reports(NOW, store, push)

    check("送信失敗はfailedに記録される", result.failed == ["w1"])
    check("送信失敗時はsentに含まれない", result.sent == [])
    check(
        "送信失敗時はtrial_end_notified_atを書き込まない(次回再試行対象として残る)",
        store.get_trial_end_notified_at("w1") is None,
    )


def test_send_payment_failure_reminders_sends_only_to_due_workshop_and_marks_sent():
    store = _make_store()
    store.set_payment_failure_detected_at("w1", NOW - timedelta(days=5))  # 5日経過(4〜7日で対象)
    store.set_payment_failure_detected_at("w2", NOW - timedelta(days=1))  # 1日経過(対象外)
    push = InMemoryLinePushClient()

    result = send_payment_failure_reminders(NOW, store, push)

    check("猶予期間終盤のworkshopのみ送信対象", result.sent == ["w1"])
    check(
        "payment_failure_reminder_sent_atが書き込まれる",
        store.get_payment_failure_reminder_sent_at("w1") == NOW,
    )
    check(
        "リマインド未対象workshopは書き込まれない",
        store.get_payment_failure_reminder_sent_at("w2") is None,
    )
    check("送信文言はPAYMENT_FAILURE_REMINDER_MESSAGE", push.sent[0][1] == PAYMENT_FAILURE_REMINDER_MESSAGE)


def test_send_payment_failure_reminders_delivery_failure_is_not_marked_sent():
    store = _make_store()
    store.set_payment_failure_detected_at("w1", NOW - timedelta(days=5))
    push = _FailingLinePushClient()

    result = send_payment_failure_reminders(NOW, store, push)

    check("送信失敗はfailedに記録される", result.failed == ["w1"])
    check(
        "送信失敗時はpayment_failure_reminder_sent_atを書き込まない",
        store.get_payment_failure_reminder_sent_at("w1") is None,
    )


def test_run_daily_workshop_checks_wires_all_three_notification_kinds():
    store = _make_store()
    store.set_trial_start_at("w1", NOW - timedelta(days=TRIAL_PERIOD_DAYS))
    store.set_payment_failure_detected_at(
        "w2", NOW - timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS + 1)
    )  # 猶予期間超過済み(制限モード移行、オーナー通知対象)
    push = InMemoryLinePushClient()

    result = run_daily_workshop_checks(NOW, store, push)

    check("(B)トライアル到達報告が送信される", result.trial_end_reports.sent == ["w1"])
    check("決済失敗リマインドは対象無し", result.payment_failure_reminders.sent == [])
    check(
        "制限モード移行済みworkshopのオーナー通知が送信される",
        result.payment_suspension_owner_notifications.sent == ["w2"],
    )
    check(
        "契約者向け(トライアル到達)1件+オーナー向け1件の計2件が送信される"
        "(w2は既に猶予期間超過済みのためリマインド対象外)",
        len(push.sent) == 2,
    )


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
    test_build_trial_end_states_reflects_store_fields_in_workshop_id_order()
    test_build_payment_failure_states_reflects_store_fields()
    test_send_trial_end_reports_sends_only_to_due_workshop_and_marks_notified()
    test_send_trial_end_reports_delivery_failure_is_not_marked_notified()
    test_send_payment_failure_reminders_sends_only_to_due_workshop_and_marks_sent()
    test_send_payment_failure_reminders_delivery_failure_is_not_marked_sent()
    test_run_daily_workshop_checks_wires_all_three_notification_kinds()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
