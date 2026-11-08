#!/usr/bin/env python3
"""stripe_webhook.pyのロジック検証(test_fan_pass_store.pyと同じ形式の素朴なassertベース
テスト、pytest等の外部依存を増やさない方針を踏襲)。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from fan_pass_store import InMemoryFanPassStore
from stripe_webhook import (
    dispatch_stripe_event,
    receive_stripe_webhook,
    verify_stripe_signature,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def _sign(payload: bytes, secret: str, *, timestamp: int) -> str:
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def test_verify_stripe_signature_valid_and_invalid() -> None:
    secret = "whsec_test"
    payload = b'{"id":"evt_1"}'
    now = int(time.time())
    header = _sign(payload, secret, timestamp=now)
    check("valid signature verifies", verify_stripe_signature(payload, header, secret, now=now))
    check("missing header fails", not verify_stripe_signature(payload, None, secret, now=now))
    check(
        "wrong secret fails",
        not verify_stripe_signature(payload, header, "whsec_other", now=now),
    )
    check(
        "expired timestamp fails",
        not verify_stripe_signature(payload, header, secret, now=now + 1000),
    )


def test_checkout_session_completed_subscription_creates_fan_pass() -> None:
    store = InMemoryFanPassStore()
    event = {
        "type": "checkout.session.completed",
        "created": 1700000000,
        "data": {
            "object": {
                "mode": "subscription",
                "customer": "cus_1",
                "subscription": "sub_1",
                "customer_details": {"email": "fan@example.com"},
            }
        },
    }
    result = dispatch_stripe_event(event, store)
    check("handled", result.handled)
    check("action is fan_pass_created", result.action == "fan_pass_created")
    fan_pass = store.get_by_stripe_subscription_id("sub_1")
    check("fan_pass created with active status", fan_pass is not None and fan_pass.subscription_status == "active")


def test_checkout_session_completed_payment_mode_ignored() -> None:
    store = InMemoryFanPassStore()
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "mode": "payment",
                "customer": "cus_2",
                "subscription": None,
                "customer_details": {"email": "fan@example.com"},
            }
        },
    }
    result = dispatch_stripe_event(event, store)
    check("mode=payment is ignored", not result.handled and result.action == "ignored_mode")
    check("no fan_pass created", store.get_by_stripe_subscription_id("sub_2") is None)


def test_subscription_deleted_cancels_fan_pass() -> None:
    store = InMemoryFanPassStore()
    internal_id, _ = store.create(email="fan@example.com", stripe_customer_id="cus_3", stripe_subscription_id="sub_3")
    event = {
        "type": "customer.subscription.deleted",
        "created": 1700000100,
        "data": {"object": {"id": "sub_3"}},
    }
    result = dispatch_stripe_event(event, store)
    check("handled", result.handled and result.action == "subscription_deleted")
    check(
        "status becomes canceled",
        store.get_by_stripe_subscription_id("sub_3").subscription_status == "canceled",
    )


def test_subscription_created_reactivates_existing_only() -> None:
    store = InMemoryFanPassStore()
    internal_id, _ = store.create(email="fan@example.com", stripe_customer_id="cus_4", stripe_subscription_id="sub_4")
    store.update_subscription_status(internal_id, "canceled", event_time=1700000000)

    # 既存ドキュメントが見つかる場合は再加入としてactiveに戻す。
    reactivate_event = {
        "type": "customer.subscription.created",
        "created": 1700000200,
        "data": {"object": {"id": "sub_4"}},
    }
    result = dispatch_stripe_event(reactivate_event, store)
    check("reactivation handled", result.handled and result.action == "subscription_reactivated")
    check(
        "status becomes active again",
        store.get_by_stripe_subscription_id("sub_4").subscription_status == "active",
    )

    # 新規契約相当(既存ドキュメントが見つからない)は何もしない。
    new_contract_event = {
        "type": "customer.subscription.created",
        "created": 1700000300,
        "data": {"object": {"id": "sub_unknown"}},
    }
    result2 = dispatch_stripe_event(new_contract_event, store)
    check("unknown subscription is ignored", not result2.handled and result2.action == "ignored_new_contract")


def test_subscription_updated_maps_status() -> None:
    store = InMemoryFanPassStore()
    internal_id, _ = store.create(email="fan@example.com", stripe_customer_id="cus_5", stripe_subscription_id="sub_5")

    past_due_event = {
        "type": "customer.subscription.updated",
        "created": 1700000400,
        "data": {"object": {"id": "sub_5", "status": "past_due"}},
    }
    dispatch_stripe_event(past_due_event, store)
    check(
        "past_due maps to canceled",
        store.get_by_stripe_subscription_id("sub_5").subscription_status == "canceled",
    )

    trialing_event = {
        "type": "customer.subscription.updated",
        "created": 1700000500,
        "data": {"object": {"id": "sub_5", "status": "trialing"}},
    }
    dispatch_stripe_event(trialing_event, store)
    check(
        "trialing maps to active",
        store.get_by_stripe_subscription_id("sub_5").subscription_status == "active",
    )


def test_subscription_status_change_unknown_subscription_is_safe() -> None:
    store = InMemoryFanPassStore()
    event = {
        "type": "customer.subscription.deleted",
        "created": 1700000600,
        "data": {"object": {"id": "sub_does_not_exist"}},
    }
    result = dispatch_stripe_event(event, store)
    check("unknown subscription does not raise", not result.handled and result.error == "fan_pass_not_found")


def test_ignored_event_type() -> None:
    store = InMemoryFanPassStore()
    event = {"type": "invoice.paid", "data": {"object": {}}}
    result = dispatch_stripe_event(event, store)
    check("unrelated event type is ignored", not result.handled and result.action == "ignored_type")


def test_receive_stripe_webhook_end_to_end() -> None:
    store = InMemoryFanPassStore()
    secret = "whsec_e2e"
    payload = json.dumps(
        {
            "id": "evt_e2e",
            "type": "checkout.session.completed",
            "created": 1700000700,
            "data": {
                "object": {
                    "mode": "subscription",
                    "customer": "cus_6",
                    "subscription": "sub_6",
                    "customer_details": {"email": "fan@example.com"},
                }
            },
        }
    ).encode("utf-8")
    now = 1700000700
    header = _sign(payload, secret, timestamp=now)

    result = receive_stripe_webhook(payload, header, secret, store=store, now=now)
    check("status_code 200", result.status_code == 200)
    check("dispatch handled", result.dispatch_result is not None and result.dispatch_result.handled)
    check("fan_pass created end-to-end", store.get_by_stripe_subscription_id("sub_6") is not None)

    bad_result = receive_stripe_webhook(payload, "t=1,v1=bad", secret, store=store, now=now)
    check("invalid signature returns 401", bad_result.status_code == 401)

    bad_payload = b"not json"
    bad_header = _sign(bad_payload, secret, timestamp=now)
    invalid_json_result = receive_stripe_webhook(bad_payload, bad_header, secret, store=store, now=now)
    check("invalid json returns 400", invalid_json_result.status_code == 400)


if __name__ == "__main__":
    test_verify_stripe_signature_valid_and_invalid()
    test_checkout_session_completed_subscription_creates_fan_pass()
    test_checkout_session_completed_payment_mode_ignored()
    test_subscription_deleted_cancels_fan_pass()
    test_subscription_created_reactivates_existing_only()
    test_subscription_updated_maps_status()
    test_subscription_status_change_unknown_subscription_is_safe()
    test_ignored_event_type()
    test_receive_stripe_webhook_end_to_end()
    print(f"PASS={PASS} FAIL={FAIL}")
