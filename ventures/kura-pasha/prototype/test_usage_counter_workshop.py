#!/usr/bin/env python3
"""usage_counter_workshop.pyの検証用テスト。`python3 test_usage_counter_workshop.py`で実行する。"""

from datetime import datetime

from usage_counter_workshop import (
    InMemoryUsageCounterStore,
    InMemoryUserProfileStore,
    InMemoryWorkshopStore,
    UnknownPlanError,
    WorkshopNotLinkedError,
    check_and_increment_usage,
)

FEB = datetime(2026, 2, 1, 9, 0, 0)
MAR = datetime(2026, 3, 1, 9, 0, 0)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def make_stores():
    return InMemoryUserProfileStore(), InMemoryWorkshopStore(), InMemoryUsageCounterStore()


def test_single_craftsman_light_within_limit():
    profiles, workshops, counters = make_stores()
    profiles.link("U1", "W1")
    workshops.set_plan("W1", "light")

    r = check_and_increment_usage("U1", FEB, profiles, workshops, counters)
    check("1回目はlight上限3回以内", r.within_limit is True)
    check("count_after_increment=1", r.count_after_increment == 1)
    check("plan_id=light", r.plan_id == "light")


def test_multi_craftsman_shared_counter():
    """複数職人プランで異なるuser_idが同一workshopを共有する場合、カウンタが
    workshop単位で合算されることを確認する(usage-counter-workshop-key-design.md
    1節が指摘した「抜け穴」が塞がれていることの検証)。
    """
    profiles, workshops, counters = make_stores()
    profiles.link("CONTRACTOR", "W2")
    profiles.link("MEMBER2", "W2")
    workshops.set_plan("W2", "multi_craftsman")

    for _ in range(19):
        check_and_increment_usage("CONTRACTOR", FEB, profiles, workshops, counters)
    r19 = check_and_increment_usage("MEMBER2", FEB, profiles, workshops, counters)
    check("契約者・メンバー分を合算して20回目でも上限内", r19.count_after_increment == 20)
    check("20回目はmulti_craftsman上限20回以内", r19.within_limit is True)

    r21 = check_and_increment_usage("CONTRACTOR", FEB, profiles, workshops, counters)
    check("21回目は上限超過", r21.within_limit is False)
    check("超過単価は150円", r21.overage_price_jpy == 150)


def test_month_rollover_resets_count():
    profiles, workshops, counters = make_stores()
    profiles.link("U3", "W3")
    workshops.set_plan("W3", "standard")

    for _ in range(8):
        check_and_increment_usage("U3", FEB, profiles, workshops, counters)
    r_feb_9 = check_and_increment_usage("U3", FEB, profiles, workshops, counters)
    check("2月9回目は上限超過", r_feb_9.within_limit is False)

    r_mar_1 = check_and_increment_usage("U3", MAR, profiles, workshops, counters)
    check("月替わりでcountが1にリセットされる", r_mar_1.count_after_increment == 1)
    check("3月1回目は上限内に戻る", r_mar_1.within_limit is True)


def test_workshop_not_linked_raises():
    profiles, workshops, counters = make_stores()
    try:
        check_and_increment_usage("UNKNOWN", FEB, profiles, workshops, counters)
        check("workshop未設定でWorkshopNotLinkedErrorが送出される", False)
    except WorkshopNotLinkedError:
        check("workshop未設定でWorkshopNotLinkedErrorが送出される", True)


def test_unknown_plan_raises():
    profiles, workshops, counters = make_stores()
    profiles.link("U4", "W4")
    workshops.set_plan("W4", "unknown_plan")
    try:
        check_and_increment_usage("U4", FEB, profiles, workshops, counters)
        check("不明なplan_idでUnknownPlanErrorが送出される", False)
    except UnknownPlanError:
        check("不明なplan_idでUnknownPlanErrorが送出される", True)


if __name__ == "__main__":
    test_single_craftsman_light_within_limit()
    test_multi_craftsman_shared_counter()
    test_month_rollover_resets_count()
    test_workshop_not_linked_raises()
    test_unknown_plan_raises()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
