#!/usr/bin/env python3
"""
mvp-flow-draft.md「次回候補」・README フェーズ122「次回候補(2)」を受け、Webフォーム
送信処理本体を実装する(本venture未実装だった、個別モジュールを束ねるオーケストレーション
層)。trial_management.is_generation_paused()・record_generation_and_get_trial_end_notice()・
post_generation_checks.run_all_checks()という既存の個別モジュールを、1回のフォーム送信
処理としてどの順序で呼び出すかをまとめる。

- 実LLM呼び出しは行わない(APIキー取得はオーナー承認待ち、pending-approval.md参照)。
  呼び出し元が注入する`llm_generate`関数(入力メモ文字列→schema/output.schema.json準拠の
  dict)を介して構造化出力を受け取る想定のスタブとして設計した。
- overage_notifications.py(月間生成回数90%通知・保有台数プラン超過通知)は、通知対象と
  なるplan_id(pricing-plan.mdのlight/standard/fleet)がfleet_operatorドキュメントに
  いつ・どう書き込まれるか(Stripe決済導線、本venture未着手)が未確定のため、本フェーズでは
  意図的に組み込まない(次回以降の課題、README参照)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from post_generation_checks import run_all_checks
from trial_management import (
    CANCELED_NOTICE,
    FleetOperatorStoreProtocol,
    GENERATION_PAUSED_NOTICE,
    is_generation_paused,
    is_subscription_canceled,
    record_generation_and_get_trial_end_notice,
)

LlmGenerateFn = Callable[[str], dict]


def process_form_submission(
    raw_text: str,
    operator_id: str,
    now: datetime,
    llm_generate: LlmGenerateFn,
    operator_store: FleetOperatorStoreProtocol,
) -> dict:
    """1回のWebフォーム送信を処理する。

    呼び出し順序:
    1. is_subscription_canceled()で解約確定済みかを判定する。対象の場合はトライアル
       進捗・upgraded_atの値によらず常に最優先でLLM呼び出し自体を行わずCANCELED_NOTICEを
       返す(is_generation_paused()より先に判定する。kura-pasha/course-set-pasha/
       aircon-pashaで発見された「有料転換済みユーザーが解約後も無期限に生成を使い続け
       られる」欠落への対応、subscription-canceled-immediate-block-design.md相当)。
    2. is_generation_paused()でトライアル終了後・未アップグレードの一時停止対象かを
       判定する。対象の場合はLLM呼び出し自体を行わずGENERATION_PAUSED_NOTICEを返す
       (trial-end-notification-design.md 4節が想定していた「記録整形自体をスキップする
       分岐」)。
    3. llm_generate(raw_text)でschema/output.schema.json準拠の構造化出力(instance)を
       得る(実LLM未接続のためスタブ注入)。
    4. run_all_checks(instance)で厳守事項6・7の機械チェックを行う。エラーがあれば
       status="invalid_output"としてそのまま利用者には返さない(他venture未確立の
       フォールバック方針と同じ、一次検証のみを本フェーズの範囲とする)。
    5. instanceのstatusに応じて応答テキストを組み立てる。status="generated"の場合のみ、
       record_generation_and_get_trial_end_notice()でトライアル生成回数を加算し、
       ちょうど終了条件に達した場合は返却テキスト末尾に通知文を追記する。

    戻り値は次のキーを持つdict:
    - status: "canceled" | "paused" | "generated" | "out_of_scope"
               | "insufficient_input" | "invalid_output"
    - response_text: 利用者に返すテキスト(status="invalid_output"の場合はNone)
    - check_errors: run_all_checks()の結果(空リストなら問題なし)
    """
    if is_subscription_canceled(operator_id, operator_store):
        return {
            "status": "canceled",
            "response_text": CANCELED_NOTICE,
            "check_errors": [],
        }

    if is_generation_paused(operator_id, operator_store):
        return {
            "status": "paused",
            "response_text": GENERATION_PAUSED_NOTICE,
            "check_errors": [],
        }

    instance = llm_generate(raw_text)

    check_errors = run_all_checks(instance)
    if check_errors:
        return {
            "status": "invalid_output",
            "response_text": None,
            "check_errors": check_errors,
        }

    status = instance.get("status")

    if status == "out_of_scope":
        return {
            "status": status,
            "response_text": instance.get("out_of_scope_message"),
            "check_errors": [],
        }

    if status == "insufficient_input":
        return {
            "status": status,
            "response_text": instance.get("missing_fields_request"),
            "check_errors": [],
        }

    # status == "generated"
    record = instance.get("inspection_record") or {}
    response_text = record.get("body") or ""
    reminder_notice = record.get("reminder_notice")
    if reminder_notice:
        response_text += "\n" + reminder_notice

    trial_end_notice = record_generation_and_get_trial_end_notice(
        operator_store, operator_id, now
    )
    if trial_end_notice:
        response_text += "\n" + trial_end_notice

    return {
        "status": status,
        "response_text": response_text,
        "check_errors": [],
    }
