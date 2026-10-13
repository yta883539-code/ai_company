#!/usr/bin/env python3
"""vehicle_registry.pyの境界値テスト(フェーズ149)。pure stdlibのみで実行する
(overage_notifications.py等と同じ方針)。

実行方法: python3 prototype/test_vehicle_registry.py
"""

import sys

from overage_notifications import InMemoryVehicleCountStore
from vehicle_registry import InMemoryVehicleStore, register_vehicle_from_inspection_memo


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- 新規車両: vehicle_idが発行され、vehicleCountが1増える ---
    vehicle_store = InMemoryVehicleStore()
    count_store = InMemoryVehicleCountStore()

    result = register_vehicle_from_inspection_memo(
        vehicle_store, count_store, "op1", "2号機", plan_id="light"
    )

    results.append(_check("新規車両はis_new_vehicle=True", result.is_new_vehicle, True))
    results.append(_check(
        "新規車両はvehicle_idが発行される(空文字列ではない)",
        bool(result.vehicle_id),
        True,
    ))
    results.append(_check(
        "新規車両登録でvehicleCountが1になる",
        count_store.get_vehicle_count("op1"),
        1,
    ))

    # --- 同一表記を再送: 既存vehicle_idを再利用し、vehicleCountは増えない ---
    result2 = register_vehicle_from_inspection_memo(
        vehicle_store, count_store, "op1", "2号機", plan_id="light"
    )

    results.append(_check("同一表記の再送はis_new_vehicle=False", result2.is_new_vehicle, False))
    results.append(_check(
        "同一表記の再送は同じvehicle_idを返す(再利用)",
        result2.vehicle_id,
        result.vehicle_id,
    ))
    results.append(_check(
        "同一表記の再送ではvehicleCountが増えない",
        count_store.get_vehicle_count("op1"),
        1,
    ))
    results.append(_check(
        "同一表記の再送ではoverage_noticeが発生しない",
        result2.overage_notice,
        None,
    ))

    # --- 前後空白のみの表記差: トリム後は同一車両として扱われる(design.md 3節) ---
    result3 = register_vehicle_from_inspection_memo(
        vehicle_store, count_store, "op1", "  2号機  ", plan_id="light"
    )

    results.append(_check(
        "前後空白のみの表記差はトリム後に同一視される(is_new_vehicle=False)",
        result3.is_new_vehicle,
        False,
    ))
    results.append(_check(
        "前後空白のみの表記差は同じvehicle_idを返す",
        result3.vehicle_id,
        result.vehicle_id,
    ))

    # --- 全角/半角等の表記ゆらぎは意図的に別車両として扱う(design.md 3節、吸収しない) ---
    result4 = register_vehicle_from_inspection_memo(
        vehicle_store, count_store, "op1", "２号機", plan_id="light"
    )

    results.append(_check(
        "全角表記は別車両として扱われる(is_new_vehicle=True)",
        result4.is_new_vehicle,
        True,
    ))
    results.append(_check(
        "全角表記は元の(トリムのみ正規化の)表記とは異なるvehicle_idを持つ",
        result4.vehicle_id != result.vehicle_id,
        True,
    ))
    results.append(_check(
        "表記ゆらぎを別車両として扱った結果vehicleCountが2になる",
        count_store.get_vehicle_count("op1"),
        2,
    ))

    # --- 事業者をまたぐ同一表記は別車両として扱う((operatorInternalId, vehicleLabel)の組) ---
    result5 = register_vehicle_from_inspection_memo(
        vehicle_store, count_store, "op2", "2号機", plan_id="light"
    )

    results.append(_check(
        "事業者が異なれば同一表記でも別車両(is_new_vehicle=True)",
        result5.is_new_vehicle,
        True,
    ))
    results.append(_check(
        "事業者が異なれば同一表記でも別vehicle_idを持つ",
        result5.vehicle_id != result.vehicle_id,
        True,
    ))
    results.append(_check(
        "op1のvehicleCountはop2の登録の影響を受けない",
        count_store.get_vehicle_count("op1"),
        2,
    ))
    results.append(_check(
        "op2は新規1台のみでvehicleCountが1になる",
        count_store.get_vehicle_count("op2"),
        1,
    ))

    # --- ライトプラン(上限1台)の2台目登録でプラン超過通知が発生する ---
    # op2は既に1台(上限ちょうど)。2台目(新規ラベル)でライトプラン上限を新たに超える。
    result6 = register_vehicle_from_inspection_memo(
        vehicle_store, count_store, "op2", "3号機", plan_id="light"
    )

    results.append(_check(
        "ライトプラン上限を新たに超えた2台目はoverage_noticeが発生する",
        result6.overage_notice is not None,
        True,
    ))
    results.append(_check(
        "ライトプラン上限超過の通知文にはスタンダードプランへの案内が含まれる",
        "スタンダードプラン" in (result6.overage_notice or ""),
        True,
    ))

    ok = all(results)
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
