#!/usr/bin/env python3
"""
mvp-flow-draft.md(フェーズ2)「入力」節・tech-stack.md(フェーズ7)「Webフォーム」節で
整理した、Webフォームから届く単発イベントメモをLLM呼び出し前に受け付ける処理の骨格。
llm-system-prompt-draft.mdの次回候補(「チャット/フォームの受信処理部分」実装)、および
mvp-flow-draft.mdの次回候補(2)に対応する。

位置づけ:
- 本venture(event-komiguai-pasha)はline-reservation-ai等と異なり会話状態マシンを持たず、
  1フォーム送信=1イベント分の単方向バッチ処理で完結する(tech-stack.md「MVPスコープ」)。
  このため本モジュールは、LINE Webhookのような継続的なイベントディスパッチではなく、
  1回のフォーム送信ペイロードを受け取り、(a)厳守事項8の必須項目充足チェックを行い、
  (b)不足していればLLMを呼ばずにその場でinsufficient_input応答を構成し、
  (c)充足していればLLMへ渡すリクエストペイロードを組み立てる、という分岐のみを担う。
- 実LLM呼び出し(course-set-pasha等のllm_client相当)・実Webフォーム/Cloud Run functions
  へのデプロイはいずれも別モジュール・オーナー承認後の課題であり、本モジュールはそれより
  手前の「受信したフォーム入力をどう検証し、どちらの経路に振るか」のロジックのみを
  実クラウド接続なしで検証可能にしたもの(course-set-pasha/cloud_function_webhook.pyと
  同じ位置づけ)。
- fee_inquiry_note(厳守事項7)・out_of_scope判定・4出力の生成自体はLLMの構造化出力に
  委ねる方針(llm-system-prompt-draft.md厳守事項7・8)のため、本モジュールでは判定しない。

設計の参照元: mvp-flow-draft.md(フェーズ2・21・25)、tech-stack.md(フェーズ7)、
llm-system-prompt-draft.md(フェーズ3)、schema/output.schema.json(フェーズ5・25)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# mvp-flow-draft.mdの「出力スキーマ方針」: insufficient_inputはこの3項目のいずれかが
# 欠落している場合。staffing・outdoor_queueは必須項目に含まれない(未入力でも
# generated/out_of_scope側の判定・注記ロジックで扱う、厳守事項2参照)。
REQUIRED_FIELDS = ("capacity", "entry_exit_points", "admission_type")

# missing_fields_request文中で項目名を主催者にわかる日本語で示すための対応表。
FIELD_LABELS = {
    "capacity": "会場キャパシティ",
    "entry_exit_points": "入場口・退場口の数(共用か分離か)",
    "admission_type": "入場方式(自由入場/指定席/事前予約制 等)",
}


@dataclass(frozen=True)
class EventMemoInput:
    """Webフォームの5入力要素(mvp-flow-draft.mdフェーズ2)。いずれも主催者が入力した
    生テキスト(構造化・コード化はLLM側で行う)。未入力はNoneまたは空文字で表す。"""

    capacity: Optional[str] = None
    entry_exit_points: Optional[str] = None
    admission_type: Optional[str] = None
    staffing: Optional[str] = None
    outdoor_queue: Optional[str] = None


def parse_form_payload(raw_payload: dict) -> EventMemoInput:
    """Webフォーム送信の生ペイロード(dict)をEventMemoInputへ変換する。
    空文字・空白のみの入力は未入力(None)として扱う(厳守事項8の判定を単純化する)。"""

    def _clean(value: object) -> Optional[str]:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    return EventMemoInput(
        capacity=_clean(raw_payload.get("capacity")),
        entry_exit_points=_clean(raw_payload.get("entry_exit_points")),
        admission_type=_clean(raw_payload.get("admission_type")),
        staffing=_clean(raw_payload.get("staffing")),
        outdoor_queue=_clean(raw_payload.get("outdoor_queue")),
    )


def find_missing_required_fields(memo: EventMemoInput) -> list[str]:
    """厳守事項8: capacity・entry_exit_points・admission_typeのうち欠落している項目名
    (REQUIRED_FIELDSのキー)を入力順に返す。欠落なしの場合は空リスト。"""

    missing = []
    for field in REQUIRED_FIELDS:
        if getattr(memo, field) is None:
            missing.append(field)
    return missing


def build_insufficient_input_response(missing_fields: list[str]) -> dict:
    """schema/output.schema.jsonの形に沿った status=insufficient_input 応答を、LLMを
    呼び出さずその場で構成する。厳守事項8「不明な項目を推測で埋めて生成しない」ため、
    欠落項目を具体的に列挙するのみで4出力はすべてnullとする。"""

    if not missing_fields:
        raise ValueError("missing_fields_request can only be built when fields are missing")

    labels = "・".join(FIELD_LABELS[field] for field in missing_fields)
    return {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": f"{labels}について追加で教えてください。",
        "checklist": None,
        "staffing_plan": None,
        "notice_board_text": None,
        "near_miss_record_template": None,
        "fee_inquiry_note": None,
    }


def build_llm_request_payload(memo: EventMemoInput) -> dict:
    """必須項目が充足している場合に、LLM(llm-system-prompt-draft.md厳守事項1〜10)へ渡す
    リクエストペイロードを組み立てる。実LLM API呼び出し自体は別モジュール(APIキー取得後、
    オーナー承認待ちの範囲)に委ねるため、ここでは呼び出し用の入力データを整形するだけに
    留める。"""

    if find_missing_required_fields(memo):
        raise ValueError("required fields must be present before building an LLM request")

    return {
        "system_prompt_ref": "llm-system-prompt-draft.md",
        "output_schema_ref": "schema/output.schema.json",
        "user_memo_fields": {
            "capacity": memo.capacity,
            "entry_exit_points": memo.entry_exit_points,
            "admission_type": memo.admission_type,
            "staffing": memo.staffing,
            "outdoor_queue": memo.outdoor_queue,
        },
    }


def handle_form_submission(raw_payload: dict) -> dict:
    """Webフォーム送信の受信処理エントリーポイント(骨格)。tech-stack.mdの
    「Webhook/バックエンド」節で想定するCloud Run functionsのHTTPSトリガーから
    呼ばれる想定。戻り値は次のいずれか:
    - status=insufficient_inputの完成済み応答(dict。LLM呼び出し不要)
    - LLMへ渡すリクエストペイロード(dict。呼び出し側が実LLM clientに渡す想定)
    """

    memo = parse_form_payload(raw_payload)
    missing = find_missing_required_fields(memo)
    if missing:
        return build_insufficient_input_response(missing)
    return build_llm_request_payload(memo)
