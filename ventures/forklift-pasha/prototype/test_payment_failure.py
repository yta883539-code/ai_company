#!/usr/bin/env python3
"""payment_failure.pyの境界値テスト(フェーズ167)。pure stdlibのみで実行する
(trial_management.py等と同じ方針)。

実行方法: python3 prototype/test_payment_failure.py
"""

import sys
from datetime import datetime, timedelta, timezone

from payment_failure import (
    PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    classify_payment_recovery,
    clear_payment_failure_on_success,
    is_payment_suspended,
    mark_payment_failure_detected,
)
from trial_management import InMemoryFleetOperatorStore

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main() -> int:
    results = []

    # --- mark_payment_failure_detected() ---
    store1 = InMemoryFleetOperatorStore()
    returned = mark_payment_failure_detected(store1, "op-1", NOW)
    results.append(_check("検知時刻を書き込む", store1.get_payment_failure_detected_at("op-1"), NOW))
    results.append(_check("書き込んだ値を返す", returned, NOW))

    later = NOW + timedelta(days=1)
    mark_payment_failure_detected(store1, "op-1", later)
    results.append(_check(
        "複数回の失敗通知は最新の失敗日時で上書きする",
        store1.get_payment_failure_detected_at("op-1"),
        later,
    ))

    # --- is_payment_suspended() ---
    store2 = InMemoryFleetOperatorStore()
    store2.set_upgraded_at("op-2", NOW - timedelta(days=100))
    results.append(_check(
        "payment_failure_detected_at未設定なら制限モードではない",
        is_payment_suspended("op-2", NOW, store2),
        False,
    ))

    mark_payment_failure_detected(store2, "op-2", NOW)
    results.append(_check(
        "猶予期間中(7日未満)は制限モードではない",
        is_payment_suspended("op-2", NOW + timedelta(days=6), store2),
        False,
    ))
    results.append(_check(
        f"猶予期間終了({PAYMENT_FAILURE_GRACE_PERIOD_DAYS}日)で制限モードになる",
        is_payment_suspended("op-2", NOW + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS), store2),
        True,
    ))

    store3 = InMemoryFleetOperatorStore()
    mark_payment_failure_detected(store3, "op-3", NOW)
    results.append(_check(
        "トライアル中(upgraded_at未設定)は決済失敗が設定済みでも制限モードにならない",
        is_payment_suspended("op-3", NOW + timedelta(days=30), store3),
        False,
    ))

    store4 = InMemoryFleetOperatorStore()
    store4.set_upgraded_at("op-4", NOW - timedelta(days=100))
    store4.set_canceled_at("op-4", NOW)
    mark_payment_failure_detected(store4, "op-4", NOW)
    results.append(_check(
        "解約済み(canceled_at設定済み)は決済失敗が設定済みでも制限モードにならない",
        is_payment_suspended("op-4", NOW + timedelta(days=30), store4),
        False,
    ))

    # --- clear_payment_failure_on_success() ---
    store5 = InMemoryFleetOperatorStore()
    results.append(_check(
        "未検知状態でのクリアはFalseを返し何もしない",
        clear_payment_failure_on_success(store5, "op-5"),
        False,
    ))

    mark_payment_failure_detected(store5, "op-5", NOW)
    store5.set_payment_failure_reminder_sent_at("op-5", NOW)
    store5.set_payment_suspension_owner_notified_at("op-5", NOW)
    results.append(_check("検知済み状態のクリアはTrueを返す", clear_payment_failure_on_success(store5, "op-5"), True))
    results.append(_check(
        "クリア後はpayment_failure_detected_atがNoneになる",
        store5.get_payment_failure_detected_at("op-5"),
        None,
    ))
    results.append(_check(
        "クリア後はpayment_failure_reminder_sent_atもNoneになる(フェーズ170)",
        store5.get_payment_failure_reminder_sent_at("op-5"),
        None,
    ))
    results.append(_check(
        "クリア後はpayment_suspension_owner_notified_atもNoneになる(フェーズ170)",
        store5.get_payment_suspension_owner_notified_at("op-5"),
        None,
    ))

    # --- classify_payment_recovery() ---
    results.append(_check(
        "猶予期間中の解消はresolved_within_grace_period",
        classify_payment_recovery(NOW, NOW + timedelta(days=6)),
        "resolved_within_grace_period",
    ))
    results.append(_check(
        "猶予期間終了後の復旧はrecovered_from_suspension",
        classify_payment_recovery(NOW, NOW + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS)),
        "recovered_from_suspension",
    ))

    passed = sum(1 for r in results if r)
    print(f"\n{len(results)}件中{passed}件成功")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
