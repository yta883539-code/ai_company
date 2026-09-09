#!/usr/bin/env python3
"""stripe_webhook.pyの検証用テスト。`python3 test_stripe_webhook.py`で実行する。"""

import hashlib
import hmac
import json
import time

from stripe_webhook import (
    CheckoutSessionCompletedResult,
    CustomerSubscriptionDeletedResult,
    CustomerSubscriptionUpdatedResult,
    handle_checkout_session_completed,
    handle_customer_subscription_deleted,
    handle_customer_subscription_updated,
    receive_stripe_webhook,
    verify_stripe_signature,
)
from subscription_cancellation_notification import (
    InMemoryLinePushClient,
    LinePushDeliveryError,
    OUTCOME_CANCELLATION_RESCHEDULED,
    OUTCOME_CANCELLATION_SCHEDULED,
    OUTCOME_NO_CHANGE,
    SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE,
    SUBSCRIPTION_CANCELLED_MESSAGE,
)
from usage_counter_workshop import InMemoryWorkshopStore


class _FailingPushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("send failed")

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


WEBHOOK_SECRET = "whsec_test_secret"


def _sign(payload: bytes, timestamp: int, secret: str = WEBHOOK_SECRET) -> str:
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    v1 = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={v1}"


# --- verify_stripe_signature ---


def test_verify_rejects_missing_header():
    check(
        "署名ヘッダなしはFalse",
        verify_stripe_signature(b"{}", None, WEBHOOK_SECRET) is False,
    )


def test_verify_rejects_malformed_header():
    check(
        "t/v1を含まない不正な形式はFalse",
        verify_stripe_signature(b"{}", "garbage", WEBHOOK_SECRET) is False,
    )


def test_verify_accepts_valid_signature():
    payload = b'{"type": "checkout.session.completed"}'
    now = 1_700_000_000
    header = _sign(payload, now)
    check(
        "正しい署名・許容範囲内の時刻はTrue",
        verify_stripe_signature(payload, header, WEBHOOK_SECRET, now=now) is True,
    )


def test_verify_rejects_wrong_secret():
    payload = b'{"type": "checkout.session.completed"}'
    now = 1_700_000_000
    header = _sign(payload, now, secret="whsec_wrong")
    check(
        "誤ったwebhook_secretで署名した場合はFalse",
        verify_stripe_signature(payload, header, WEBHOOK_SECRET, now=now) is False,
    )


def test_verify_rejects_stale_timestamp():
    payload = b'{"type": "checkout.session.completed"}'
    now = 1_700_000_000
    header = _sign(payload, now)
    check(
        "許容誤差(300秒)を超えたタイムスタンプはFalse",
        verify_stripe_signature(payload, header, WEBHOOK_SECRET, now=now + 301) is False,
    )


def test_verify_accepts_any_matching_v1_during_rotation():
    payload = b'{"type": "checkout.session.completed"}'
    now = 1_700_000_000
    old_sig = _sign(payload, now, secret="whsec_old").split(",")[1]
    new_sig = _sign(payload, now, secret=WEBHOOK_SECRET).split(",")[1]
    header = f"t={now},{old_sig},{new_sig}"
    check(
        "複数v1のうち新シークレットに一致する方があればTrue",
        verify_stripe_signature(payload, header, WEBHOOK_SECRET, now=now) is True,
    )


# --- handle_checkout_session_completed ---


def test_handle_returns_invalid_when_client_reference_id_missing():
    store = InMemoryWorkshopStore()
    result = handle_checkout_session_completed({"customer": "cus_1"}, store)
    check("client_reference_id欠落はinvalid=True", result.invalid is True)


def test_handle_returns_invalid_when_client_reference_id_empty():
    store = InMemoryWorkshopStore()
    result = handle_checkout_session_completed(
        {"client_reference_id": "", "customer": "cus_1"}, store
    )
    check("client_reference_id空文字列はinvalid=True", result.invalid is True)


