#!/usr/bin/env python3
"""form_submission_flow.pyの境界値テスト(フェーズ123)。pure stdlibのみで実行する
(trial_management.py等と同じ方針)。

実行方法: python3 prototype/test_form_submission_flow.py
"""

import sys
from datetime import datetime

from access_token_store import InMemoryAccessTokenStore
from daily_form_render import today_jst_date_str
from form_submission_flow import (
    build_daily_raw_text_from_form,
    get_form_submission_runtime_dependencies,
    main as form_submission_main,
    process_form_submission,
    receive_form_submission,
)
from overage_notifications import InMemoryUsageCounterStore, InMemoryVehicleCountStore
from trial_management import (
    CANCELED_NOTICE,
    FIRST_DAILY_GENERATION_NOTICE_MESSAGE,
    GENERATION_PAUSED_NOTICE,
    TRIAL_END_RETURN_TEXT_NOTICE,
    TRIAL_GENERATION_LIMIT,
    InMemoryFleetOperatorStore,
    format_minutes_saved_line,
)
from vehicle_registry import InMemoryVehicleStore


class _StubRequest:
    """main(request)のテスト用、functions_frameworkが渡すFlask Requestのうち
    `request.args.get()`・`request.form.get()`インターフェースのみを模した最小スタブ
    (test_checkout_session.py/test_access_url_reissue_handler.py `_StubRequest`と同系)。"""

    def __init__(self, args: dict, form: "dict | None" = None, method: str = "POST"):
        self.args = args
        self.form = form or {}
        self.method = method


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def _generated_instance(
    body="2号機、始業前点検、ブレーキ○、異音なし",
    reminder_notice=None,
    type="daily",
    vehicle_id="2号機",
    inspector_name="山田",
    inspector_company=None,
):
    return {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "inspection_record": {
            "vehicle_id": vehicle_id,
            "type": type,
            "date": "2026-10-11",
            "items": "ブレーキ○、異音なし",
            "result": "異常なし",
            "inspector_name": inspector_name,
            "inspector_company": inspector_company,
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
        "通常生成: response_textは整形済みbody+初回daily確認案内(reminder_noticeなし)",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし\n" + FIRST_DAILY_GENERATION_NOTICE_MESSAGE,
    ))
    results.append(_check("通常生成: check_errorsは空", result["check_errors"], []))
    results.append(_check("通常生成: llm_generateが1回呼ばれる", len(calls), 1))

    # --- 同一事業者の2回目以降のdaily送信では確認案内は付記されない ---
    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op1",
        now,
        llm_generate,
        store,
    )
    results.append(_check(
        "2回目のdaily生成: 確認案内は付記されない",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし",
    ))

    # --- reminder_noticeがある場合は本文末尾に改行付きで追記される ---
    store = InMemoryFleetOperatorStore()
    result = process_form_submission(
        "1号機、月次自主検査、油圧系統・荷台に異常なし、2026-10-11",
        "op2",
        now,
        lambda raw_text: _generated_instance(
            body="1号機、月次自主検査、油圧系統・荷台に異常なし",
            reminder_notice="次回の月次自主検査期限は2026-11-11です。",
            type="monthly",
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
        f"トライアル{TRIAL_GENERATION_LIMIT}回目: 通知文(浮いた作業時間の目安を含む)が末尾に追記される",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし\n" + TRIAL_END_RETURN_TEXT_NOTICE
        + "\n" + format_minutes_saved_line(TRIAL_GENERATION_LIMIT),
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

    # --- vehicle_store/vehicle_count_store未指定(既存呼び出し元)では車両登録は一切
    # 行われない(後方互換、フェーズ231で追加したパラメータは省略可能) ---
    store = InMemoryFleetOperatorStore()
    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op9",
        now,
        lambda raw_text: _generated_instance(),
        store,
    )
    results.append(_check(
        "vehicle_store未指定: response_textは車両登録なしで本文+初回確認案内のみ",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし\n" + FIRST_DAILY_GENERATION_NOTICE_MESSAGE,
    ))

    # --- plan_id未設定(トライアル中)の事業者: 新規車両は登録されるがoverage_noticeは
    # 発生しない(vehicle_registry.pyのplan_id=None時の方針どおり、フェーズ231) ---
    store = InMemoryFleetOperatorStore()
    vehicle_store = InMemoryVehicleStore()
    vehicle_count_store = InMemoryVehicleCountStore()
    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op10",
        now,
        lambda raw_text: _generated_instance(),
        store,
        vehicle_store,
        vehicle_count_store,
    )
    results.append(_check(
        "plan_id未設定: response_textにoverage_noticeは追記されない",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし\n" + FIRST_DAILY_GENERATION_NOTICE_MESSAGE,
    ))
    results.append(_check(
        "plan_id未設定でもvehicleCountは加算される",
        vehicle_count_store.get_vehicle_count("op10"),
        1,
    ))

    # --- ライトプラン(上限1台)契約済みの事業者: 2台目の新規車両登録でプラン超過通知が
    # first_daily_noticeの直後・trial_end_noticeより先に追記される ---
    store = InMemoryFleetOperatorStore()
    store.set_upgraded_at("op11", now)
    store.set_plan_id("op11", "light")
    vehicle_store = InMemoryVehicleStore()
    vehicle_count_store = InMemoryVehicleCountStore()

    result = process_form_submission(
        "2号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op11",
        now,
        lambda raw_text: _generated_instance(),
        store,
        vehicle_store,
        vehicle_count_store,
    )
    results.append(_check(
        "ライトプラン1台目(上限ちょうど): overage_noticeは発生しない",
        result["response_text"],
        "2号機、始業前点検、ブレーキ○、異音なし\n" + FIRST_DAILY_GENERATION_NOTICE_MESSAGE,
    ))

    result = process_form_submission(
        "3号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op11",
        now,
        lambda raw_text: _generated_instance(
            body="3号機、始業前点検、ブレーキ○、異音なし", vehicle_id="3号機"
        ),
        store,
        vehicle_store,
        vehicle_count_store,
    )
    results.append(_check(
        "ライトプラン2台目(上限超過)でoverage_noticeが追記される(確認案内は初回のみのため未付記)",
        "スタンダードプラン" in result["response_text"],
        True,
    ))
    results.append(_check(
        "ライトプラン2台目: vehicleCountは2になる",
        vehicle_count_store.get_vehicle_count("op11"),
        2,
    ))

    # --- フェーズ232: 車両登録(register_vehicle_from_inspection_memo呼び出し)はtype
    # (daily/monthly/annual)で分岐しない1か所の処理であることを明示的に固定する(README
    # フェーズ230/231の次回候補(2)「monthly/annual側の配線は未着手」という記述が、実際には
    # process_form_submission側に区分分岐が存在しないため当てはまらないことの確認)。
    # first_daily_noticeはtype="daily"以外では付記されないため、response_textは本文のみ
    # になるが、vehicleCountはdailyと同様に加算されることを検証する。
    store = InMemoryFleetOperatorStore()
    vehicle_store = InMemoryVehicleStore()
    vehicle_count_store = InMemoryVehicleCountStore()
    result = process_form_submission(
        "4号機、月次点検、ブレーキ○、異音なし、2026-10-11",
        "op12",
        now,
        lambda raw_text: _generated_instance(
            body="4号機、月次点検、ブレーキ○、異音なし",
            type="monthly",
            vehicle_id="4号機",
        ),
        store,
        vehicle_store,
        vehicle_count_store,
    )
    results.append(_check(
        "type=monthly: response_textは本文のみ(first_daily_noticeは付記されない)",
        result["response_text"],
        "4号機、月次点検、ブレーキ○、異音なし",
    ))
    results.append(_check(
        "type=monthly でもvehicleCountはdailyと同様に加算される",
        vehicle_count_store.get_vehicle_count("op12"),
        1,
    ))

    store = InMemoryFleetOperatorStore()
    vehicle_store = InMemoryVehicleStore()
    vehicle_count_store = InMemoryVehicleCountStore()
    result = process_form_submission(
        "5号機、年次点検、ブレーキ○、異音なし、2026-10-11",
        "op13",
        now,
        lambda raw_text: _generated_instance(
            body="5号機、年次点検、ブレーキ○、異音なし",
            type="annual",
            vehicle_id="5号機",
            inspector_name=None,
            inspector_company="株式会社フォーク検査センター",
        ),
        store,
        vehicle_store,
        vehicle_count_store,
    )
    results.append(_check(
        "type=annual: response_textは本文のみ(first_daily_noticeは付記されない)",
        result["response_text"],
        "5号機、年次点検、ブレーキ○、異音なし",
    ))
    results.append(_check(
        "type=annual でもvehicleCountはdailyと同様に加算される",
        vehicle_count_store.get_vehicle_count("op13"),
        1,
    ))

    # --- フェーズ255: usage_counter_store配線。plan_id未設定(トライアル中)では使用量
    # 通知は付記されないが、vehicleCountと同じ考え方でカウント自体は加算される ---
    store = InMemoryFleetOperatorStore()
    usage_counter_store = InMemoryUsageCounterStore()
    result = process_form_submission(
        "6号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op14",
        now,
        lambda raw_text: _generated_instance(
            body="6号機、始業前点検、ブレーキ○、異音なし", vehicle_id="6号機"
        ),
        store,
        usage_counter_store=usage_counter_store,
    )
    results.append(_check(
        "usage_counter_store指定・plan_id未設定: response_textに使用量通知は追記されない",
        result["response_text"],
        "6号機、始業前点検、ブレーキ○、異音なし\n" + FIRST_DAILY_GENERATION_NOTICE_MESSAGE,
    ))
    results.append(_check(
        "usage_counter_store指定・plan_id未設定でもカウントは加算される",
        usage_counter_store.get_count("op14", "2026-10"),
        1,
    ))

    # --- ライトプラン(上限25回)契約済みの事業者が90%閾値(23回目)に達した生成完了
    # 時点で1回だけ使用量通知が追記される。24回目は1回のみ通知のため再度は付記されない ---
    store = InMemoryFleetOperatorStore()
    store.set_upgraded_at("op15", now)
    store.set_plan_id("op15", "light")
    usage_counter_store = InMemoryUsageCounterStore()
    llm_generate_op15 = lambda raw_text: _generated_instance(
        body="7号機、始業前点検、ブレーキ○、異音なし", vehicle_id="7号機"
    )
    for _ in range(22):
        process_form_submission(
            "7号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
            "op15",
            now,
            llm_generate_op15,
            store,
            usage_counter_store=usage_counter_store,
        )
    result = process_form_submission(
        "7号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op15",
        now,
        llm_generate_op15,
        store,
        usage_counter_store=usage_counter_store,
    )
    results.append(_check(
        "ライトプラン23回目(90%閾値)で使用量通知が追記される",
        "上限25回のうち23回" in result["response_text"],
        True,
    ))
    result_next = process_form_submission(
        "7号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op15",
        now,
        llm_generate_op15,
        store,
        usage_counter_store=usage_counter_store,
    )
    results.append(_check(
        "ライトプラン24回目は1回のみ通知のため使用量通知が再度付記されない",
        "上限25回のうち" in result_next["response_text"],
        False,
    ))

    # --- 台数超過通知(3節)と使用量通知(2節)が同一リクエストで両方発生した場合、
    # design.md 4節の表示順どおり台数超過通知が先・使用量通知が後になる ---
    store = InMemoryFleetOperatorStore()
    store.set_upgraded_at("op16", now)
    store.set_plan_id("op16", "light")
    vehicle_store = InMemoryVehicleStore()
    vehicle_count_store = InMemoryVehicleCountStore()
    usage_counter_store = InMemoryUsageCounterStore()
    llm_generate_op16_vehicle8 = lambda raw_text: _generated_instance(
        body="8号機、始業前点検、ブレーキ○、異音なし", vehicle_id="8号機"
    )
    for _ in range(22):
        process_form_submission(
            "8号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
            "op16",
            now,
            llm_generate_op16_vehicle8,
            store,
            vehicle_store,
            vehicle_count_store,
            usage_counter_store,
        )
    # ここまで22回生成済み(同一車両「8号機」のためvehicleCountは1のまま)。23回目に
    # 新規車両「9号機」を登録し、台数超過通知・使用量通知(23回目でちょうど閾値)の
    # 両方を同時に発生させる。
    result = process_form_submission(
        "9号機、始業前点検、ブレーキ○、異音なし、2026-10-11",
        "op16",
        now,
        lambda raw_text: _generated_instance(
            body="9号機、始業前点検、ブレーキ○、異音なし", vehicle_id="9号機"
        ),
        store,
        vehicle_store,
        vehicle_count_store,
        usage_counter_store,
    )
    vehicle_notice_pos = result["response_text"].find("スタンダードプラン")
    usage_notice_pos = result["response_text"].find("上限25回のうち")
    results.append(_check(
        "台数超過通知・使用量通知が両方とも追記される",
        vehicle_notice_pos >= 0 and usage_notice_pos >= 0,
        True,
    ))
    results.append(_check(
        "表示順はdesign.md 4節どおり台数超過通知(3節)が先・使用量通知(2節)が後",
        vehicle_notice_pos < usage_notice_pos
        if (vehicle_notice_pos >= 0 and usage_notice_pos >= 0)
        else False,
        True,
    ))

    # --- receive_form_submission(): access_token欠落・未知・raw_text欠落・llm未接続 ---
    access_token_store = InMemoryAccessTokenStore()
    access_token_store.set_access_token("op-reg", "token-reg")
    operator_store_http = InMemoryFleetOperatorStore()

    results.append(_check(
        "receive_form_submission(): access_token欠落は400",
        receive_form_submission(
            None, "5号機、異常なし", now,
            access_token_store=access_token_store,
            operator_store=operator_store_http,
            llm_generate=lambda raw_text: _generated_instance(),
        ).status_code,
        400,
    ))
    results.append(_check(
        "receive_form_submission(): 未知のaccess_tokenは404",
        receive_form_submission(
            "unknown-token", "5号機、異常なし", now,
            access_token_store=access_token_store,
            operator_store=operator_store_http,
            llm_generate=lambda raw_text: _generated_instance(),
        ).status_code,
        404,
    ))
    results.append(_check(
        "receive_form_submission(): raw_text欠落(空文字列)は400",
        receive_form_submission(
            "token-reg", "   ", now,
            access_token_store=access_token_store,
            operator_store=operator_store_http,
            llm_generate=lambda raw_text: _generated_instance(),
        ).status_code,
        400,
    ))
    results.append(_check(
        "receive_form_submission(): llm_generate=None(実LLM未接続)は503"
        "(process_form_submission()自体は呼ばれない安全側フォールバック)",
        receive_form_submission(
            "token-reg", "5号機、異常なし", now,
            access_token_store=access_token_store,
            operator_store=operator_store_http,
            llm_generate=None,
        ).status_code,
        503,
    ))

    normal_result = receive_form_submission(
        "token-reg", "5号機、異常なし", now,
        access_token_store=access_token_store,
        operator_store=operator_store_http,
        llm_generate=lambda raw_text: _generated_instance(vehicle_id=None),
    )
    results.append(_check(
        "receive_form_submission(): 正常系(status=generated)は200",
        normal_result.status_code,
        200,
    ))
    results.append(_check(
        "receive_form_submission(): 正常系のresponse_textはprocess_form_submission()と同一"
        "(本人特定の鍵がaccess_tokenからoperator_idへ解決されただけで内容は同一、"
        "op-regは初回生成のためfirst_daily_noticeが付記される)",
        normal_result.response_text,
        f"2号機、始業前点検、ブレーキ○、異音なし\n{FIRST_DAILY_GENERATION_NOTICE_MESSAGE}",
    ))

    # --- main(): Cloud Functionsエントリポイント自体の回帰確認 ---
    body_missing, status_missing = form_submission_main(_StubRequest({}))
    results.append(_check(
        "main(): access_token未指定(request.args空)は400",
        (body_missing, status_missing),
        ("missing_access_token", 400),
    ))

    # get_form_submission_runtime_dependencies()はmain()呼び出しごとに新規の空
    # InMemoryストアを生成するため(checkout_session.main()と同じ既知の限界)、
    # runtime_dependencies省略時は有効そうなaccess_tokenを渡しても本プロセス内では
    # 常に未知のトークンとして404になる(llm_generate未接続による503に到達する前に
    # access_token解決で止まることの確認)。
    body_unconnected, status_unconnected = form_submission_main(
        _StubRequest({"access_token": "token-reg"}, {"raw_text": "5号機、異常なし"})
    )
    results.append(_check(
        "main(): runtime_dependencies省略時は有効そうなaccess_tokenを渡しても404"
        "(本プロセス内で状態非保持のため)",
        (body_unconnected, status_unconnected),
        ("unknown_access_token", 404),
    ))

    injected_access_token_store = InMemoryAccessTokenStore()
    injected_access_token_store.set_access_token("op-injected", "token-injected")
    injected_dependencies = {
        "access_token_store": injected_access_token_store,
        "operator_store": InMemoryFleetOperatorStore(),
        "vehicle_store": InMemoryVehicleStore(),
        "vehicle_count_store": InMemoryVehicleCountStore(),
        "llm_generate": lambda raw_text: _generated_instance(vehicle_id=None),
    }
    body_injected, status_injected = form_submission_main(
        _StubRequest(
            {"access_token": "token-injected"}, {"raw_text": "2号機、異常なし"}
        ),
        runtime_dependencies=injected_dependencies,
    )
    results.append(_check(
        "main(): runtime_dependencies注入時はllm_generate接続済みのため200に到達できる",
        status_injected,
        200,
    ))
    results.append(_check(
        "main(): runtime_dependencies注入時のレスポンス本文はresponse_textそのもの"
        "(op-injectedは初回生成のためfirst_daily_noticeが付記される)",
        body_injected,
        f"2号機、始業前点検、ブレーキ○、異音なし\n{FIRST_DAILY_GENERATION_NOTICE_MESSAGE}",
    ))
    results.append(_check(
        "main(): runtime_dependencies注入時でも未知のaccess_tokenは引き続き404",
        form_submission_main(
            _StubRequest(
                {"access_token": "unknown-token"}, {"raw_text": "2号機、異常なし"}
            ),
            runtime_dependencies=injected_dependencies,
        )[1],
        404,
    ))

    # --- フェーズ258: build_daily_raw_text_from_form() ---
    # 「異常あり」で項目を1件申告した場合、assemble_daily_raw_text()と同じ組み立て
    # ロジックが実際のdaily.htmlフィールド名(checked_items複数値・item_note_<slug>)
    # から正しく動作することを確認する。
    daily_form_ng = {
        "vehicle": "2号車",
        "mode": "ng",
        "checked_items": ["ブレーキ", "異音"],
        "item_note_brake": "効きが甘い",
        "item_note_noise_smell": "",
    }
    results.append(_check(
        "build_daily_raw_text_from_form(): modeがngの場合、チェック項目のみnote付きで組み立てられる",
        build_daily_raw_text_from_form(daily_form_ng, date="2026-11-22", inspector_name="鈴木"),
        "点検種別: 日次点検(作業開始前点検)\n車両: 2号車\n点検者: 鈴木\n実施日: 2026-11-22\n"
        "点検結果: 異常あり\n点検項目: ブレーキ:効きが甘い、異音",
    ))

    # --- 車両を「その他(新規登録)」で選択した場合、vehicle_new_labelの値が使われる ---
    daily_form_new_vehicle = {
        "vehicle": "__new__",
        "vehicle_new_label": "4号車",
        "mode": "ok",
        "checked_items": ["ブレーキ", "警告灯", "異音", "油圧", "タイヤ", "フォーク"],
    }
    results.append(_check(
        "build_daily_raw_text_from_form(): vehicle=__new__の場合はvehicle_new_labelを使う",
        build_daily_raw_text_from_form(
            daily_form_new_vehicle, date="2026-11-22", inspector_name="佐藤"
        ),
        "点検種別: 日次点検(作業開始前点検)\n車両: 4号車\n点検者: 佐藤\n実施日: 2026-11-22\n"
        "点検結果: 異常なし\n点検項目: ブレーキ、警告灯、異音、油圧、タイヤ、フォーク",
    ))

    # --- modeが未送信・不正値の場合はValueErrorが伝播する(main()側で400に変換される契約) ---
    try:
        build_daily_raw_text_from_form({"vehicle": "1号車"}, date="2026-11-22", inspector_name="")
        results.append(_check("build_daily_raw_text_from_form(): mode未送信はValueError", False, True))
    except ValueError:
        results.append(_check("build_daily_raw_text_from_form(): mode未送信はValueError", True, True))

    # --- main(): type=dailyのアクセスURLで構造化フィールドが送信された場合、
    # receive_form_submission()までraw_textが正しく組み立てられて到達する ---
    daily_access_token_store = InMemoryAccessTokenStore()
    daily_access_token_store.set_access_token("op-daily", "token-daily")
    daily_injected_dependencies = {
        "access_token_store": daily_access_token_store,
        "operator_store": InMemoryFleetOperatorStore(),
        "vehicle_store": InMemoryVehicleStore(),
        "vehicle_count_store": InMemoryVehicleCountStore(),
        "llm_generate": lambda raw_text: _generated_instance(body=raw_text, vehicle_id=None),
    }
    body_daily, status_daily = form_submission_main(
        _StubRequest(
            {"access_token": "token-daily", "type": "daily"},
            {
                "vehicle": "1号車",
                "mode": "ok",
                "checked_items": ["ブレーキ"],
                "inspector_name": "田中",
                "date": "2026-11-22",
            },
        ),
        runtime_dependencies=daily_injected_dependencies,
    )
    results.append(_check(
        "main(): type=dailyでは構造化フィールドから組み立てたraw_textがそのまま"
        "process_form_submission()経由でresponse_textに反映される(本文はllm_generateが"
        "そのまま返す設定のため)",
        body_daily,
        "点検種別: 日次点検(作業開始前点検)\n車両: 1号車\n点検者: 田中\n実施日: 2026-11-22\n"
        "点検結果: 異常なし\n点検項目: ブレーキ\n" + FIRST_DAILY_GENERATION_NOTICE_MESSAGE,
    ))
    results.append(_check("main(): type=dailyの正常系は200", status_daily, 200))
    results.append(_check(
        "main(): type=dailyの正常系(200)後はinspector-name-date-prefill-design.md"
        "(フェーズ261)4節(2)の配線によりset_last_inspector_name()が呼ばれる"
        "(フェーズ262)",
        daily_injected_dependencies["operator_store"].get_last_inspector_name("op-daily"),
        "田中",
    ))

    # --- main(): type=dailyでもinspector_nameが空文字列の場合はキャッシュを空上書き
    # しない(design.md 3節「直前に送信した人の名前」という意味論上、空文字列は
    # 「名前」ではないため対象外、フェーズ262) ---
    body_daily_blank_inspector, status_daily_blank_inspector = form_submission_main(
        _StubRequest(
            {"access_token": "token-daily", "type": "daily"},
            {
                "vehicle": "1号車",
                "mode": "ok",
                "checked_items": ["ブレーキ"],
                "inspector_name": "",
                "date": "2026-11-22",
            },
        ),
        runtime_dependencies=daily_injected_dependencies,
    )
    results.append(_check(
        "main(): type=dailyでinspector_name空文字列でも正常系自体は200",
        status_daily_blank_inspector,
        200,
    ))
    results.append(_check(
        "main(): type=dailyでinspector_name空文字列の送信後もlast_inspector_nameは"
        "直前の値(「田中」)のまま変化しない",
        daily_injected_dependencies["operator_store"].get_last_inspector_name("op-daily"),
        "田中",
    ))

    # --- main(): type=dailyでmode未送信・不正の場合は400(process_form_submission()自体は
    # 呼ばれず、llm_generateも呼ばれない) ---
    body_daily_invalid, status_daily_invalid = form_submission_main(
        _StubRequest(
            {"access_token": "token-daily", "type": "daily"},
            {"vehicle": "1号車"},
        ),
        runtime_dependencies=daily_injected_dependencies,
    )
    results.append(_check(
        "main(): type=dailyでmode未送信は400",
        (body_daily_invalid, status_daily_invalid),
        ("invalid_daily_mode", 400),
    ))

    # --- main(): GET(type=daily)でdaily.html/daily-empty.htmlを動的レンダリングして返す
    # (inspector-name-date-prefill-design.md フェーズ261、4節(3)の実装、フェーズ263) ---
    body_get_missing, status_get_missing = form_submission_main(
        _StubRequest({"type": "daily"}, method="GET")
    )
    results.append(_check(
        "main(): GET・type=dailyでaccess_token未指定は400",
        (body_get_missing, status_get_missing),
        ("missing_access_token", 400),
    ))

    body_get_unknown, status_get_unknown = form_submission_main(
        _StubRequest({"access_token": "unknown-token", "type": "daily"}, method="GET"),
        runtime_dependencies=daily_injected_dependencies,
    )
    results.append(_check(
        "main(): GET・type=dailyで未知のaccess_tokenは404",
        (body_get_unknown, status_get_unknown),
        ("unknown_access_token", 404),
    ))

    body_get_unsupported, status_get_unsupported = form_submission_main(
        _StubRequest({"access_token": "token-daily", "type": "monthly"}, method="GET"),
        runtime_dependencies=daily_injected_dependencies,
    )
    results.append(_check(
        "main(): GET・type=daily以外(monthly/annual/未指定)はGET動的レンダリング未対応で400"
        "(design.md適用範囲外、次回候補)",
        (body_get_unsupported, status_get_unsupported),
        ("unsupported_get_type", 400),
    ))

    # op-dailyはここまでのPOSTテストのllm_generateスタブがvehicle_id=None固定のため
    # vehicle_registry側の登録を経由していない(vehicle_count=0のまま)。daily.html側
    # (車両1台以上)のレンダリングを検証するため、ここで直接vehicle_count_storeへ1台分を
    # 加算する(実運用ではvehicle_idを含む実LLM出力経由でvehicle_registry.
    # register_vehicle_from_inspection_memo()が加算する想定、本テストはGETハンドラの
    # テンプレート選択ロジックのみを対象とするためモックで代替する)。
    # last_inspector_nameは直前のPOSTテストで「田中」に設定済みのため、GETはdaily.html
    # (車両1台以上側)を返し、inspector_nameには「田中」が注入される。
    daily_injected_dependencies["vehicle_count_store"].increment_vehicle_count("op-daily")
    body_get_daily, status_get_daily = form_submission_main(
        _StubRequest({"access_token": "token-daily", "type": "daily"}, method="GET"),
        runtime_dependencies=daily_injected_dependencies,
    )
    results.append(_check(
        "main(): GET・type=dailyの正常系は200",
        status_get_daily,
        200,
    ))
    results.append(_check(
        "main(): GET・type=dailyでop-dailyは車両登録済み(1台)のためdaily.html"
        "(「車両0台」表記を含まない側)が返る",
        "・車両0台)" in body_get_daily,
        False,
    ))
    results.append(_check(
        "main(): GET・type=dailyのレスポンスにはlast_inspector_name〈田中〉が注入される",
        'name="inspector_name" value="田中"' in body_get_daily,
        True,
    ))
    expected_today = today_jst_date_str()
    results.append(_check(
        "main(): GET・type=dailyのレスポンスには当日日付(JST)が注入される",
        f'name="date" value="{expected_today}"' in body_get_daily,
        True,
    ))

    # --- main(): GET・type=dailyでvehicle_count=0(車両未登録)の事業者はdaily-empty.html
    # が返り、last_inspector_name未設定時はinspector_nameが空欄(ダミー値を表示しない) ---
    empty_access_token_store = InMemoryAccessTokenStore()
    empty_access_token_store.set_access_token("op-empty", "token-empty")
    empty_dependencies = {
        "access_token_store": empty_access_token_store,
        "operator_store": InMemoryFleetOperatorStore(),
        "vehicle_store": InMemoryVehicleStore(),
        "vehicle_count_store": InMemoryVehicleCountStore(),
        "llm_generate": None,
    }
    body_get_empty, status_get_empty = form_submission_main(
        _StubRequest({"access_token": "token-empty", "type": "daily"}, method="GET"),
        runtime_dependencies=empty_dependencies,
    )
    results.append(_check(
        "main(): GET・type=dailyでvehicle_count=0の事業者はdaily-empty.html(「車両0台」"
        "表記を含む側)が200で返る",
        (status_get_empty, "・車両0台)" in body_get_empty),
        (200, True),
    ))
    results.append(_check(
        "main(): GET・type=dailyでlast_inspector_name未設定の事業者はinspector_nameが"
        "空欄で注入される(ダミー値「山田 太郎」を表示しない)",
        'name="inspector_name" value="">' in body_get_empty and "山田 太郎" not in body_get_empty,
        True,
    ))

    deps = get_form_submission_runtime_dependencies()
    results.append(_check(
        "get_form_submission_runtime_dependencies(): llm_generateは未接続(None)",
        deps["llm_generate"],
        None,
    ))
    results.append(_check(
        "get_form_submission_runtime_dependencies(): usage_counter_storeは"
        "InMemoryUsageCounterStore(フェーズ255)",
        isinstance(deps["usage_counter_store"], InMemoryUsageCounterStore),
        True,
    ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
