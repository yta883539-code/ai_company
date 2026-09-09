#!/usr/bin/env python3
"""payment_failure_notification.pyの検証用テスト。
`python3 test_payment_failure_notification.py`で実行する。"""

from datetime import datetime, timedelta

from payment_failure_notification import (
    OUTCOME_NOT_APPLICABLE,
    OUTCOME_RECOVERED_FROM_SUSPENSION,
    OUTCOME_SEND_FAILED,
    OUTCOME_SILENT_RESET,
    PAYMENT_FAILURE_DETECTED_MESSAGE,
    PAYMENT_RECOVERED_MESSAGE,
    classify_payment_recovery,
    handle_payment_failure_detected,
    handle_payment_succeeded,
    render_payment_failure_detected_message,
)
from subscription_cancellation_notification import InMemoryLinePushClient, LinePushDeliveryError
from usage_counter_workshop import InMemoryWorkshopStore

NOW = datetime(2026, 9, 9, 9, 0, 0)

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


class _FailingPushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("send failed")


def test_render_payment_failure_detected_message_returns_constant():
    check(
        "render_payment_failure_detected_messageは定数をそのまま返す",
        render_payment_failure_detected_message() == PAYMENT_FAILURE_DETECTED_MESSAGE,
    )


def test_handle_payment_failure_detected_notifies_contractor_only():
    store = InMemoryWorkshopStore()
    store.set_members("W1", contractor_user_id="U1", member_user_ids=["U1", "U2"])
    push = InMemoryLinePushClient()

    result = handle_payment_failure_detected("W1", store, push)

    check("検知通知は成功する", result.notified is True)
    check("検知通知の宛先は契約者本人", result.contractor_user_id == "U1")
    check("送信は契約者1件のみ", push.sent == [("U1", PAYMENT_FAILURE_DETECTED_MESSAGE)])


def test_handle_payment_failure_detected_returns_false_on_send_failure():
    store = InMemoryWorkshopStore()
    store.set_members("W2", contractor_user_id="U3", member_user_ids=["U3"])

    result = handle_payment_failure_detected("W2", store, _FailingPushClient())

    check("送信失敗時はnotified=False", result.notified is False)
    check("送信失敗時もcontractor_user_idは返す", result.contractor_user_id == "U3")


def test_classify_payment_recovery_not_applicable_when_never_detected():
    check(
        "未検知はOUTCOME_NOT_APPLICABLE",
        classify_payment_recovery(None, NOW) == OUTCOME_NOT_APPLICABLE,
    )


def test_classify_payment_recovery_recovered_from_suspension_after_grace_period():
    detected_at = NOW - timedelta(days=8)
    check(
        "猶予期間(7日)超過はOUTCOME_RECOVERED_FROM_SUSPENSION",
        classify_payment_recovery(detected_at, NOW) == OUTCOME_RECOVERED_FROM_SUSPENSION,
    )


def test_classify_payment_recovery_silent_reset_within_grace_period():
    detected_at = NOW - timedelta(days=3)
    check(
        "猶予期間内の解消はOUTCOME_SILENT_RESET",
        classify_payment_recovery(detected_at, NOW) == OUTCOME_SILENT_RESET,
    )


def test_classify_payment_recovery_boundary_exactly_grace_period_is_recovered():
    detected_at = NOW - timedelta(days=7)
    check(
        "猶予期間ちょうど7日はOUTCOME_RECOVERED_FROM_SUSPENSION(is_payment_suspendedと同じ境界)",
        classify_payment_recovery(detected_at, NOW) == OUTCOME_RECOVERED_FROM_SUSPENSION,
    )


def test_handle_payment_succeeded_not_applicable_sends_nothing():
    store = InMemoryWorkshopStore()
    store.set_members("W3", contractor_user_id="U4", member_user_ids=["U4"])
    push = InMemoryLinePushClient()

    result = handle_payment_succeeded("W3", NOW, store, push)

    check("未検知の場合はOUTCOME_NOT_APPLICABLE", result.outcome == OUTCOME_NOT_APPLICABLE)
    check("未検知の場合は送信されない", push.sent == [])


def test_handle_payment_succeeded_recovered_from_suspension_notifies_and_clears():
    store = InMemoryWorkshopStore()
    store.set_members("W4", contractor_user_id="U5", member_user_ids=["U5", "U6"])
    store.set_payment_failure_detected_at("W4", NOW - timedelta(days=10))
    push = InMemoryLinePushClient()

    result = handle_payment_succeeded("W4", NOW, store, push)

    check("制限モードからの復旧はnotified=True", result.notified is True)
    check("制限モードからの復旧の宛先は契約者本人", result.contractor_user_id == "U5")
    check("復旧メッセージが契約者にのみ送信される", push.sent == [("U5", PAYMENT_RECOVERED_MESSAGE)])
    check(
        "復旧後はpayment_failure_detected_atがクリアされる",
        store.get_payment_failure_detected_at("W4") is None,
    )


def test_handle_payment_succeeded_silent_reset_sends_nothing_but_clears_state():
    store = InMemoryWorkshopStore()
    store.set_members("W5", contractor_user_id="U7", member_user_ids=["U7"])
    store.set_payment_failure_detected_at("W5", NOW - timedelta(days=2))
    push = InMemoryLinePushClient()

    result = handle_payment_succeeded("W5", NOW, store, push)

    check("猶予期間中の解消はOUTCOME_SILENT_RESET", result.outcome == OUTCOME_SILENT_RESET)
    check("猶予期間中の解消は送信されない", push.sent == [])
    check(
        "猶予期間中の解消でもpayment_failure_detected_atはクリアされる",
        store.get_payment_failure_detected_at("W5") is None,
    )


def test_handle_payment_succeeded_send_failure_keeps_state_for_retry():
    store = InMemoryWorkshopStore()
    store.set_members("W6", contractor_user_id="U8", member_user_ids=["U8"])
    detected_at = NOW - timedelta(days=10)
    store.set_payment_failure_detected_at("W6", detected_at)

    result = handle_payment_succeeded("W6", NOW, store, _FailingPushClient())

    check("送信失敗はOUTCOME_SEND_FAILED", result.outcome == OUTCOME_SEND_FAILED)
    check("送信失敗時は状態を変更しない(Webhookリトライに委ねる)", result.notified is False)
    check(
        "送信失敗時はpayment_failure_detected_atがクリアされない",
        store.get_payment_failure_detected_at("W6") == detected_at,
    )


if __name__ == "__main__":
    test_render_payment_failure_detected_message_returns_constant()
    test_handle_payment_failure_detected_notifies_contractor_only()
    test_handle_payment_failure_detected_returns_false_on_send_failure()
    test_classify_payment_recovery_not_applicable_when_never_detected()
    test_classify_payment_recovery_recovered_from_suspension_after_grace_period()
    test_classify_payment_recovery_silent_reset_within_grace_period()
    test_classify_payment_recovery_boundary_exactly_grace_period_is_recovered()
    test_handle_payment_succeeded_not_applicable_sends_nothing()
    test_handle_payment_succeeded_recovered_from_suspension_notifies_and_clears()
    test_handle_payment_succeeded_silent_reset_sends_nothing_but_clears_state()
    test_handle_payment_succeeded_send_failure_keeps_state_for_retry()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