def test_handle_writes_stripe_customer_id_when_unset():
    store = InMemoryWorkshopStore()
    result = handle_checkout_session_completed(
        {"client_reference_id": "W1", "customer": "cus_new"}, store
    )
    check("未設定時はstripe_customer_idを書き込む", store.get_stripe_customer_id("W1") == "cus_new")
    check("stripe_customer_id_written=True", result.stripe_customer_id_written is True)


def test_handle_sets_subscription_status_active():
    store = InMemoryWorkshopStore()
    handle_checkout_session_completed({"client_reference_id": "W2", "customer": "cus_2"}, store)
    check("subscription_statusがactiveへ遷移", store.get_subscription_status("W2") == "active")


def test_handle_does_not_overwrite_existing_stripe_customer_id():
    store = InMemoryWorkshopStore()
    store.set_stripe_customer_id("W3", "cus_original")
    result = handle_checkout_session_completed(
        {"client_reference_id": "W3", "customer": "cus_different"}, store
    )
    check(
        "既存customer_idが設定済みなら上書きしない",
        store.get_stripe_customer_id("W3") == "cus_original",
    )
    check("stripe_customer_id_written=False", result.stripe_customer_id_written is False)
    check(
        "既存customer_id設定済みでもsubscription_statusはactiveへ更新",
        store.get_subscription_status("W3") == "active",
    )


def test_handle_returns_workshop_id_on_success():
    store = InMemoryWorkshopStore()
    result = handle_checkout_session_completed(
        {"client_reference_id": "W4", "customer": "cus_4"}, store
    )
    check("成功時はworkshop_idを返す", result.workshop_id == "W4")
    check("成功時はinvalid=False", result.invalid is False)


# --- handle_customer_subscription_deleted ---


def test_deleted_returns_invalid_when_customer_missing():
    store = InMemoryWorkshopStore()
    result = handle_customer_subscription_deleted({}, store)
    check("customer欠落はinvalid=True", result.invalid is True)


def test_deleted_returns_unresolved_when_customer_unknown():
    store = InMemoryWorkshopStore()
    result = handle_customer_subscription_deleted({"customer": "cus_unknown"}, store)
    check("紐付け無しのcustomerはunresolved=True", result.unresolved is True)
    check("unresolved時はinvalid=False", result.invalid is False)


def test_deleted_sets_subscription_status_canceled():
    store = InMemoryWorkshopStore()
    store.set_stripe_customer_id("W8", "cus_8")
    store.set_subscription_status("W8", "active")
    result = handle_customer_subscription_deleted({"customer": "cus_8"}, store)
    check("subscription_statusがcanceledへ遷移", store.get_subscription_status("W8") == "canceled")
    check("成功時はworkshop_idを返す", result.workshop_id == "W8")
    check("成功時はinvalid=False・unresolved=False", not result.invalid and not result.unresolved)
    check("push_client未指定時はnotified=False", result.notified is False)


def test_deleted_sends_notification_to_contractor_when_push_client_given():
    store = InMemoryWorkshopStore()
    store.set_members("W10", contractor_user_id="contractor_10", member_user_ids=["contractor_10", "member_10"])
    store.set_stripe_customer_id("W10", "cus_10")
    store.set_subscription_status("W10", "active")
    push = InMemoryLinePushClient()
    result = handle_customer_subscription_deleted(
        {"customer": "cus_10"}, store, push_client=push
    )
    check("push_client指定時はnotified=True", result.notified is True)
    check("送信先は契約者本人のuser_id", push.sent == [("contractor_10", SUBSCRIPTION_CANCELLED_MESSAGE)])
    check("subscription_statusはcanceledへ遷移", store.get_subscription_status("W10") == "canceled")


