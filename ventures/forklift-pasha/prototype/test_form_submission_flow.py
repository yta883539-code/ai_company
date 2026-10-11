#!/usr/bin/env python3
"""form_submission_flow.pyの境界値テスト(フェーズ123)。pure stdlibのみで実行する
(trial_management.py等と同じ方針)。

実行方法: python3 prototype/test_form_submission_flow.py
"""

import sys
from datetime import datetime

from form_submission_flow import process_form_submission
from trial_management import (
    CANCELED_NOTICE,
    GENERATION_PAUSED_NOTICE,
    TRIAL_END_RETURN_TEXT_NOTICE,
    TRIAL_GENERATION_LIMIT,
    InMemoryFleetOperatorStore,
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def _generated_instance(body="2号機、始業前点検、ブレーキ○、異音なし", reminder_notice=None):
    return {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "inspection_record": {
            "vehicle_id": "2号機",
            "type": "daily",
            "date": "2026-10-11",
            "items": "ブレーキ○、異音なし",
            "result": "異常なし",
            "inspector_name": "山田",
            "inspector_company": None,
            "body": body,
            "reminder_notice": reminder_notice,
        },
    }


def main():
    results = []
    now = datetime(2026, 10, 11, 12, 0, 0)

    # --- 一時停止対象でない場合はllm_generateが呼ばれ、正常に生成される ---
    store = InMemoryFleetOperatorStore()
    calls = []

    def llm_generate(raw_text):
        calls.append(raw_text)
        return _generated_instance()

    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op1",
        now,
        llm_generate,
        store,
    )
    results.append(_check("通常生成: status", result["status"], "generated"))
    results.append(_check(
        "通常生成: response_textは整形済みbodyそのまま(reminder_noticeなし)",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし",
    ))
    results.append(_check("通常生成: check_errorsは空", result["check_errors"], []))
    results.append(_check("通常生成: llm_generateが1回呼ばれる", len(calls), 1))

    # --- reminder_noticeがある場合は本文末尾に改行付きで追記される ---
    store = InMemoryFleetOperatorStore()
    result = process_form_submission(
        "1号機、月次自主検査、油圧系統・荷台に異常なし、2026-10-11",
        "op2",
        now,
        lambda raw_text: _generated_instance(
            body="1号機、月次自主検査、油圧系統・荷台に異常なし",
            reminder_notice="次回の月次自主検査期限は2026-11-11です。",
        ),
        store,
    )
    results.append(_check(
        "reminder_notice追記",
        result["response_text"],
        "1号機、月次自主検査、油圧系統・荷台に異常なし\n次回の月次自主検査期限は2026-11-11です。",
    ))

    # --- out_of_scope: out_of_scope_messageがそのまま返る ---
    store = InMemoryFleetOperatorStore()
    result = process_form_submission(
        "この車両は修理すべきですか?",
        "op3",
        now,
        lambda raw_text: {
            "status": "out_of_scope",
            "out_of_scope_message": "本サービスは点検記録の整形と実施期限の管理支援のみを行っております。",
            "missing_fields_request": None,
            "inspection_record": None,
        },
        store,
    )
    results.append(_check("out_of_scope: status", result["status"], "out_of_scope"))
    results.append(_check(
        "out_of_scope: response_textはout_of_scope_message",
        result["response_text"],
        "本サービスは点検記録の整形と実施期限の管理支援のみを行っております。",
    ))

    # --- insufficient_input: missing_fields_requestがそのまま返る ---
    store = InMemoryFleetOperatorStore()
    result = process_form_submission(
        "点検しました",
        "op4",
        now,
        lambda raw_text: {
            "status": "insufficient_input",
            "out_of_scope_message": None,
            "missing_fields_request": "車両番号・点検種別・実施日をお知らせください。",
            "inspection_record": None,
        },
        store,
    )
    results.append(_check("insufficient_input: status", result["status"], "insufficient_input"))
    results.append(_check(
        "insufficient_input: response_textはmissing_fields_request",
        result["response_text"],
        "車両番号・点検種別・実施日をお知らせください。",
    ))

    # --- invalid_output: 絵文字入り出力はcheck_errorsが非空でresponse_textはNone ---
    store = InMemoryFleetOperatorStore()
    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op5",
        now,
        lambda raw_text: _generated_instance(body="2号機、始業前点検完了です😊"),
        store,
    )
    results.append(_check("invalid_output: status", result["status"], "invalid_output"))
    results.append(_check("invalid_output: response_textはNone", result["response_text"], None))
    results.append(_check(
        "invalid_output: check_errorsが非空",
        len(result["check_errors"]) > 0,
        True,
    ))

    # --- paused: トライアル終了済み・未アップグレードの場合はllm_generateを呼ばない ---
    store = InMemoryFleetOperatorStore()
    store.set_trial_start_at("op6", now)
    store.set_trial_end_notified_at("op6", now)
    paused_calls = []

    def llm_generate_should_not_be_called(raw_text):
        paused_calls.append(raw_text)
        return _generated_instance()

    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op6",
        now,
        llm_generate_should_not_be_called,
        store,
    )
    results.append(_check("paused: status", result["status"], "paused"))
    results.append(_check(
        "paused: response_textはGENERATION_PAUSED_NOTICE",
        result["response_text"],
        GENERATION_PAUSED_NOTICE,
    ))
    results.append(_check("paused: llm_generateは呼ばれない", len(paused_calls), 0))

    # --- 解約確定(canceled_at設定済み)は、有料転換済みでも最優先でブロックされる ---
    store = InMemoryFleetOperatorStore()
    store.set_upgraded_at("op6b", now)
    store.set_canceled_at("op6b", now)
    canceled_calls = []

    def llm_generate_should_not_be_called_canceled(raw_text):
        canceled_calls.append(raw_text)
        return _generated_instance()

    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op6b",
        now,
        llm_generate_should_not_be_called_canceled,
        store,
    )
    results.append(_check("canceled: status", result["status"], "canceled"))
    results.append(_check(
        "canceled: response_textはCANCELED_NOTICE",
        result["response_text"],
        CANCELED_NOTICE,
    ))
    results.append(_check("canceled: llm_generateは呼ばれない", len(canceled_calls), 0))

    # --- アップグレード済みの場合は一時停止対象にならない ---
    store = InMemoryFleetOperatorStore()
    store.set_trial_start_at("op7", now)
    store.set_trial_end_notified_at("op7", now)
    store.set_upgraded_at("op7", now)
    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op7",
        now,
        lambda raw_text: _generated_instance(),
        store,
    )
    results.append(_check("アップグレード済み: status", result["status"], "generated"))

    # --- トライアル終了条件にちょうど達した生成では末尾に通知文が追記される ---
    store = InMemoryFleetOperatorStore()
    for _ in range(TRIAL_GENERATION_LIMIT - 1):
        process_form_submission(
            "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
            "op8",
            now,
            lambda raw_text: _generated_instance(),
            store,
        )
    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op8",
        now,
        lambda raw_text: _generated_instance(),
        store,
    )
    results.append(_check(
        f"トライアル{TRIAL_GENERATION_LIMIT}回目: 通知文が末尾に追記される",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし\n" + TRIAL_END_RETURN_TEXT_NOTICE,
    ))
    # 次回(6回目)は既に一時停止対象になっているため、以降はpausedになる
    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op8",
        now,
        lambda raw_text: _generated_instance(),
        store,
    )
    results.append(_check(
        f"トライアル終了通知後の次回送信はpaused",
        result["status"],
        "paused",
    ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
