#!/usr/bin/env python3
"""trial_management.pyの境界値テスト(フェーズ118)。pure stdlibのみで実行する
(due_date_logic.py・overage_notifications.py等と同じ方針)。

実行方法: python3 prototype/test_trial_management.py
"""

import sys
from datetime import datetime, timedelta

from trial_management import (
    TRIAL_GENERATION_LIMIT,
    TRIAL_PERIOD_DAYS,
    InMemoryFleetOperatorStore,
    is_trial_period_over,
    record_generation_for_trial,
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []
    now = datetime(2026, 10, 10, 12, 0, 0)

    # --- trialStartAt未設定(初回生成前)は常にFalse ---
    store = InMemoryFleetOperatorStore()
    results.append(_check(
        "初回生成前はトライアル終了ではない",
        is_trial_period_over("op1", now, store),
        False,
    ))

    # --- (A) 生成回数到達: 5回目でTrue、4回目まではFalse ---
    store = InMemoryFleetOperatorStore()
    for i in range(1, TRIAL_GENERATION_LIMIT):
        record_generation_for_trial(store, "op2", now)
        results.append(_check(
            f"生成回数条件: {i}回目はまだトライアル終了ではない",
            is_trial_period_over("op2", now, store),
            False,
        ))
    record_generation_for_trial(store, "op2", now)
    results.append(_check(
        f"生成回数条件: {TRIAL_GENERATION_LIMIT}回目でトライアル終了",
        is_trial_period_over("op2", now, store),
        True,
    ))
    results.append(_check(
        "生成回数条件: 5回到達後も加算を続けて良い(6回目でもTrueのまま)",
        is_trial_period_over("op2", now, store),
        True,
    ))

    # --- (B) 期間到達: 29日後はFalse、30日後はTrue(生成1回のみ、回数条件は未到達) ---
    store = InMemoryFleetOperatorStore()
    record_generation_for_trial(store, "op3", now)
    results.append(_check(
        "期間条件: 初回生成の29日後はまだトライアル終了ではない",
        is_trial_period_over("op3", now + timedelta(days=TRIAL_PERIOD_DAYS - 1), store),
        False,
    ))
    results.append(_check(
        "期間条件: 初回生成のちょうど30日後でトライアル終了(境界値)",
        is_trial_period_over("op3", now + timedelta(days=TRIAL_PERIOD_DAYS), store),
        True,
    ))
    results.append(_check(
        "期間条件: 初回生成の31日後も引き続きトライアル終了",
        is_trial_period_over("op3", now + timedelta(days=TRIAL_PERIOD_DAYS + 1), store),
        True,
    ))

    # --- trialStartAtは初回生成時に1回だけ設定され、以降不変 ---
    store = InMemoryFleetOperatorStore()
    record_generation_for_trial(store, "op4", now)
    first_start = store.get_trial_start_at("op4")
    record_generation_for_trial(store, "op4", now + timedelta(days=10))
    results.append(_check(
        "trialStartAtは初回生成時刻のまま変わらない(2回目生成で上書きされない)",
        store.get_trial_start_at("op4"),
        first_start,
    ))
    results.append(_check(
        "trialGenerationCountは2回目生成で2になる",
        store.get_trial_generation_count("op4"),
        2,
    ))

    # --- 異なるoperatorは独立してカウントされる ---
    store = InMemoryFleetOperatorStore()
    record_generation_for_trial(store, "op5", now)
    results.append(_check(
        "別operatorのカウントは0のまま独立している",
        store.get_trial_generation_count("op6"),
        0,
    ))
    results.append(_check(
        "別operatorのtrialStartAtはNoneのまま独立している",
        store.get_trial_start_at("op6"),
        None,
    ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