def test_deleted_status_update_independent_of_notification_failure():
    store = InMemoryWorkshopStore()
    store.set_members("W11", contractor_user_id="contractor_11", member_user_ids=["contractor_11"])
    store.set_stripe_customer_id("W11", "cus_11")
    store.set_subscription_status("W11", "active")
    result = handle_customer_subscription_deleted(
        {"customer": "cus_11"}, store, push_client=_FailingPushClient()
    )
    check("通知送信失敗時もnotified=False", result.notified is False)
    check(
        "通知送信失敗時もsubscription_statusはcanceledへ更新される",
        store.get_subscription_status("W11") == "canceled",
    )


# --- handle_customer_subscription_updated ---


def _updated_event(customer="cus_20", before=False, after=True, current_period_end=1_760_000_000):
    previous_attributes = {}
    if before != after:
        previous_attributes["cancel_at_period_end"] = before
    return {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": customer,
                "cancel_at_period_end": after,
                "current_period_end": current_period_end,
            },
            "previous_attributes": previous_attributes,
        },
    }


def test_updated_returns_invalid_when_customer_missing():
    store = InMemoryWorkshopStore()
    result = handle_customer_subscription_updated({"data": {"object": {}}}, store)
    check("customer欠落はinvalid=True", result.invalid is True)


def test_updated_returns_unresolved_when_customer_unknown():
    store = InMemoryWorkshopStore()
    result = handle_customer_subscription_updated(
        _updated_event(customer="cus_unknown"), store
    )
    check("紐付け無しのcustomerはunresolved=True", result.unresolved is True)


def test_updated_without_push_client_does_not_notify():
    store = InMemoryWorkshopStore()
    store.set_stripe_customer_id("W20", "cus_20")
    result = handle_customer_subscription_updated(_updated_event(), store)
    check("push_client未指定時はnotified=False", result.notified is False)
    check("workshop_idは返す", result.workshop_id == "W20")


def test_updated_scheduled_notifies_contractor():
    store = InMemoryWorkshopStore()
    store.set_members("W21", contractor_user_id="contractor_21", member_user_ids=["contractor_21"])
    store.set_stripe_customer_id("W21", "cus_21")
    push = InMemoryLinePushClient()
    result = handle_customer_subscription_updated(
        _updated_event(customer="cus_21", before=False, after=True), store, push_client=push
    )
    check("outcome=cancellation_scheduled", result.outcome == OUTCOME_CANCELLATION_SCHEDULED)
    check("notified=True", result.notified is True)
    check("契約者へ送信される", len(push.sent) == 1 and push.sent[0][0] == "contractor_21")


def test_updated_rescheduled_notifies_contractor():
    store = InMemoryWorkshopStore()
    store.set_members("W22", contractor_user_id="contractor_22", member_user_ids=["contractor_22"])
    store.set_stripe_customer_id("W22", "cus_22")
    push = InMemoryLinePushClient()
    result = handle_customer_subscription_updated(
        _updated_event(customer="cus_22", before=True, after=False), store, push_client=push
    )
    check("outcome=cancellation_rescheduled", result.outcome == OUTCOME_CANCELLATION_RESCHEDULED)
    check(
        "解約取り消しメッセージが送信される",
        push.sent == [("contractor_22", SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE)],
    )


def test_updated_no_change_sends_nothing():
    store = InMemoryWorkshopStore()
    store.set_members("W23", contractor_user_id="contractor_23", member_user_ids=["contractor_23"])
    store.set_stripe_customer_id("W23", "cus_23")
    push = InMemoryLinePushClient()
    result = handle_customer_subscription_updated(
        _updated_event(customer="cus_23", before=False, after=False), store, push_client=push
    )
    check("outcome=no_change", result.outcome == OUTCOME_NO_CHANGE)
    check("送信は行われない", push.sent == [])


# --- receive_stripe_webhook ---


def _event_body(workshop_id="W5", customer="cus_5", event_type="checkout.session.completed"):
    return json.dumps(
        {
            "type": event_type,
            "data": {"object": {"client_reference_id": workshop_id, "customer": customer}},
        }
    ).encode("utf-8")


