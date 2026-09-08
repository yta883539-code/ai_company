#!/usr/bin/env python3
"""usage_counter_workshop.pyの検証用テスト。`python3 test_usage_counter_workshop.py`で実行する。"""

from datetime import datetime, timedelta

from usage_counter_workshop import (
    MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_CONFIRMATION,
    MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_EXPIRED_NOTICE,
    MESSAGE_CONTEXT_GENERATION_REQUEST,
    MESSAGE_CONTEXT_MEMBER_RETENTION_NOTICE,
    ContractorTransferTargetNotFoundError,
    InMemoryUsageCounterStore,
    InMemoryUserProfileStore,
    InMemoryWorkshopStore,
    MemberRemovedError,
    UnknownPlanError,
    WorkshopNotLinkedError,
    apply_contractor_transfer,
    cancel_pending_contractor_transfer,
    check_and_apply_pending_member_reduction,
    check_and_expire_pending_contractor_transfer,
    check_and_increment_usage,
    ensure_member_is_active,
    get_contractor_transfer_expired_notice_context,
    is_contractor_transfer_confirmation_context,
    process_generation_request,
    resolve_contractor_transfer_target,
    select_message_context,
    start_pending_contractor_transfer,
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


def test_process_generation_request_normal_case_no_pending_reduction():
    profiles, workshops, counters = make_stores()
    profiles.link("U12", "W12")
    workshops.set_plan("W12", "standard")
    workshops.set_members("W12", "U12", ["U12"])

    result = process_generation_request("U12", FEB, profiles, workshops, counters)
    check("縮小待ちなしの通常時はmember_reductionがNone", result.member_reduction is None)
    check("usageは1回目としてカウントされる", result.usage.count_after_increment == 1)


def test_process_generation_request_applies_reduction_before_usage_check():
    """猶予期間到達後の最初の生成リクエストで、縮小(1)→除外チェック(2)→
    カウント加算(3)が同一呼び出し内で正しい順序で行われることを検証する。
    契約者本人からのリクエストなので、縮小が適用されてもensure_member_is_activeは
    例外を送出せずusageまで到達する。
    """
    profiles, workshops, counters = make_stores()
    profiles.link("CONTRACTOR13", "W13")
    profiles.link("MEMBER13", "W13")
    workshops.set_plan("W13", "multi_craftsman")
    workshops.set_members("W13", "CONTRACTOR13", ["CONTRACTOR13", "MEMBER13"])
    workshops.set_pending_reduction_effective_at("W13", FEB)

    result = process_generation_request("CONTRACTOR13", MAR, profiles, workshops, counters)
    check("縮小が適用されmember_reduction.appliedはTrue", result.member_reduction.applied is True)
    check("除外されたのはMEMBER13", result.member_reduction.removed_user_ids == ["MEMBER13"])
    check("縮小適用後もcheck_and_increment_usageまで到達しカウントされる", result.usage.count_after_increment == 1)
    check("縮小後のmember_user_idsは契約者のみ", workshops.get_member_user_ids("W13") == ["CONTRACTOR13"])


def test_process_generation_request_raises_for_member_removed_in_same_call():
    """猶予期間到達後、除外される側のメンバーが生成リクエストを送ってきた場合、
    (1)の縮小適用で除外が確定した直後に(2)でMemberRemovedErrorが送出され、
    (3)のusageカウントには到達しない(=課金対象にならない)ことを検証する。
    """
    profiles, workshops, counters = make_stores()
    profiles.link("CONTRACTOR14", "W14")
    profiles.link("MEMBER14", "W14")
    workshops.set_plan("W14", "multi_craftsman")
    workshops.set_members("W14", "CONTRACTOR14", ["CONTRACTOR14", "MEMBER14"])
    workshops.set_pending_reduction_effective_at("W14", FEB)

    try:
        process_generation_request("MEMBER14", MAR, profiles, workshops, counters)
        check("除外対象メンバーはMemberRemovedErrorが送出される", False)
    except MemberRemovedError:
        check("除外対象メンバーはMemberRemovedErrorが送出される", True)
    check("除外された場合usage_counter_storeには何も書き込まれない", counters.get("W14") is None)


def test_process_generation_request_workshop_not_linked_raises():
    profiles, workshops, counters = make_stores()
    try:
        process_generation_request("UNKNOWN15", FEB, profiles, workshops, counters)
        check("workshop未設定でWorkshopNotLinkedErrorが送出される(統合版)", False)
    except WorkshopNotLinkedError:
        check("workshop未設定でWorkshopNotLinkedErrorが送出される(統合版)", True)


def test_resolve_contractor_transfer_target_matches_existing_member():
    """contractor-transfer-design.md 3節: 名指しされた相手が既存メンバーの表示名と
    一致する場合、そのuser_idが返る(status=contractor_transfer_selectionに対応)。
    """
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W16",
        "CONTRACTOR16",
        ["MEMBER16A", "MEMBER16B"],
        display_names={"CONTRACTOR16": "親方", "MEMBER16A": "弟子太郎", "MEMBER16B": "弟子次郎"},
    )

    target = resolve_contractor_transfer_target("W16", "弟子太郎", workshops)
    check("名指しされた既存メンバーのuser_idが返る", target == "MEMBER16A")


