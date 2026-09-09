#!/usr/bin/env python3
"""subscription_cancellation_notification.pyの検証用テスト。
`python3 test_subscription_cancellation_notification.py`で実行する。"""

from subscription_cancellation_notification import (
    InMemoryLinePushClient,
    LinePushDeliveryError,
    OUTCOME_CANCELLATION_RESCHEDULED,
    OUTCOME_CANCELLATION_SCHEDULED,
    OUTCOME_NO_CHANGE,
    SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE,
    SUBSCRIPTION_CANCELLED_MESSAGE,
    classify_cancel_at_period_end_change,
    handle_subscription_cancellation_update,
    handle_subscription_cancelled,
    render_subscription_cancellation_rescheduled_message,
    render_subscription_cancellation_scheduled_message,
    render_subscription_cancelled_message,
)
from usage_counter_workshop import InMemoryWorkshopStore

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


class _FailingPushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("send failed")


def test_render_message_content():
    text = render_subscription_cancelled_message()
    check("「ご契約が終了しました」を含む", "ご契約が終了しました" in text)
    check(
        "「それまでは引き続きご利用いただけます」という誤った案内を含まない",
        "それまでは引き続きご利用いただけます" not in text,
    )
    check("再開手続きの案内を含む", "新規契約と" in text and "同じお手続き" in text)


def test_handle_sends_to_contractor_only():
    store = InMemoryWorkshopStore()
    store.set_members(
        "W1", contractor_user_id="contractor_1", member_user_ids=["contractor_1", "member_1"]
    )
    push = InMemoryLinePushClient()
    result = handle_subscription_cancelled("W1", store, push)
    check("notified=True", result.notified is True)
    check("contractor_user_idを返す", result.contractor_user_id == "contractor_1")
    check(
        "送信先は契約者本人のみ(共同利用者には送らない)",
        push.sent == [("contractor_1", SUBSCRIPTION_CANCELLED_MESSAGE)],
    )


def test_handle_returns_notified_false_on_delivery_error():
    store = InMemoryWorkshopStore()
    store.set_members("W2", contractor_user_id="contractor_2", member_user_ids=["contractor_2"])
    result = handle_subscription_cancelled("W2", store, _FailingPushClient())
    check("送信失敗時はnotified=False", result.notified is False)
    check(
        "送信失敗時もcontractor_user_idは返す",
        result.contractor_user_id == "contractor_2",
    )


def test_handle_resolves_contractor_even_for_multi_member_workshop():
    store = InMemoryWorkshopStore()
    store.set_members(
        "W3",
        contractor_user_id="contractor_3",
        member_user_ids=["contractor_3", "member_a", "member_b"],
    )
    push = InMemoryLinePushClient()
    handle_subscription_cancelled("W3", store, push)
    check(
        "複数職人プランでも通知はcontractor宛て1件のみ",
        push.sent == [("contractor_3", SUBSCRIPTION_CANCELLED_MESSAGE)],
    )


# --- classify_cancel_at_period_end_change ---


def test_classify_false_to_true_is_scheduled():
    check(
        "false→trueはcancellation_scheduled",
        classify_cancel_at_period_end_change(False, True) == OUTCOME_CANCELLATION_SCHEDULED,
    )


def test_classify_true_to_false_is_rescheduled():
    check(
        "true→falseはcancellation_rescheduled",
        classify_cancel_at_period_end_change(True, False) == OUTCOME_CANCELLATION_RESCHEDULED,
    )


def test_classify_no_change_cases():
    check("false→falseはno_change", classify_cancel_at_period_end_change(False, False) == OUTCOME_NO_CHANGE)
    check("true→trueはno_change", classify_cancel_at_period_end_change(True, True) == OUTCOME_NO_CHANGE)


# --- render_subscription_cancellation_scheduled_message / rescheduled ---


def test_render_scheduled_message_with_date():
    text = render_subscription_cancellation_scheduled_message("2026-10-09")
    check("終了日を含む", "2026-10-09" in text)
    check("解約のお手続きを承りましたを含む", "解約のお手続きを承りました" in text)


def test_render_scheduled_message_without_date_fallback():
    text = render_subscription_cancellation_scheduled_message(None)
    check(
        "日付Noneの場合は日付なしの表現にフォールバック",
        "今回の請求期間の終了日まで" in text,
    )


def test_render_rescheduled_message_is_fixed_text():
    check(
        "解約取り消しの固定文言を返す",
        render_subscription_cancellation_rescheduled_message()
        == SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE,
    )
    check("引き続きご利用いただけますを含む", "引き続きご利用いただけます" in SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE)


# --- handle_subscription_cancellation_update ---


def test_update_scheduled_notifies_contractor():
    store = InMemoryWorkshopStore()
    store.set_members("W20", contractor_user_id="contractor_20", member_user_ids=["contractor_20", "member_20"])
    push = InMemoryLinePushClient()
    result = handle_subscription_cancellation_update(
        "W20", False, True, 1_760_000_000, store, push
    )
    check("outcome=cancellation_scheduled", result.outcome == OUTCOME_CANCELLATION_SCHEDULED)
    check("notified=True", result.notified is True)
    check("送信先は契約者本人のみ", len(push.sent) == 1 and push.sent[0][0] == "contractor_20")


def test_update_rescheduled_notifies_contractor():
    store = InMemoryWorkshopStore()
    store.set_members("W21", contractor_user_id="contractor_21", member_user_ids=["contractor_21"])
    push = InMemoryLinePushClient()
    result = handle_subscription_cancellation_update("W21", True, False, None, store, push)
    check("outcome=cancellation_rescheduled", result.outcome == OUTCOME_CANCELLATION_RESCHEDULED)
    check(
        "解約取り消しメッセージが送信される",
        push.sent == [("contractor_21", SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE)],
    )


def test_update_no_change_sends_nothing():
    store = InMemoryWorkshopStore()
    store.set_members("W22", contractor_user_id="contractor_22", member_user_ids=["contractor_22"])
    push = InMemoryLinePushClient()
    result = handle_subscription_cancellation_update("W22", False, False, None, store, push)
    check("outcome=no_change", result.outcome == OUTCOME_NO_CHANGE)
    check("notified=False", result.notified is False)
    check("送信は行われない", push.sent == [])


def test_update_delivery_failure_returns_notified_false():
    store = InMemoryWorkshopStore()
    store.set_members("W23", contractor_user_id="contractor_23", member_user_ids=["contractor_23"])
    result = handle_subscription_cancellation_update(
        "W23", False, True, None, store, _FailingPushClient()
    )
    check("送信失敗時はnotified=False", result.notified is False)
    check("outcomeはscheduledのまま返す", result.outcome == OUTCOME_CANCELLATION_SCHEDULED)


if __name__ == "__main__":
    test_render_message_content()
    test_handle_sends_to_contractor_only()
    test_handle_returns_notified_false_on_delivery_error()
    test_handle_resolves_contractor_even_for_multi_member_workshop()
    test_classify_false_to_true_is_scheduled()
    test_classify_true_to_false_is_rescheduled()
    test_classify_no_change_cases()
    test_render_scheduled_message_with_date()
    test_render_scheduled_message_without_date_fallback()
    test_render_rescheduled_message_is_fixed_text()
    test_update_scheduled_notifies_contractor()
    test_update_rescheduled_notifies_contractor()
    test_update_no_change_sends_nothing()
    test_update_delivery_failure_returns_notified_false()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
