#!/usr/bin/env python3
"""overage_notifications.pyの境界値テスト(フェーズ116)。pure stdlibのみで実行する
(due_date_logic.py等と同じ方針)。

実行方法: python3 prototype/test_overage_notifications.py
"""

import sys

from overage_notifications import (
    PLAN_MONTHLY_LIMIT,
    PLAN_VEHICLE_LIMIT,
    InMemoryUsageCounterStore,
    InMemoryVehicleCountStore,
    determine_usage_limit_notice,
    format_fleet_overage_notice,
    format_usage_limit_notice,
    record_generation_and_get_usage_notice,
    record_vehicle_and_get_overage_notice,
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- format_usage_limit_notice: 利用率90%方式の境界値(pricing-plan.md 3プラン) ---
    # ライトプラン(25回): 90%=22.5 -> ceil 23回目で通知。
    results.append(_check(
        "usage_limit: light 22回目はまだ通知なし",
        format_usage_limit_notice(22, PLAN_MONTHLY_LIMIT["light"]),
        None,
    ))
    results.append(_check(
        "usage_limit: light 23回目(90%到達)で通知",
        format_usage_limit_notice(23, PLAN_MONTHLY_LIMIT["light"]) is not None,
        True,
    ))
    results.append(_check(
        "usage_limit: light 25回目(上限到達)でも通知文を返す(残り0回)",
        "残り0回" in format_usage_limit_notice(25, PLAN_MONTHLY_LIMIT["light"]),
        True,
    ))
    results.append(_check(
        "usage_limit: light 26回目(超過後)でも通知文を返す",
        format_usage_limit_notice(26, PLAN_MONTHLY_LIMIT["light"]) is not None,
        True,
    ))

    # スタンダードプラン(70回): 90%=63 -> ちょうど63回目で通知。
    results.append(_check(
        "usage_limit: standard 62回目はまだ通知なし",
        format_usage_limit_notice(62, PLAN_MONTHLY_LIMIT["standard"]),
        None,
    ))
    results.append(_check(
        "usage_limit: standard 63回目(90%到達、ちょうど整数)で通知",
        format_usage_limit_notice(63, PLAN_MONTHLY_LIMIT["standard"]) is not None,
        True,
    ))

    # 複数台プラン(220回): 90%=198 -> ちょうど198回目で通知。
    results.append(_check(
        "usage_limit: fleet 197回目はまだ通知なし",
        format_usage_limit_notice(197, PLAN_MONTHLY_LIMIT["fleet"]),
        None,
    ))
    results.append(_check(
        "usage_limit: fleet 198回目(90%到達)で通知",
        format_usage_limit_notice(198, PLAN_MONTHLY_LIMIT["fleet"]) is not None,
        True,
    ))

    # 異常値。
    try:
        format_usage_limit_notice(1, 0)
        results.append(_check(
            "usage_limit: monthly_limit<=0でValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "usage_limit: monthly_limit<=0でValueError(伝播)", True, True,
        ))

    try:
        format_usage_limit_notice(-1, 25)
        results.append(_check(
            "usage_limit: count_after_increment<0でValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "usage_limit: count_after_increment<0でValueError(伝播)", True, True,
        ))

    # --- format_fleet_overage_notice: 台数超過の新規発生判定(設計文書3節) ---
    # ライトプラン(1台まで): 1台->2台で新たに超過、通知あり。
    notice = format_fleet_overage_notice(1, 2, "light")
    results.append(_check(
        "fleet_overage: light 1台->2台で新たに超過、スタンダードプランへの案内を含む",
        notice is not None and "スタンダードプラン" in notice,
        True,
    ))
    # 既に超過済み(2台->3台)では再通知しない。
    results.append(_check(
        "fleet_overage: light 2台->3台(既に超過済み)は再通知しない",
        format_fleet_overage_notice(2, 3, "light"),
        None,
    ))
    # 上限台数以内の増加(0台->1台、light上限1台)では通知しない。
    results.append(_check(
        "fleet_overage: light 0台->1台(上限内)は通知しない",
        format_fleet_overage_notice(0, 1, "light"),
        None,
    ))

    # スタンダードプラン(3台まで): 3台->4台で新たに超過、複数台プランへの案内。
    notice = format_fleet_overage_notice(3, 4, "standard")
    results.append(_check(
        "fleet_overage: standard 3台->4台で新たに超過、複数台プランへの案内を含む",
        notice is not None and "複数台プラン" in notice,
        True,
    ))

    # 複数台プラン(10台まで、最上位): 10台->11台で新たに超過、個別相談案内。
    notice = format_fleet_overage_notice(10, 11, "fleet")
    results.append(_check(
        "fleet_overage: fleet 10台->11台(最上位プラン超過)は個別相談案内",
        notice is not None and "個別にご相談ください" in notice,
        True,
    ))
    # 複数台プランで既に超過済みからさらに増える場合は再通知しない。
    results.append(_check(
        "fleet_overage: fleet 11台->12台(既に超過済み)は再通知しない",
        format_fleet_overage_notice(11, 12, "fleet"),
        None,
    ))
    # 1登録で複数台まとめて超過する境界(1台->3台、light上限1台)でも判定式どおり発火する。
    results.append(_check(
        "fleet_overage: light 1台->3台(一度に複数台超過)でも発火する",
        format_fleet_overage_notice(1, 3, "light") is not None,
        True,
    ))

    # 異常値。
    try:
        format_fleet_overage_notice(1, 2, "unknown")
        results.append(_check(
            "fleet_overage: 未知のplan_idでValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "fleet_overage: 未知のplan_idでValueError(伝播)", True, True,
        ))

    try:
        format_fleet_overage_notice(3, 2, "light")
        results.append(_check(
            "fleet_overage: vehicle_count_after<beforeでValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "fleet_overage: vehicle_count_after<beforeでValueError(伝播)", True, True,
        ))

    # PLAN_VEHICLE_LIMIT・PLAN_MONTHLY_LIMITがpricing-plan.mdの値と一致することの確認。
    results.append(_check(
        "PLAN_MONTHLY_LIMIT: pricing-plan.mdの3プランの値と一致",
        PLAN_MONTHLY_LIMIT,
        {"light": 25, "standard": 70, "fleet": 220},
    ))
    results.append(_check(
        "PLAN_VEHICLE_LIMIT: pricing-plan.mdの3プランの値と一致",
        PLAN_VEHICLE_LIMIT,
        {"light": 1, "standard": 3, "fleet": 10},
    ))

    # --- determine_usage_limit_notice: 「1回のみ通知」の前後比較判定(フェーズ117) ---
    # ライトプラン(25回、閾値23回): 21回->22回はまだ閾値未到達。
    results.append(_check(
        "determine_usage_limit: light 21->22回(閾値23回未到達)は通知なし",
        determine_usage_limit_notice(21, 22, PLAN_MONTHLY_LIMIT["light"]),
        None,
    ))
    # 22回->23回で新たに閾値を跨ぐ。
    results.append(_check(
        "determine_usage_limit: light 22->23回(新たに閾値到達)で通知",
        determine_usage_limit_notice(22, 23, PLAN_MONTHLY_LIMIT["light"]) is not None,
        True,
    ))
    # 既に23回以上だった場合(23->24回)は再通知しない。
    results.append(_check(
        "determine_usage_limit: light 23->24回(既に閾値到達済み)は再通知しない",
        determine_usage_limit_notice(23, 24, PLAN_MONTHLY_LIMIT["light"]),
        None,
    ))
    # 1回で複数回分まとめて加算され閾値をまたぐ場合でも発火する。
    results.append(_check(
        "determine_usage_limit: light 20->23回(一度に閾値を跨ぐ)でも発火する",
        determine_usage_limit_notice(20, 23, PLAN_MONTHLY_LIMIT["light"]) is not None,
        True,
    ))
    try:
        determine_usage_limit_notice(5, 4, PLAN_MONTHLY_LIMIT["light"])
        results.append(_check(
            "determine_usage_limit: before>afterでValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "determine_usage_limit: before>afterでValueError(伝播)", True, True,
        ))

    # --- InMemoryUsageCounterStore + record_generation_and_get_usage_notice ---
    usage_store = InMemoryUsageCounterStore()
    notices = [
        record_generation_and_get_usage_notice(usage_store, "user-1", "2026-10", "light")
        for _ in range(25)
    ]
    non_none = [n for n in notices if n is not None]
    results.append(_check(
        "record_generation: lightプランで25回生成しても通知は23回目の1回のみ",
        len(non_none),
        1,
    ))
    results.append(_check(
        "record_generation: 23回目の通知文であることを確認",
        notices[22] is not None and notices[22] == non_none[0],
        True,
    ))
    results.append(_check(
        "record_generation: increment後のusage_storeのカウントは25",
        usage_store.get_count("user-1", "2026-10"),
        25,
    ))
    # 別ユーザー・別年月は独立してカウントされる。
    other_notice = record_generation_and_get_usage_notice(usage_store, "user-2", "2026-10", "light")
    results.append(_check(
        "record_generation: 別ユーザーは1回目(閾値未到達)で通知なし",
        other_notice,
        None,
    ))
    try:
        record_generation_and_get_usage_notice(usage_store, "user-1", "2026-10", "unknown")
        results.append(_check(
            "record_generation: 未知のplan_idでValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "record_generation: 未知のplan_idでValueError(伝播)", True, True,
        ))

    # --- InMemoryVehicleCountStore + record_vehicle_and_get_overage_notice ---
    vehicle_store = InMemoryVehicleCountStore()
    vehicle_notices = [
        record_vehicle_and_get_overage_notice(vehicle_store, "user-1", "light")
        for _ in range(3)
    ]
    results.append(_check(
        "record_vehicle: lightプラン(1台まで)で3回登録すると2回目のみ通知",
        [n is not None for n in vehicle_notices],
        [False, True, False],
    ))
    results.append(_check(
        "record_vehicle: increment後のvehicle_storeの台数は3",
        vehicle_store.get_vehicle_count("user-1"),
        3,
    ))
    try:
        record_vehicle_and_get_overage_notice(vehicle_store, "user-1", "light", delta=0)
        results.append(_check(
            "record_vehicle: delta<=0でValueError(伝播)",
            "ValueErrorが発生しなかった", "ValueErrorが発生する",
        ))
    except ValueError:
        results.append(_check(
            "record_vehicle: delta<=0でValueError(伝播)", True, True,
        ))

    total = len(results)
    failed = total - sum(results)
    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
