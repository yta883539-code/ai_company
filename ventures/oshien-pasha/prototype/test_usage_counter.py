#!/usr/bin/env python3
"""usage_counter.pyの検証用テスト。`python3 test_usage_counter.py`で実行する。"""

from datetime import datetime

import usage_counter
from usage_counter import (
    InMemoryUsageCounterStore,
    UnknownInternalIdError,
    current_month_jst,
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


def test_record_generation_raises_for_unregistered_internal_id():
    store = InMemoryUsageCounterStore()
    try:
        store.record_generation(
            "UNKNOWN",
            requested_at=datetime(2026, 11, 9, 10, 0, 0),
            venue_matched=True,
            input_performance_count=1,
        )
        check("record_generation raises for unregistered internal_id", False)
    except UnknownInternalIdError:
        check("record_generation raises for unregistered internal_id", True)


def test_get_current_month_count_raises_for_unregistered_internal_id():
    store = InMemoryUsageCounterStore()
    try:
        store.get_current_month_count("UNKNOWN")
        check("get_current_month_count raises for unregistered internal_id", False)
    except UnknownInternalIdError:
        check("get_current_month_count raises for unregistered internal_id", True)


def test_record_generation_increments_and_appends_log():
    store = InMemoryUsageCounterStore()
    store.register("F1")

    count_after_1 = store.record_generation(
        "F1",
        requested_at=datetime(2026, 11, 9, 10, 0, 0),
        venue_matched=True,
        input_performance_count=1,
    )
    count_after_2 = store.record_generation(
        "F1",
        requested_at=datetime(2026, 11, 9, 11, 0, 0),
        venue_matched=False,
        input_performance_count=2,
    )

    check("first record_generation returns 1", count_after_1 == 1)
    check("second record_generation returns 2", count_after_2 == 2)
    check("get_current_month_count reflects both records", store.get_current_month_count("F1") == 2)

    log = store.get_generation_log("F1")
    check("generation_log has 2 entries", len(log) == 2)
    check("generation_log entry 1 venue_matched is True", log[0].venue_matched is True)
    check("generation_log entry 2 input_performance_count is 2", log[1].input_performance_count == 2)


def test_record_generation_is_independent_per_internal_id():
    store = InMemoryUsageCounterStore()
    store.register("F1")
    store.register("F2")

    store.record_generation(
        "F1",
        requested_at=datetime(2026, 11, 9, 10, 0, 0),
        venue_matched=True,
        input_performance_count=1,
    )

    check("F1 count is 1", store.get_current_month_count("F1") == 1)
    check("F2 count is still 0 (untouched)", store.get_current_month_count("F2") == 0)


def test_month_rollover_resets_count_on_record_generation():
    store = InMemoryUsageCounterStore()
    store.register("F1")

    original_current_month_jst = usage_counter.current_month_jst
    try:
        usage_counter.current_month_jst = lambda: "2026-10"
        store.record_generation(
            "F1",
            requested_at=datetime(2026, 10, 31, 10, 0, 0),
            venue_matched=True,
            input_performance_count=1,
        )
        check("count is 1 in 2026-10", store.get_current_month_count("F1") == 1)

        usage_counter.current_month_jst = lambda: "2026-11"
        check(
            "get_current_month_count returns 0 for stale month without writing",
            store.get_current_month_count("F1") == 0,
        )

        count_after_rollover = store.record_generation(
            "F1",
            requested_at=datetime(2026, 11, 1, 0, 30, 0),
            venue_matched=True,
            input_performance_count=1,
        )
        check("record_generation resets count to 1 after month rollover", count_after_rollover == 1)
    finally:
        usage_counter.current_month_jst = original_current_month_jst


def test_current_month_jst_returns_yyyy_mm_format():
    month = current_month_jst()
    check("current_month_jst returns 7-character YYYY-MM string", len(month) == 7 and month[4] == "-")


if __name__ == "__main__":
    test_record_generation_raises_for_unregistered_internal_id()
    test_get_current_month_count_raises_for_unregistered_internal_id()
    test_record_generation_increments_and_appends_log()
    test_record_generation_is_independent_per_internal_id()
    test_month_rollover_resets_count_on_record_generation()
    test_current_month_jst_returns_yyyy_mm_format()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
