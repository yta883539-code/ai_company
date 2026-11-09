#!/usr/bin/env python3
"""one_time_pass_store.pyのロジック検証(test_fan_pass_store.pyと同じ形式の素朴なassertベース
テスト、pytest等の外部依存を増やさない方針を踏襲)。
"""

from __future__ import annotations

from one_time_pass_store import (
    AlreadyConsumedError,
    InMemoryOneTimePassStore,
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
    store = InMemoryOneTimePassStore()
    internal_id, access_token = store.create(
        stripe_checkout_session_id="cs_1", created_at=1_000_000
    )

    by_token = store.get_by_access_token(access_token)
    check("get_by_access_token returns created one_time_pass", by_token is not None)
    check("internal_id matches", by_token.internal_id == internal_id)
    check("consumed_at starts out None", by_token.consumed_at is None)
    check(
        "expires_at is created_at + 24h",
        by_token.expires_at == 1_000_000 + 24 * 60 * 60,
    )

    by_session = store.get_by_checkout_session_id("cs_1")
    check("get_by_checkout_session_id returns same doc", by_session.internal_id == internal_id)


def test_create_is_idempotent_on_duplicate_webhook_delivery() -> None:
    store = InMemoryOneTimePassStore()
    internal_id_1, access_token_1 = store.create(
        stripe_checkout_session_id="cs_5", created_at=1_000_000
    )

    internal_id_2, access_token_2 = store.create(
        stripe_checkout_session_id="cs_5", created_at=2_000_000
    )

    check("duplicate create returns same internal_id", internal_id_1 == internal_id_2)
    check("duplicate create returns same access_token", access_token_1 == access_token_2)
    check(
        "created_at from the first call is kept (second call's value is ignored)",
        store.get_by_checkout_session_id("cs_5").created_at == 1_000_000,
    )


def test_get_by_unknown_token_or_session_returns_none() -> None:
    store = InMemoryOneTimePassStore()
    check("unknown access_token returns None", store.get_by_access_token("nope") is None)
    check(
        "unknown stripe_checkout_session_id returns None",
        store.get_by_checkout_session_id("cs_nope") is None,
    )


def test_mark_consumed() -> None:
    store = InMemoryOneTimePassStore()
    internal_id, access_token = store.create(
        stripe_checkout_session_id="cs_2", created_at=1_000_000
    )

    store.mark_consumed(internal_id, consumed_at=1_000_500)
    check(
        "consumed_at is set after mark_consumed",
        store.get_by_access_token(access_token).consumed_at == 1_000_500,
    )


def test_mark_consumed_twice_raises() -> None:
    store = InMemoryOneTimePassStore()
    internal_id, _ = store.create(stripe_checkout_session_id="cs_3", created_at=1_000_000)
    store.mark_consumed(internal_id, consumed_at=1_000_500)

    try:
        store.mark_consumed(internal_id, consumed_at=1_000_600)
        check("second mark_consumed raises AlreadyConsumedError", False)
    except AlreadyConsumedError:
        check("second mark_consumed raises AlreadyConsumedError", True)

    check(
        "consumed_at keeps the first value after the rejected second call",
        store.get_by_checkout_session_id("cs_3").consumed_at == 1_000_500,
    )


def test_unknown_internal_id_operations_raise() -> None:
    store = InMemoryOneTimePassStore()
    try:
        store.mark_consumed("unknown-id", consumed_at=1_000_000)
        check("mark_consumed on unknown internal_id raises", False)
    except UnknownInternalIdError:
        check("mark_consumed on unknown internal_id raises", True)


if __name__ == "__main__":
    test_create_and_lookup()
    test_create_is_idempotent_on_duplicate_webhook_delivery()
    test_get_by_unknown_token_or_session_returns_none()
    test_mark_consumed()
    test_mark_consumed_twice_raises()
    test_unknown_internal_id_operations_raise()
    print(f"PASS={PASS} FAIL={FAIL}")