def test_resolve_contractor_transfer_target_ignores_contractor_self():
    """契約者自身の表示名を指定した場合は譲渡先として一致させない(自分自身への
    譲渡は意味を持たないため、既存メンバー〈契約者以外〉からのみ探す)。
    """
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W17",
        "CONTRACTOR17",
        ["MEMBER17"],
        display_names={"CONTRACTOR17": "親方", "MEMBER17": "弟子"},
    )

    target = resolve_contractor_transfer_target("W17", "親方", workshops)
    check("契約者自身の表示名は譲渡先として一致しない", target is None)


def test_resolve_contractor_transfer_target_returns_none_for_unknown_name():
    """workshopに参加していない第三者を指定した場合はNoneが返る
    (status=contractor_transfer_unclearに対応する呼び出し側の分岐条件)。
    """
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W18",
        "CONTRACTOR18",
        ["MEMBER18"],
        display_names={"CONTRACTOR18": "親方", "MEMBER18": "弟子"},
    )

    target = resolve_contractor_transfer_target("W18", "未加入の三郎", workshops)
    check("未加入の第三者はNoneが返る", target is None)


def test_apply_contractor_transfer_updates_contractor_and_keeps_previous_as_member():
    """契約者からの再確認応答後に確定処理を呼ぶと、contractor_user_idが更新され、
    旧契約者はmember_user_idsから自動的には外されない(3節の方針)。
    """
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W19",
        "CONTRACTOR19",
        ["MEMBER19"],
        display_names={"CONTRACTOR19": "親方", "MEMBER19": "弟子太郎"},
    )

    result = apply_contractor_transfer("W19", "MEMBER19", workshops)
    check("previous_contractor_user_idは旧契約者", result.previous_contractor_user_id == "CONTRACTOR19")
    check("new_contractor_user_idは新契約者", result.new_contractor_user_id == "MEMBER19")
    check("matched_display_nameは新契約者の表示名", result.matched_display_name == "弟子太郎")
    check("workshop_store側のcontractor_user_idも更新される", workshops.get_contractor_user_id("W19") == "MEMBER19")
    check("旧契約者はmember_user_idsに残る", "CONTRACTOR19" in workshops.get_member_user_ids("W19"))


def test_apply_contractor_transfer_raises_for_non_member():
    """workshop外(member_user_idsに含まれない)user_idを渡した場合は
    ContractorTransferTargetNotFoundErrorが送出される(2節のスコープ限定違反への防御)。
    """
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W20",
        "CONTRACTOR20",
        ["MEMBER20"],
        display_names={"CONTRACTOR20": "親方", "MEMBER20": "弟子"},
    )

    try:
        apply_contractor_transfer("W20", "OUTSIDER20", workshops)
        check("既存メンバー外への譲渡はContractorTransferTargetNotFoundError", False)
    except ContractorTransferTargetNotFoundError:
        check("既存メンバー外への譲渡はContractorTransferTargetNotFoundError", True)
    check("例外発生時はcontractor_user_idが変更されない", workshops.get_contractor_user_id("W20") == "CONTRACTOR20")