def test_receive_rejects_invalid_signature():
    store = InMemoryWorkshopStore()
    result = receive_stripe_webhook(
        _event_body(), "t=1,v1=wrong", WEBHOOK_SECRET, workshop_store=store
    )
    check("署名不正時は400", result.status_code == 400)
    check("エラーコードinvalid_signature", result.error == "invalid_signature")
    check(
        "署名不正時はworkshop_storeへ一切書き込まれない",
        store.get_subscription_status("W5") == "trialing",
    )


def test_receive_rejects_invalid_json():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = b"not json"
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("不正なJSONは400", result.status_code == 400)
    check("エラーコードinvalid_json", result.error == "invalid_json")


def test_receive_ignores_unhandled_event_type():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = _event_body(event_type="invoice.payment_failed")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("未対応イベント種別も200", result.status_code == 200)
    check(
        "未対応イベント種別はignored_typeに元のtypeを格納",
        result.ignored_type == "invoice.payment_failed",
    )
    check(
        "未対応イベント種別はworkshop_storeへ書き込まれない",
        store.get_subscription_status("W5") == "trialing",
    )


def test_receive_dispatches_customer_subscription_deleted():
    store = InMemoryWorkshopStore()
    store.set_stripe_customer_id("W9", "cus_9")
    store.set_subscription_status("W9", "active")
    now = int(time.time())
    body = _event_body(customer="cus_9", event_type="customer.subscription.deleted")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("正常系は200", result.status_code == 200)
    check("workshop_idを返す", result.workshop_id == "W9")
    check("workshop_storeが更新される", store.get_subscription_status("W9") == "canceled")


def test_receive_dispatches_push_client_on_customer_subscription_deleted():
    store = InMemoryWorkshopStore()
    store.set_members("W12", contractor_user_id="contractor_12", member_user_ids=["contractor_12"])
    store.set_stripe_customer_id("W12", "cus_12")
    store.set_subscription_status("W12", "active")
    push = InMemoryLinePushClient()
    now = int(time.time())
    body = _event_body(customer="cus_12", event_type="customer.subscription.deleted")
    header = _sign(body, now)
    result = receive_stripe_webhook(
        body, header, WEBHOOK_SECRET, workshop_store=store, push_client=push
    )
    check("正常系は200", result.status_code == 200)
    check("契約者へ通知が送信される", push.sent == [("contractor_12", SUBSCRIPTION_CANCELLED_MESSAGE)])


def test_receive_returns_200_for_unresolved_customer_on_deleted():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = _event_body(customer="cus_unmapped", event_type="customer.subscription.deleted")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("紐付け無しcustomerでも200(Stripe側の再送を避ける)", result.status_code == 200)
    check("unresolved_customer=True", result.unresolved_customer is True)


def test_receive_returns_400_for_missing_customer_on_deleted():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = json.dumps(
        {"type": "customer.subscription.deleted", "data": {"object": {}}}
    ).encode("utf-8")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("customer欠落は400", result.status_code == 400)
    check("エラーコードmissing_customer", result.error == "missing_customer")


def _updated_event_body(customer="cus_24", before=False, after=True):
    previous_attributes = {}
    if before != after:
        previous_attributes["cancel_at_period_end"] = before
    return json.dumps(
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": customer,
                    "cancel_at_period_end": after,
                    "current_period_end": 1_760_000_000,
                },
                "previous_attributes": previous_attributes,
            },
        }
    ).encode("utf-8")


def test_receive_dispatches_customer_subscription_updated():
    store = InMemoryWorkshopStore()
    store.set_members("W24", contractor_user_id="contractor_24", member_user_ids=["contractor_24"])
    store.set_stripe_customer_id("W24", "cus_24")
    push = InMemoryLinePushClient()
    now = int(time.time())
    body = _updated_event_body(customer="cus_24", before=False, after=True)
    header = _sign(body, now)
    result = receive_stripe_webhook(
        body, header, WEBHOOK_SECRET, workshop_store=store, push_client=push
    )
    check("正常系は200", result.status_code == 200)
    check("workshop_idを返す", result.workshop_id == "W24")
    check("契約者へ解約予約受理通知が送信される", len(push.sent) == 1 and push.sent[0][0] == "contractor_24")


