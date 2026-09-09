#!/usr/bin/env python3
"""stripe_webhook.pyの検証用テスト。`python3 test_stripe_webhook.py`で実行する。"""

import hashlib
import hmac
import json
import time

from stripe_webhook import (
    CheckoutSessionCompletedResult,
    CustomerSubscriptionDeletedResult,
    handle_checkout_session_completed,
    handle_customer_subscription_deleted,
    receive_stripe_webhook,
    verify_stripe_signature,
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
    test_receive_rejects_invalid_signature()
    test_receive_rejects_invalid_json()
    test_receive_ignores_unhandled_event_type()
    test_receive_dispatches_checkout_session_completed()
    test_receive_dispatches_customer_subscription_deleted()
    test_receive_returns_200_for_unresolved_customer_on_deleted()
    test_receive_returns_400_for_missing_customer_on_deleted()
    test_receive_returns_400_when_workshop_store_missing()
    test_receive_returns_400_for_missing_client_reference_id()

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        raise SystemExit(1)
