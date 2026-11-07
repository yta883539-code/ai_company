#!/usr/bin/env python3
"""fan_pass_store.pyのロジック検証(usage_counter.pyのtest_usage_counter.pyと同じ形式の
素朴なassertベーステスト、pytest等の外部依存を増やさない方針を踏襲)。
"""

from __future__ import annotations

from fan_pass_store import (
    InMemoryFanPassStore,
    InvalidSubscriptionStatusError,
    UnknownInternalIdError,
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


def test_create_and_lookup() -> None:
    store = InMemoryFanPassStore()
    internal_id, access_token = store.create(
        email="fan@example.com",
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
    )

    by_token = store.get_by_access_token(access_token)
    check("get_by_access_token returns created fan_pass", by_token is not None)
    check("internal_id matches", by_token.internal_id == internal_id)
    check("initial subscription_status is active", by_token.subscription_status == "active")

    by_sub = store.get_by_stripe_subscription_id("sub_1")
    check("get_by_stripe_subscription_id returns same doc", by_sub.internal_id == internal_id)


def test_create_is_idempotent_on_duplicate_webhook_delivery() -> None:
    store = InMemoryFanPassStore()
    internal_id_1, access_token_1 = store.create(
        email="fan@example.com", stripe_customer_id="cus_5", stripe_subscription_id="sub_5"
    )

    internal_id_2, access_token_2 = store.create(
        email="fan@example.com", stripe_customer_id="cus_5", stripe_subscription_id="sub_5"
    )

    check("duplicate create returns same internal_id", internal_id_1 == internal_id_2)
    check("duplicate create returns same access_token", access_token_1 == access_token_2)
    check(
        "no second document is registered for the same subscription_id",
        store.get_by_stripe_subscription_id("sub_5").internal_id == internal_id_1,
    )


def test_get_by_unknown_token_or_subscription_returns_none() -> None:
    store = InMemoryFanPassStore()
    check("unknown access_token returns None", store.get_by_access_token("nope") is None)
    check(
        "unknown stripe_subscription_id returns None",
        store.get_by_stripe_subscription_id("sub_nope") is None,
    )


def test_update_subscription_status() -> None:
    store = InMemoryFanPassStore()
    internal_id, access_token = store.create(
        email="fan@example.com", stripe_customer_id="cus_2", stripe_subscription_id="sub_2"
    )

    store.update_subscription_status(internal_id, "canceled")
    check(
        "subscription_status updated to canceled",
        store.get_by_access_token(access_token).subscription_status == "canceled",
    )

    store.update_subscription_status(internal_id, "active")
    check(
        "subscription_status can revert to active (customer.subscription.created再加入)",
        store.get_by_access_token(access_token).subscription_status == "active",
    )


def test_update_subscription_status_with_event_time_guard() -> None:
    store = InMemoryFanPassStore()
    internal_id, access_token = store.create(
        email="fan@example.com", stripe_customer_id="cus_6", stripe_subscription_id="sub_6"
    )

    store.update_subscription_status(internal_id, "canceled", event_time=200)
    check(
        "first event_time-bearing update applies unconditionally",
        store.get_by_access_token(access_token).subscription_status == "canceled",
    )

    store.update_subscription_status(internal_id, "active", event_time=100)
    check(
        "stale (older) event_time is skipped, status unchanged",
        store.get_by_access_token(access_token).subscription_status == "canceled",
    )

    store.update_subscription_status(internal_id, "active", event_time=200)
    check(
        "event_time equal to last applied is also treated as stale",
        store.get_by_access_token(access_token).subscription_status == "canceled",
    )

    store.update_subscription_status(internal_id, "active", event_time=300)
    check(
        "newer event_time applies",
        store.get_by_access_token(access_token).subscription_status == "active",
    )


def test_update_subscription_status_without_event_time_always_applies() -> None:
    store = InMemoryFanPassStore()
    internal_id, access_token = store.create(
        email="fan@example.com", stripe_customer_id="cus_7", stripe_subscription_id="sub_7"
    )

    store.update_subscription_status(internal_id, "canceled", event_time=500)
    store.update_subscription_status(internal_id, "active")
    check(
        "omitting event_time applies unconditionally even after an event_time-bearing update",
        store.get_by_access_token(access_token).subscription_status == "active",
    )


def test_update_subscription_status_rejects_invalid_value() -> None:
    store = InMemoryFanPassStore()
    internal_id, _ = store.create(
        email="fan@example.com", stripe_customer_id="cus_3", stripe_subscription_id="sub_3"
    )
    try:
        store.update_subscription_status(internal_id, "trialing")
        check("invalid status raises InvalidSubscriptionStatusError", False)
    except InvalidSubscriptionStatusError:
        check("invalid status raises InvalidSubscriptionStatusError", True)


def test_reissue_access_token_invalidates_old_token() -> None:
    store = InMemoryFanPassStore()
    internal_id, old_token = store.create(
        email="fan@example.com", stripe_customer_id="cus_4", stripe_subscription_id="sub_4"
    )

    store.reissue_access_token(internal_id, new_access_token="new-token-xyz")

    check("old access_token is invalidated", store.get_by_access_token(old_token) is None)
    new_doc = store.get_by_access_token("new-token-xyz")
    check("new access_token resolves to same internal_id", new_doc.internal_id == internal_id)


def test_unknown_internal_id_operations_raise() -> None:
    store = InMemoryFanPassStore()
    try:
        store.update_subscription_status("unknown-id", "active")
        check("update_subscription_status on unknown internal_id raises", False)
    except UnknownInternalIdError:
        check("update_subscription_status on unknown internal_id raises", True)

    try:
        store.reissue_access_token("unknown-id", new_access_token="x")
        check("reissue_access_token on unknown internal_id raises", False)
    except UnknownInternalIdError:
        check("reissue_access_token on unknown internal_id raises", True)


if __name__ == "__main__":
    test_create_and_lookup()
    test_create_is_idempotent_on_duplicate_webhook_delivery()
    test_get_by_unknown_token_or_subscription_returns_none()
    test_update_subscription_status()
    test_update_subscription_status_with_event_time_guard()
    test_update_subscription_status_without_event_time_always_applies()
    test_update_subscription_status_rejects_invalid_value()
    test_reissue_access_token_invalidates_old_token()
    test_unknown_internal_id_operations_raise()
    print(f"PASS={PASS} FAIL={FAIL}")