def test_start_pending_contractor_transfer_writes_expected_state():
    """contractor-transfer-confirmation-detection-design.md 1節: status=
    contractor_transfer_selection生成と同時にpending_contractor_transferを書き込み、
    expires_atはrequested_at(=now)+24時間になることを検証する。
    """
    _, workshops, _ = make_stores()
    workshops.set_members("W21", "CONTRACTOR21", ["MEMBER21"])

    pending = start_pending_contractor_transfer(
        "W21", "MEMBER21", "弟子太郎", FEB, workshops
    )
    check("candidate_user_idが記録される", pending.candidate_user_id == "MEMBER21")
    check("candidate_member_nameが記録される", pending.candidate_member_name == "弟子太郎")
    check("expires_atはrequested_at+24時間", pending.expires_at == FEB + timedelta(hours=24))
    stored = workshops.get_pending_contractor_transfer("W21")
    check("workshop_store側にも同じ内容が保存される", stored == pending)


def test_is_contractor_transfer_confirmation_context_true_for_contractor_within_expiry():
    _, workshops, _ = make_stores()
    workshops.set_members("W22", "CONTRACTOR22", ["MEMBER22"])
    start_pending_contractor_transfer("W22", "MEMBER22", "弟子", FEB, workshops)

    within_expiry = FEB + timedelta(hours=1)
    check(
        "契約者本人・期限内はTrue",
        is_contractor_transfer_confirmation_context("CONTRACTOR22", "W22", within_expiry, workshops) is True,
    )


def test_is_contractor_transfer_confirmation_context_false_for_non_contractor():
    _, workshops, _ = make_stores()
    workshops.set_members("W23", "CONTRACTOR23", ["MEMBER23"])
    start_pending_contractor_transfer("W23", "MEMBER23", "弟子", FEB, workshops)

    check(
        "契約者以外はFalse(6節・7a等の既存判定ルールをそのまま適用)",
        is_contractor_transfer_confirmation_context("MEMBER23", "W23", FEB, workshops) is False,
    )


def test_is_contractor_transfer_confirmation_context_false_when_no_pending():
    _, workshops, _ = make_stores()
    workshops.set_members("W24", "CONTRACTOR24", ["MEMBER24"])

    check(
        "pending_contractor_transfer未設定ならFalse",
        is_contractor_transfer_confirmation_context("CONTRACTOR24", "W24", FEB, workshops) is False,
    )


def test_is_contractor_transfer_confirmation_context_false_after_expiry():
    _, workshops, _ = make_stores()
    workshops.set_members("W25", "CONTRACTOR25", ["MEMBER25"])
    start_pending_contractor_transfer("W25", "MEMBER25", "弟子", FEB, workshops)

    after_expiry = FEB + timedelta(hours=24, minutes=1)
    check(
        "expires_atを過ぎるとFalse(4節: 通常メッセージとして扱う)",
        is_contractor_transfer_confirmation_context("CONTRACTOR25", "W25", after_expiry, workshops) is False,
    )


def test_apply_contractor_transfer_clears_pending_state():
    """1節: 確定処理(apply_contractor_transfer)実行時にpending_contractor_transferを
    削除することを検証する。
    """
    _, workshops, _ = make_stores()
    workshops.set_members(
        "W26", "CONTRACTOR26", ["MEMBER26"], display_names={"MEMBER26": "弟子太郎"}
    )
    start_pending_contractor_transfer("W26", "MEMBER26", "弟子太郎", FEB, workshops)

    apply_contractor_transfer("W26", "MEMBER26", workshops)
    check(
        "確定処理後はpending_contractor_transferが削除される",
        workshops.get_pending_contractor_transfer("W26") is None,
    )


def test_cancel_pending_contractor_transfer_clears_without_updating_contractor():
    """3節: kind=contractor_transfer_cancelledのとき、pending_contractor_transferを
    削除するのみでcontractor_user_idは更新しないことを検証する。
    """
    _, workshops, _ = make_stores()
    workshops.set_members("W27", "CONTRACTOR27", ["MEMBER27"])
    start_pending_contractor_transfer("W27", "MEMBER27", "弟子", FEB, workshops)

    cancel_pending_contractor_transfer("W27", workshops)
    check(
        "キャンセル後はpending_contractor_transferが削除される",
        workshops.get_pending_contractor_transfer("W27") is None,
    )
    check(
        "contractor_user_idは変更されない",
        workshops.get_contractor_user_id("W27") == "CONTRACTOR27",
    )


