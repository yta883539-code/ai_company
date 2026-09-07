#!/usr/bin/env python3
"""usage_counter_workshop.pyの検証用テスト。`python3 test_usage_counter_workshop.py`で実行する。"""

from datetime import datetime

from usage_counter_workshop import (
    InMemoryUsageCounterStore,
    InMemoryUserProfileStore,
    InMemoryWorkshopStore,
    MemberRemovedError,
    UnknownPlanError,
    WorkshopNotLinkedError,
    check_and_apply_pending_member_reduction,
    check_and_increment_usage,
    ensure_member_is_active,
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


def test_pending_reduction_not_yet_effective_does_nothing():
    _, workshops, _ = make_stores()
    workshops.set_members("W5", "CONTRACTOR", ["CONTRACTOR", "MEMBER2"])
    workshops.set_pending_reduction_effective_at("W5", MAR)

    r = check_and_apply_pending_member_reduction("W5", FEB, workshops)
    check("猶予期間中はNoneを返し何もしない", r is None)
    check("member_user_idsは変更されない", workshops.get_member_user_ids("W5") == ["CONTRACTOR", "MEMBER2"])


def test_pending_reduction_default_rule_keeps_contractor_only():
    _, workshops, _ = make_stores()
    workshops.set_members("W6", "CONTRACTOR", ["CONTRACTOR", "MEMBER2"])
    workshops.set_pending_reduction_effective_at("W6", FEB)

    r = check_and_apply_pending_member_reduction("W6", MAR, workshops)
    check("到達後は縮小が適用される", r.applied is True)
    check("契約者のみが残る", r.retained_user_id == "CONTRACTOR")
    check("MEMBER2が除外される", r.removed_user_ids == ["MEMBER2"])
    check("指定なしの場合specified_member_matchedはFalse", r.specified_member_matched is False)
    check("member_user_idsが契約者のみに更新される", workshops.get_member_user_ids("W6") == ["CONTRACTOR"])
    check(
        "pending_member_reduction_effective_atがクリアされる",
        workshops.get_pending_reduction_effective_at("W6") is None,
    )


def test_pending_reduction_specified_name_matches_contractor():
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W7",
        "CONTRACTOR",
        ["CONTRACTOR", "MEMBER2"],
        display_names={"CONTRACTOR": "山田太郎"},
    )
    workshops.set_pending_reduction_effective_at("W7", FEB)
    workshops.set_specified_retention_member_name("W7", "山田太郎")

    r = check_and_apply_pending_member_reduction("W7", MAR, workshops)
    check("契約者本人を指定した場合はspecified_member_matched=True", r.specified_member_matched is True)
    check("noteは記録されない", r.note is None)
    check("結果は契約者のみ残る", r.retained_user_id == "CONTRACTOR")


def test_pending_reduction_specified_name_mismatch_notes_and_keeps_default():
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W8",
        "CONTRACTOR",
        ["CONTRACTOR", "MEMBER2"],
        display_names={"CONTRACTOR": "山田太郎", "MEMBER2": "鈴木花子"},
    )
    workshops.set_pending_reduction_effective_at("W8", FEB)
    workshops.set_specified_retention_member_name("W8", "鈴木花子")

    r = check_and_apply_pending_member_reduction("W8", MAR, workshops)
    check("契約者以外を指定した場合はspecified_member_matched=False", r.specified_member_matched is False)
    check("noteに理由が記録される", r.note is not None and "鈴木花子" in r.note)
    check("それでも契約者のみが残る(デフォルトルール適用)", r.retained_user_id == "CONTRACTOR")


def test_pending_reduction_already_single_member_clears_flag_only():
    _, workshops, _ = make_stores()
    workshops.set_members("W9", "CONTRACTOR", ["CONTRACTOR"])
    workshops.set_pending_reduction_effective_at("W9", FEB)

    r = check_and_apply_pending_member_reduction("W9", MAR, workshops)
    check("既に1名の場合はapplied=False", r.applied is False)
    check(
        "pending_member_reduction_effective_atはクリアされる",
        workshops.get_pending_reduction_effective_at("W9") is None,
    )


def test_ensure_member_is_active_allows_contractor_and_current_members():
    _, workshops, _ = make_stores()
    workshops.set_members("W10", "CONTRACTOR", ["CONTRACTOR", "MEMBER2"])

    ensure_member_is_active("CONTRACTOR", "W10", workshops)
    ensure_member_is_active("MEMBER2", "W10", workshops)
    check("契約者・現メンバーは例外を送出しない", True)


def test_ensure_member_is_active_raises_for_removed_member():
    _, workshops, _ = make_stores()
    workshops.set_members("W11", "CONTRACTOR", ["CONTRACTOR", "MEMBER2"])
    workshops.set_pending_reduction_effective_at("W11", FEB)
    check_and_apply_pending_member_reduction("W11", MAR, workshops)

    try:
        ensure_member_is_active("MEMBER2", "W11", workshops)
        check("縮小で除外されたメンバーはMemberRemovedErrorが送出される", False)
    except MemberRemovedError:
        check("縮小で除外されたメンバーはMemberRemovedErrorが送出される", True)


if __name__ == "__main__":
    test_single_craftsman_light_within_limit()
    test_multi_craftsman_shared_counter()
    test_month_rollover_resets_count()
    test_workshop_not_linked_raises()
    test_unknown_plan_raises()
    test_pending_reduction_not_yet_effective_does_nothing()
    test_pending_reduction_default_rule_keeps_contractor_only()
    test_pending_reduction_specified_name_matches_contractor()
    test_pending_reduction_specified_name_mismatch_notes_and_keeps_default()
    test_pending_reduction_already_single_member_clears_flag_only()
    test_ensure_member_is_active_allows_contractor_and_current_members()
    test_ensure_member_is_active_raises_for_removed_member()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
