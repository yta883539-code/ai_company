#!/usr/bin/env python3
"""plan_id_resolution.pyの境界値テスト(フェーズ124)。pure stdlibのみで実行する
(trial_management.py等と同じ方針)。

実行方法: python3 prototype/test_plan_id_resolution.py
"""

import sys

from plan_id_resolution import (
    KNOWN_PLAN_IDS,
    LOOKUP_KEY_TO_PLAN_ID,
    resolve_plan_id_from_subscription,
    sync_plan_id_on_subscription_event,
    write_plan_id_from_checkout_session_metadata,
)
from trial_management import InMemoryFleetOperatorStore


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def _subscription_data_object(lookup_key):
    return {"items": {"data": [{"price": {"lookup_key": lookup_key}}]}}


def main():
    results = []

    # --- KNOWN_PLAN_IDSはoverage_notifications.PLAN_VEHICLE_LIMITと同一のキー集合 ---
    results.append(_check(
        "KNOWN_PLAN_IDSはlight/standard/fleetの3件",
        KNOWN_PLAN_IDS,
        frozenset({"light", "standard", "fleet"}),
    ))

    # --- write_plan_id_from_checkout_session_metadata: 既知のplanは書き込まれる ---
    store = InMemoryFleetOperatorStore()
    results.append(_check(
        "既知のplan('standard')はTrueを返し書き込まれる",
        write_plan_id_from_checkout_session_metadata(store, "op1", {"plan": "standard"}),
        True,
    ))
    results.append(_check(
        "書き込み後のget_plan_idは'standard'",
        store.get_plan_id("op1"),
        "standard",
    ))

    # --- write_plan_id_from_checkout_session_metadata: 未知のplanは書き込まれない ---
    store = InMemoryFleetOperatorStore()
    results.append(_check(
        "未知のplan('unknown')はFalseを返す",
        write_plan_id_from_checkout_session_metadata(store, "op2", {"plan": "unknown"}),
        False,
    ))
    results.append(_check(
        "未知のplanは書き込まれずNoneのまま",
        store.get_plan_id("op2"),
        None,
    ))

    # --- write_plan_id_from_checkout_session_metadata: metadata欠落・plan欠落も安全側 ---
    store = InMemoryFleetOperatorStore()
    results.append(_check(
        "metadataが空辞書でもFalse",
        write_plan_id_from_checkout_session_metadata(store, "op3", {}),
        False,
    ))
    results.append(_check(
        "metadataがNoneでもFalse(エラーにならない)",
        write_plan_id_from_checkout_session_metadata(store, "op3", None),
        False,
    ))

    # --- resolve_plan_id_from_subscription: 既知のlookup_keyは解決できる ---
    for lookup_key, expected_plan_id in LOOKUP_KEY_TO_PLAN_ID.items():
        results.append(_check(
            f"lookup_key={lookup_key!r}は{expected_plan_id!r}に解決される",
            resolve_plan_id_from_subscription(_subscription_data_object(lookup_key)),
            expected_plan_id,
        ))

    # --- resolve_plan_id_from_subscription: 未知のlookup_key・欠落は常にNone ---
    results.append(_check(
        "未知のlookup_keyはNone",
        resolve_plan_id_from_subscription(_subscription_data_object("unknown_lookup_key")),
        None,
    ))
    results.append(_check(
        "items欠落時もNone(KeyErrorにならない)",
        resolve_plan_id_from_subscription({}),
        None,
    ))
    results.append(_check(
        "items.dataが空配列の場合もNone(IndexErrorにならない)",
        resolve_plan_id_from_subscription({"items": {"data": []}}),
        None,
    ))

    # --- sync_plan_id_on_subscription_event: 差分がある場合のみ書き込む ---
    store = InMemoryFleetOperatorStore()
    store.set_plan_id("op4", "light")
    results.append(_check(
        "既存'light'→解決値'standard'は差分ありでTrue",
        sync_plan_id_on_subscription_event(
            store, "op4", _subscription_data_object("forklift_pasha_standard")
        ),
        True,
    ))
    results.append(_check(
        "同期後のget_plan_idは'standard'",
        store.get_plan_id("op4"),
        "standard",
    ))
    results.append(_check(
        "既存と同値('standard')の再同期はFalse(差分なし、書き込み省略)",
        sync_plan_id_on_subscription_event(
            store, "op4", _subscription_data_object("forklift_pasha_standard")
        ),
        False,
    ))

    # --- sync_plan_id_on_subscription_event: 解決できない場合は既存値を維持してFalse ---
    store = InMemoryFleetOperatorStore()
    store.set_plan_id("op5", "fleet")
    results.append(_check(
        "未知のlookup_keyはFalse(書き込みなし)",
        sync_plan_id_on_subscription_event(
            store, "op5", _subscription_data_object("unknown_lookup_key")
        ),
        False,
    ))
    results.append(_check(
        "既存値'fleet'は維持される",
        store.get_plan_id("op5"),
        "fleet",
    ))

    # --- 別operatorは独立している ---
    store = InMemoryFleetOperatorStore()
    write_plan_id_from_checkout_session_metadata(store, "op6", {"plan": "light"})
    results.append(_check(
        "別operatorのget_plan_idはNoneのまま独立している",
        store.get_plan_id("op7"),
        None,
    ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
