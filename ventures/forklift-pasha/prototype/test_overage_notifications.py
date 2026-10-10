#!/usr/bin/env python3
"""overage_notifications.pyの境界値テスト(フェーズ116)。pure stdlibのみで実行する
(due_date_logic.py等と同じ方針)。

実行方法: python3 prototype/test_overage_notifications.py
"""

import sys

from overage_notifications import (
    PLAN_MONTHLY_LIMIT,
    PLAN_VEHICLE_LIMIT,
    format_fleet_overage_notice,
    format_usage_limit_notice,
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

    total = len(results)
    failed = total - sum(results)
    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