def test_check_and_expire_pending_contractor_transfer_clears_and_returns_when_expired():
    """4節: expires_atを過ぎたpending_contractor_transferを削除し、削除前の値を
    返すことを検証する(能動プッシュ通知は行わない方針のため戻り値は呼び出し側の
    受動案内判定にのみ使う想定)。
    """
    _, workshops, _ = make_stores()
    workshops.set_members("W28", "CONTRACTOR28", ["MEMBER28"])
    start_pending_contractor_transfer("W28", "MEMBER28", "弟子", FEB, workshops)

    after_expiry = FEB + timedelta(hours=25)
    expired = check_and_expire_pending_contractor_transfer("W28", after_expiry, workshops)
    check("期限切れ分が返る", expired is not None and expired.candidate_user_id == "MEMBER28")
    check(
        "期限切れ後はpending_contractor_transferが削除される",
        workshops.get_pending_contractor_transfer("W28") is None,
    )


def test_check_and_expire_pending_contractor_transfer_noop_within_expiry():
    _, workshops, _ = make_stores()
    workshops.set_members("W29", "CONTRACTOR29", ["MEMBER29"])
    start_pending_contractor_transfer("W29", "MEMBER29", "弟子", FEB, workshops)

    within_expiry = FEB + timedelta(hours=1)
    result = check_and_expire_pending_contractor_transfer("W29", within_expiry, workshops)
    check("期限内はNoneを返し何もしない", result is None)
    check(
        "期限内はpending_contractor_transferが維持される",
        workshops.get_pending_contractor_transfer("W29") is not None,
    )


def test_get_contractor_transfer_expired_notice_context_returns_pending_after_expiry():
    """contractor-transfer-expired-notice-design.md 1節: 契約者本人からのメッセージで、
    かつ期限切れが検出された場合に(削除前の)PendingContractorTransferを返すことを
    検証する。
    """
    _, workshops, _ = make_stores()
    workshops.set_members("W30", "CONTRACTOR30", ["MEMBER30"])
    start_pending_contractor_transfer("W30", "MEMBER30", "弟子花子", FEB, workshops)

    after_expiry = FEB + timedelta(hours=25)
    result = get_contractor_transfer_expired_notice_context("CONTRACTOR30", "W30", after_expiry, workshops)
    check(
        "契約者本人・期限切れ後はPendingContractorTransferが返る",
        result is not None and result.candidate_member_name == "弟子花子",
    )
    check(
        "期限切れ検出によりpending_contractor_transferが削除される",
        workshops.get_pending_contractor_transfer("W30") is None,
    )


def test_get_contractor_transfer_expired_notice_context_none_for_non_contractor():
    """契約者以外からのメッセージの場合はcheck_and_expire自体を呼び出さずNoneを返す
    (2節「受信メッセージの本来の用件は今回処理しない」の前提となる契約者限定の
    スコープ)ことを検証する。期限切れ後もpending状態自体は変更されない。
    """
    _, workshops, _ = make_stores()
    workshops.set_members("W31", "CONTRACTOR31", ["MEMBER31"])
    start_pending_contractor_transfer("W31", "MEMBER31", "弟子", FEB, workshops)

    after_expiry = FEB + timedelta(hours=25)
    result = get_contractor_transfer_expired_notice_context("MEMBER31", "W31", after_expiry, workshops)
    check("契約者以外はNoneを返す", result is None)
    check(
        "契約者以外からの場合はpending_contractor_transferが削除されない",
        workshops.get_pending_contractor_transfer("W31") is not None,
    )


def test_get_contractor_transfer_expired_notice_context_none_within_expiry():
    _, workshops, _ = make_stores()
    workshops.set_members("W32", "CONTRACTOR32", ["MEMBER32"])
    start_pending_contractor_transfer("W32", "MEMBER32", "弟子", FEB, workshops)

    within_expiry = FEB + timedelta(hours=1)
    result = get_contractor_transfer_expired_notice_context("CONTRACTOR32", "W32", within_expiry, workshops)
    check("期限内はNoneを返す(is_contractor_transfer_confirmation_context側の経路)", result is None)
    check(
        "期限内はpending_contractor_transferが維持される",
        workshops.get_pending_contractor_transfer("W32") is not None,
    )


