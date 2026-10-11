#!/usr/bin/env python3
"""trial_management.pyの境界値テスト(フェーズ118)。pure stdlibのみで実行する
(due_date_logic.py・overage_notifications.py等と同じ方針)。

実行方法: python3 prototype/test_trial_management.py
"""

import sys
from datetime import datetime, timedelta

from trial_management import (
    TRIAL_END_RETURN_TEXT_NOTICE,
    TRIAL_GENERATION_LIMIT,
    TRIAL_PERIOD_DAYS,
    InMemoryFleetOperatorStore,
    is_generation_paused,
    is_trial_period_over,
    record_generation_and_get_trial_end_notice,
    record_generation_for_trial,
    should_notify_trial_end,
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

    # --- should_notify_trial_end: トライアル中はFalse、終了時点でTrue ---
    store = InMemoryFleetOperatorStore()
    for _ in range(TRIAL_GENERATION_LIMIT - 1):
        record_generation_for_trial(store, "op7", now)
    results.append(_check(
        "should_notify_trial_end: トライアル中(終了1回手前)はFalse",
        should_notify_trial_end("op7", now, store),
        False,
    ))
    record_generation_for_trial(store, "op7", now)
    results.append(_check(
        "should_notify_trial_end: 生成回数到達時点でTrue",
        should_notify_trial_end("op7", now, store),
        True,
    ))

    # --- trialEndNotifiedAtは初回設定後は上書きされない、以降should_notify_trial_endはFalse ---
    store.set_trial_end_notified_at("op7", now)
    first_notified_at = store.get_trial_end_notified_at("op7")
    store.set_trial_end_notified_at("op7", now + timedelta(days=1))
    results.append(_check(
        "trialEndNotifiedAtは初回設定時刻のまま変わらない(2回目の設定で上書きされない)",
        store.get_trial_end_notified_at("op7"),
        first_notified_at,
    ))
    results.append(_check(
        "should_notify_trial_end: 通知済み後は(B)経路の再判定でもFalse",
        should_notify_trial_end("op7", now + timedelta(days=TRIAL_PERIOD_DAYS), store),
        False,
    ))

    # --- (B)期間到達経路でも同様にTrue/Falseが切り替わる ---
    store = InMemoryFleetOperatorStore()
    record_generation_for_trial(store, "op8", now)
    results.append(_check(
        "should_notify_trial_end: 期間条件の29日後はFalse",
        should_notify_trial_end("op8", now + timedelta(days=TRIAL_PERIOD_DAYS - 1), store),
        False,
    ))
    results.append(_check(
        "should_notify_trial_end: 期間条件のちょうど30日後でTrue",
        should_notify_trial_end("op8", now + timedelta(days=TRIAL_PERIOD_DAYS), store),
        True,
    ))

    # --- 別operatorのtrialEndNotifiedAtはNoneのまま独立している ---
    store = InMemoryFleetOperatorStore()
    results.append(_check(
        "別operatorのtrialEndNotifiedAtはNoneのまま独立している",
        store.get_trial_end_notified_at("op9"),
        None,
    ))

    # --- record_generation_and_get_trial_end_notice: (A)経路の呼び出し配線 ---
    store = InMemoryFleetOperatorStore()
    for _ in range(TRIAL_GENERATION_LIMIT - 1):
        results.append(_check(
            "record_generation_and_get_trial_end_notice: 5回目未到達の間はNone",
            record_generation_and_get_trial_end_notice(store, "op10", now),
            None,
        ))
    results.append(_check(
        "record_generation_and_get_trial_end_notice: 5回目到達時に通知文を返す",
        record_generation_and_get_trial_end_notice(store, "op10", now),
        TRIAL_END_RETURN_TEXT_NOTICE,
    ))
    results.append(_check(
        "record_generation_and_get_trial_end_notice: 通知後はtrialEndNotifiedAtが設定される",
        store.get_trial_end_notified_at("op10") is not None,
        True,
    ))
    results.append(_check(
        "record_generation_and_get_trial_end_notice: 通知済み後の6回目はもうNone(再通知しない)",
        record_generation_and_get_trial_end_notice(store, "op10", now),
        None,
    ))

    # --- record_generation_and_get_trial_end_notice: 既に(B)経路で通知済みなら(A)経路でもNone ---
    store = InMemoryFleetOperatorStore()
    record_generation_for_trial(store, "op11", now)
    store.set_trial_end_notified_at("op11", now + timedelta(days=TRIAL_PERIOD_DAYS))
    for _ in range(TRIAL_GENERATION_LIMIT - 1):
        record_generation_and_get_trial_end_notice(store, "op11", now)
    results.append(_check(
        "record_generation_and_get_trial_end_notice: (B)経路で通知済みなら生成回数到達時もNone",
        record_generation_and_get_trial_end_notice(store, "op11", now),
        None,
    ))

    # --- is_generation_paused: trialEndNotifiedAt未設定ならFalse(トライアル中・未終了) ---
    store = InMemoryFleetOperatorStore()
    results.append(_check(
        "is_generation_paused: trialEndNotifiedAt未設定ならFalse",
        is_generation_paused("op12", store),
        False,
    ))

    # --- is_generation_paused: trialEndNotifiedAt設定済み・upgradedAt未設定ならTrue ---
    store.set_trial_end_notified_at("op12", now)
    results.append(_check(
        "is_generation_paused: 通知済みかつ未アップグレードならTrue",
        is_generation_paused("op12", store),
        True,
    ))

    # --- is_generation_paused: upgradedAt設定後はFalse(有料転換済み) ---
    store.set_upgraded_at("op12", now + timedelta(days=1))
    results.append(_check(
        "is_generation_paused: upgradedAt設定後はFalse(有料転換済み)",
        is_generation_paused("op12", store),
        False,
    ))

    # --- is_generation_paused: upgradedAtのみ設定(trialEndNotifiedAt未設定)でもFalse ---
    store = InMemoryFleetOperatorStore()
    store.set_upgraded_at("op13", now)
    results.append(_check(
        "is_generation_paused: upgradedAtのみ設定(通知未送信)ならFalse",
        is_generation_paused("op13", store),
        False,
    ))

    # --- is_generation_paused: 別operatorは独立している ---
    store = InMemoryFleetOperatorStore()
    store.set_trial_end_notified_at("op14", now)
    results.append(_check(
        "is_generation_paused: 別operatorのupgradedAtはNoneのまま独立している",
        is_generation_paused("op15", store),
        False,
    ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