def test_receive_returns_200_for_unresolved_customer_on_updated():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = _updated_event_body(customer="cus_unmapped_2")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("紐付け無しcustomerでも200(Stripe側の再送を避ける)", result.status_code == 200)
    check("unresolved_customer=True", result.unresolved_customer is True)


def test_receive_returns_400_for_missing_customer_on_updated():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = json.dumps(
        {"type": "customer.subscription.updated", "data": {"object": {}}}
    ).encode("utf-8")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("customer欠落は400", result.status_code == 400)
    check("エラーコードmissing_customer", result.error == "missing_customer")


def test_receive_dispatches_checkout_session_completed():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = _event_body(workshop_id="W6", customer="cus_6")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("正常系は200", result.status_code == 200)
    check("workshop_idを返す", result.workshop_id == "W6")
    check("workshop_storeが更新される", store.get_subscription_status("W6") == "active")


def test_receive_returns_400_when_workshop_store_missing():
    now = int(time.time())
    body = _event_body()
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET)
    check("workshop_store未指定は400", result.status_code == 400)
    check("エラーコードmissing_workshop_store", result.error == "missing_workshop_store")


def test_receive_returns_400_for_missing_client_reference_id():
    store = InMemoryWorkshopStore()
    now = int(time.time())
    body = json.dumps(
        {
            "type": "checkout.session.completed",
            "data": {"object": {"customer": "cus_7"}},
        }
    ).encode("utf-8")
    header = _sign(body, now)
    result = receive_stripe_webhook(body, header, WEBHOOK_SECRET, workshop_store=store)
    check("client_reference_id欠落は400", result.status_code == 400)
    check(
        "エラーコードmissing_client_reference_id",
        result.error == "missing_client_reference_id",
    )


if __name__ == "__main__":
    test_verify_rejects_missing_header()
    test_verify_rejects_malformed_header()
    test_verify_accepts_valid_signature()
    test_verify_rejects_wrong_secret()
    test_verify_rejects_stale_timestamp()
    test_verify_accepts_any_matching_v1_during_rotation()
    test_handle_returns_invalid_when_client_reference_id_missing()
    test_handle_returns_invalid_when_client_reference_id_empty()
    test_handle_writes_stripe_customer_id_when_unset()
    test_handle_sets_subscription_status_active()
    test_handle_does_not_overwrite_existing_stripe_customer_id()
    test_handle_returns_workshop_id_on_success()
    test_deleted_returns_invalid_when_customer_missing()
    test_deleted_returns_unresolved_when_customer_unknown()
    test_deleted_sets_subscription_status_canceled()
    test_deleted_sends_notification_to_contractor_when_push_client_given()
    test_deleted_status_update_independent_of_notification_failure()
    test_updated_returns_invalid_when_customer_missing()
    test_updated_returns_unresolved_when_customer_unknown()
    test_updated_without_push_client_does_not_notify()
    test_updated_scheduled_notifies_contractor()
    test_updated_rescheduled_notifies_contractor()
    test_updated_no_change_sends_nothing()
    test_receive_dispatches_customer_subscription_updated()
    test_receive_returns_200_for_unresolved_customer_on_updated()
    test_receive_returns_400_for_missing_customer_on_updated()
    test_receive_rejects_invalid_signature()
    test_receive_rejects_invalid_json()
    test_receive_ignores_unhandled_event_type()
    test_receive_dispatches_checkout_session_completed()
    test_receive_dispatches_customer_subscription_deleted()
    test_receive_dispatches_push_client_on_customer_subscription_deleted()
    test_receive_returns_200_for_unresolved_customer_on_deleted()
    test_receive_returns_400_for_missing_customer_on_deleted()
    test_receive_returns_400_when_workshop_store_missing()
    test_receive_returns_400_for_missing_client_reference_id()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
