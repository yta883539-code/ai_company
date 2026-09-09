#!/usr/bin/env python3
"""subscription_cancellation_notification.pyの検証用テスト。
`python3 test_subscription_cancellation_notification.py`で実行する。"""

from subscription_cancellation_notification import (
    InMemoryLinePushClient,
    LinePushDeliveryError,
    SUBSCRIPTION_CANCELLED_MESSAGE,
    handle_subscription_cancelled,
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


if __name__ == "__main__":
    test_render_message_content()
    test_handle_sends_to_contractor_only()
    test_handle_returns_notified_false_on_delivery_error()
    test_handle_resolves_contractor_even_for_multi_member_workshop()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