def test_select_message_context_a_wins_over_b_and_c_for_contractor():
    """message-context-selection-design.md 1節(a): 期限切れ検出・契約者譲渡再確認
    待ち・残すメンバー連絡待ちが同時に成立しうる状態を人為的に作り、契約者本人からの
    メッセージでも(a)が最優先されることを検証する(design.mdが明示的に求めるケース)。
    """
    profiles, workshops, counters = make_stores()
    profiles.link("CONTRACTOR40", "W40")
    workshops.set_plan("W40", "multi_craftsman")
    workshops.set_members("W40", "CONTRACTOR40", ["MEMBER40"])
    start_pending_contractor_transfer("W40", "MEMBER40", "弟子", FEB, workshops)
    workshops.set_pending_reduction_effective_at("W40", FEB + timedelta(hours=1))

    after_expiry = FEB + timedelta(hours=25)
    ctx = select_message_context("CONTRACTOR40", after_expiry, profiles, workshops, counters)
    check(
        "(a)期限切れ案内が最優先される",
        ctx.kind == MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_EXPIRED_NOTICE,
    )
    check(
        "expired_transferに削除前の値が入る",
        ctx.expired_transfer is not None and ctx.expired_transfer.candidate_user_id == "MEMBER40",
    )
    check(
        "(a)処理後もpending_reduction_effective_atは(c)を後回しにしただけで維持される",
        workshops.get_pending_reduction_effective_at("W40") is not None,
    )


def test_select_message_context_a_triggers_regardless_of_sender():
    """design.md 1節(a)の「送信者が契約者本人かどうかを問わない」を、契約者以外からの
    メッセージでも検証する。
    """
    profiles, workshops, counters = make_stores()
    profiles.link("MEMBER41", "W41")
    workshops.set_plan("W41", "multi_craftsman")
    workshops.set_members("W41", "CONTRACTOR41", ["MEMBER41"])
    start_pending_contractor_transfer("W41", "MEMBER41", "弟子", FEB, workshops)

    after_expiry = FEB + timedelta(hours=25)
    ctx = select_message_context("MEMBER41", after_expiry, profiles, workshops, counters)
    check(
        "契約者以外からでも(a)が発動する",
        ctx.kind == MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_EXPIRED_NOTICE,
    )


def test_select_message_context_b_confirmation_for_contractor_within_expiry():
    profiles, workshops, counters = make_stores()
    profiles.link("CONTRACTOR42", "W42")
    workshops.set_plan("W42", "multi_craftsman")
    workshops.set_members("W42", "CONTRACTOR42", ["MEMBER42"])
    start_pending_contractor_transfer("W42", "MEMBER42", "弟子", FEB, workshops)

    within_expiry = FEB + timedelta(hours=1)
    ctx = select_message_context("CONTRACTOR42", within_expiry, profiles, workshops, counters)
    check(
        "(b)契約者譲渡の再確認応答文脈が選ばれる",
        ctx.kind == MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_CONFIRMATION,
    )


def test_select_message_context_b_not_triggered_for_non_contractor_falls_through_to_d():
    """(b)は契約者本人限定であり、譲渡候補本人からのメッセージは(d)通常の生成
    リクエスト処理にフォールスルーする(contractor-transfer-non-contractor-message-
    design.mdの既存結論と整合)ことを検証する。
    """
    profiles, workshops, counters = make_stores()
    profiles.link("MEMBER43", "W43")
    workshops.set_plan("W43", "multi_craftsman")
    workshops.set_members("W43", "CONTRACTOR43", ["MEMBER43"])
    start_pending_contractor_transfer("W43", "MEMBER43", "弟子", FEB, workshops)

    within_expiry = FEB + timedelta(hours=1)
    ctx = select_message_context("MEMBER43", within_expiry, profiles, workshops, counters)
    check("契約者以外は(d)通常の生成リクエストへフォールスルーする", ctx.kind == MESSAGE_CONTEXT_GENERATION_REQUEST)
    check(
        "(d)側でusage_counterが加算されている",
        ctx.generation_result is not None and ctx.generation_result.usage.count_after_increment == 1,
    )


def test_select_message_context_c_member_retention_for_contractor_with_pending_reduction():
    profiles, workshops, counters = make_stores()
    profiles.link("CONTRACTOR44", "W44")
    workshops.set_plan("W44", "multi_craftsman")
    workshops.set_members("W44", "CONTRACTOR44", ["MEMBER44"])
    workshops.set_pending_reduction_effective_at("W44", FEB + timedelta(days=10))

    ctx = select_message_context("CONTRACTOR44", FEB, profiles, workshops, counters)
    check(
        "(c)残すメンバー連絡文脈が選ばれる",
        ctx.kind == MESSAGE_CONTEXT_MEMBER_RETENTION_NOTICE,
    )


