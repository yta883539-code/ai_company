#!/usr/bin/env python3
"""mock_llm_client.pyの境界値テスト。schema/validate_test_cases.pyのPOSITIVE_CASES
(G1〜G4・OOS1・II1〜II3)を、process_form_submission()経由で実際に流し、
(1)validate_llm_output()がいずれもエラー0件であること、(2)process_form_submission()
の応答文言(status・response_text)がフィクスチャ通りに組み立てられることの両方を
1本のフローで確認する(event-komiguai-pashaフェーズ26相当の横展開)。

実行方法: python3 prototype/test_mock_llm_client.py
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "schema"))

from form_submission_flow import process_form_submission  # noqa: E402
from mock_llm_client import MockLlmClient, validate_llm_output  # noqa: E402
from trial_management import InMemoryFleetOperatorStore  # noqa: E402
from validate_test_cases import POSITIVE_CASES  # noqa: E402


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


EXPECTED_STATUS_AND_TEXT = {
    "G1_daily": (
        "generated",
        "2026-10-03 2号機 始業前点検 山田太郎 ブレーキ○、警告灯○、異音なし 異常なし",
    ),
    "G2_monthly_no_reminder": (
        "generated",
        "2026-10-01 2号機 月次自主検査 山田太郎 油圧系統○、フォーク変形なし 異常なし",
    ),
    "G3_monthly_with_reminder": (
        "generated",
        "2025-11-05 2号機 月次自主検査 山田太郎 油圧系統○、フォーク変形なし 異常なし"
        "\n2号機の月次自主検査の次回実施期限(2025-12-05)が近づいています。",
    ),
    "G4_annual_with_company": (
        "generated",
        "2026-09-15 2号機 特定自主検査(実施:株式会社フォーク検査センター) 異常なし",
    ),
    "OOS1_unrelated_request": (
        "out_of_scope",
        "本サービスは点検記録の整形と実施期限の管理支援のみを行っております。",
    ),
    "II1_no_vehicle_id": (
        "insufficient_input",
        "車両番号が読み取れませんでした。どの車両の点検か教えてください。",
    ),
    "II2_no_type": (
        "insufficient_input",
        "点検種別(始業前点検・月次自主検査・特定自主検査のいずれか)が読み取れませんでした。",
    ),
    "II3_annual_no_company": (
        "insufficient_input",
        "特定自主検査の記録には検査業者名が必要です。検査を実施した業者名を教えてください。",
    ),
}


def main():
    results = []
    now = datetime(2026, 10, 20, 12, 0, 0)

    results.append(_check(
        "EXPECTED_STATUS_AND_TEXTがPOSITIVE_CASES全件をカバーしている",
        set(EXPECTED_STATUS_AND_TEXT.keys()),
        set(POSITIVE_CASES.keys()),
    ))

    for scenario, (expected_status, expected_text) in EXPECTED_STATUS_AND_TEXT.items():
        instance = POSITIVE_CASES[scenario]

        errors = validate_llm_output(instance)
        results.append(_check(
            f"{scenario}: validate_llm_outputはエラー0件",
            errors,
            [],
        ))

        client = MockLlmClient()
        store = InMemoryFleetOperatorStore()
        result = process_form_submission(
            f"({scenario}の入力メモ)",
            f"op_{scenario}",
            now,
            client.as_llm_generate(scenario),
            store,
        )
        results.append(_check(f"{scenario}: process_form_submission status", result["status"], expected_status))
        results.append(_check(
            f"{scenario}: process_form_submission response_text",
            result["response_text"],
            expected_text,
        ))
        results.append(_check(f"{scenario}: check_errorsは空", result["check_errors"], []))
        results.append(_check(f"{scenario}: llm_generateが1回呼ばれる", len(client.calls), 1))

    # 未知シナリオ名を指定した場合はMockLlmResponseNotFoundErrorを送出する
    client = MockLlmClient()
    try:
        client.generate("入力", scenario="存在しないシナリオ")
        results.append(_check("未知シナリオで例外が発生する", False, True))
    except KeyError:
        results.append(_check("未知シナリオで例外が発生する", True, True))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