def test_select_message_context_c_not_triggered_for_non_contractor_falls_through_to_d():
    profiles, workshops, counters = make_stores()
    profiles.link("MEMBER45", "W45")
    workshops.set_plan("W45", "multi_craftsman")
    workshops.set_members("W45", "CONTRACTOR45", ["MEMBER45"])
    workshops.set_pending_reduction_effective_at("W45", FEB + timedelta(days=10))

    ctx = select_message_context("MEMBER45", FEB, profiles, workshops, counters)
    check(
        "契約者以外は(c)を経由せず(d)通常の生成リクエストへフォールスルーする",
        ctx.kind == MESSAGE_CONTEXT_GENERATION_REQUEST,
    )
    check(
        "猶予期間未到達のため縮小は適用されない(member_reductionはNone)",
        ctx.generation_result is not None and ctx.generation_result.member_reduction is None,
    )


def test_select_message_context_d_default_generation_request():
    profiles, workshops, counters = make_stores()
    profiles.link("U46", "W46")
    workshops.set_plan("W46", "light")
    workshops.set_members("W46", "U46", [])

    ctx = select_message_context("U46", FEB, profiles, workshops, counters)
    check("いずれの一時状態も無ければ(d)が選ばれる", ctx.kind == MESSAGE_CONTEXT_GENERATION_REQUEST)
    check(
        "process_generation_requestと同じ結果がgeneration_resultに入る",
        ctx.generation_result is not None
        and ctx.generation_result.usage.plan_id == "light"
        and ctx.generation_result.usage.count_after_increment == 1,
    )


def test_select_message_context_workshop_not_linked_raises():
    profiles, workshops, counters = make_stores()
    try:
        select_message_context("UNLINKED", FEB, profiles, workshops, counters)
        check("workshop未連携はWorkshopNotLinkedErrorを送出する", False)
    except WorkshopNotLinkedError:
        check("workshop未連携はWorkshopNotLinkedErrorを送出する", True)


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
    test_process_generation_request_normal_case_no_pending_reduction()
    test_process_generation_request_applies_reduction_before_usage_check()
    test_process_generation_request_raises_for_member_removed_in_same_call()
    test_process_generation_request_workshop_not_linked_raises()
    test_resolve_contractor_transfer_target_matches_existing_member()
    test_resolve_contractor_transfer_target_ignores_contractor_self()
    test_resolve_contractor_transfer_target_returns_none_for_unknown_name()
    test_apply_contractor_transfer_updates_contractor_and_keeps_previous_as_member()
    test_apply_contractor_transfer_raises_for_non_member()
    test_start_pending_contractor_transfer_writes_expected_state()
    test_is_contractor_transfer_confirmation_context_true_for_contractor_within_expiry()
    test_is_contractor_transfer_confirmation_context_false_for_non_contractor()
    test_is_contractor_transfer_confirmation_context_false_when_no_pending()
    test_is_contractor_transfer_confirmation_context_false_after_expiry()
    test_apply_contractor_transfer_clears_pending_state()
    test_cancel_pending_contractor_transfer_clears_without_updating_contractor()
    test_check_and_expire_pending_contractor_transfer_clears_and_returns_when_expired()
    test_check_and_expire_pending_contractor_transfer_noop_within_expiry()
    test_get_contractor_transfer_expired_notice_context_returns_pending_after_expiry()
    test_get_contractor_transfer_expired_notice_context_none_for_non_contractor()
    test_get_contractor_transfer_expired_notice_context_none_within_expiry()
    test_select_message_context_a_wins_over_b_and_c_for_contractor()
    test_select_message_context_a_triggers_regardless_of_sender()
    test_select_message_context_b_confirmation_for_contractor_within_expiry()
    test_select_message_context_b_not_triggered_for_non_contractor_falls_through_to_d()
    test_select_message_context_c_member_retention_for_contractor_with_pending_reduction()
    test_select_message_context_c_not_triggered_for_non_contractor_falls_through_to_d()
    test_select_message_context_d_default_generation_request()
    test_select_message_context_workshop_not_linked_raises()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
