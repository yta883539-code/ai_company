#!/usr/bin/env python3
"""
mvp-flow-draft.mdで整理した「作業後メモ→LLM呼び出し→3種類の下書き生成→返信」という
単方向バッチ処理のフローを実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のGCPプロジェクト作成・Cloud Functionsのデプロイ、実LLM API・LINE公式アカウント等
  への接続は「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「受信したメモをどう解釈し、
  どのタイミングで何を検証し、どう返信文を組み立てるか」という処理ロジック自体を
  実クラウド接続なしで検証可能にしたもの(course-set-pasha・line-reservation-aiの
  prototype/cloud_function_webhook.pyと同じ位置づけ)。
- LLM呼び出し(llm_call)・返信送信(reply_client)はいずれも差し替え可能なProtocolとし、
  承認後は実クライアントに差し替えるだけで動作させられるように設計している。
- course-set-pashaとの主な差異: 本ventureのhistory_rowは単一オブジェクト(1メモ=1件の
  訪問施工が前提、schema/output.schema.json参照)のため、history_export.pyのような
  CSV変換モジュールは不要(表1行分をそのまま文字列化するだけで足りる)。テキスト・画像の
  束ね方(text-image-bundling-design.md相当)も、mvp-flow-draft.mdで写真は「任意添付」の
  扱いにとどまり出力スキーマにhasPhoto相当のフィールドが無いため、本モジュールでは
  対応を見送った(必要になった場合の課題としてREADME.mdの「次にやること」に残す)。

設計の参照元: mvp-flow-draft.md, llm-system-prompt-draft.md, schema/output.schema.json
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from post_generation_checks import run_all_checks  # noqa: E402
from validate_test_cases import (  # noqa: E402
    SCHEMA,
    validate_against_schema,
    validate_cross_field_rules,
)


# ---------------------------------------------------------------------------
# LLM呼び出し・返信送信のProtocol(実クライアントとスタブ版の共通インターフェース)
# ---------------------------------------------------------------------------

class LlmCallClient(Protocol):
    def generate(self, memo_text: str, retry_context: Optional[str] = None) -> dict:
        """schema/output.schema.jsonに準拠した構造化出力(dict)を返す想定。

        retry_contextが渡された場合(1回目の検証エラー後の再生成時)、直前の出力の
        何が不正だったか(検証エラーの概要)を実LLM接続後にプロンプトへ添える想定
        (course-set-pasha/line-reservation-aiのjson-output-retry-fallback.mdの
        「同一入力で1回だけ再生成」方針に準拠)。
        """
        ...


class ReplyClient(Protocol):
    def reply(self, reply_token: str, message_text: str) -> None:
        ...


class InMemoryReplyClient:
    """実LINE API/フォーム通知接続の代わりに送信内容を記録するだけの検証用クライアント。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def reply(self, reply_token: str, message_text: str) -> None:
        self.sent.append((reply_token, message_text))


# ---------------------------------------------------------------------------
# 月間生成回数カウント・上限接近通知
# (limit-approaching-notification-design.md 2〜5節の実装。course-set-pashaの
#  UsageCounterProtocol/InMemoryUsageCounter/build_usage_noticeと同じ構成だが、
#  本ventureは3プランとも閾値「残り5回」で固定〈設計2節〉のため、
#  course-set-pashaのPLAN_NOTICE_THRESHOLDSに相当するプラン別マッピングは持たない。)
# ---------------------------------------------------------------------------

class UsageCounterProtocol(Protocol):
    def get_count(self, user_id: str, month: str) -> int:
        ...

    def increment(self, user_id: str, month: str) -> int:
        """インクリメント後のカウント値を返す契約とする。"""
        ...


class InMemoryUsageCounter:
    """実Firestore接続の代わりにdictでカウントを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}

    def get_count(self, user_id: str, month: str) -> int:
        return self._counts.get((user_id, month), 0)

    def increment(self, user_id: str, month: str) -> int:
        key = (user_id, month)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]


# pricing-plan.md「料金プラン」表準拠
PLAN_MONTHLY_LIMITS = {"スモール": 40, "スタンダード": 90, "繁忙期対応": 150}
PLAN_OVERAGE_UNIT_PRICE_JPY = {"スモール": 60, "スタンダード": 50, "繁忙期対応": 40}
# limit-approaching-notification-design.md 2節: 3プラン共通で「残り5回」固定
# (日次件数の上振れ〈繁忙期含む〉をカバーできる最大値として採用、プラン別の使い分けは見送り)。
NOTICE_THRESHOLD = 5


def current_month_jst() -> str:
    """JST基準の暦月をYYYY-MM形式で返す(limit-approaching-notification-design.md 3節、
    月の区切りはJST基準の暦月とする方針に準拠)。"""
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m")


def build_usage_notice(plan: str, count_after_increment: int) -> Optional[str]:
    """limit-approaching-notification-design.md 4節の通知文言を、該当条件のときのみ返す
    (残り5回に達した生成完了時、または上限を超えた生成完了時)。それ以外はNoneを返す。
    """
    limit = PLAN_MONTHLY_LIMITS[plan]
    unit_price = PLAN_OVERAGE_UNIT_PRICE_JPY[plan]

    if count_after_increment > limit:
        return f"※今月の無料生成回数の上限を超えたため、本回は追加料金{unit_price}円が発生します"
    if limit - count_after_increment == NOTICE_THRESHOLD:
        return (
            f"※今月の生成回数は残り{NOTICE_THRESHOLD}回です"
            f"(上限到達後は1回あたり{unit_price}円の追加料金がかかります)"
        )
    return None


# ---------------------------------------------------------------------------
# 返信本文の組み立て(status別)
# ---------------------------------------------------------------------------

VALIDATION_FAILURE_FALLBACK_MESSAGE = (
    "内容の確認中に問題が発生しました。お手数ですが、もう一度メモを送り直してください。"
)


def format_history_row_text(history_row: dict) -> str:
    """history_row(単一オブジェクト)を表1行分の読みやすいテキストに整形する。
    course-set-pashaのhistory_rows_to_csv_text()相当だが、本ventureは1メモ=1件のため
    CSV化ではなく項目名付きの箇条書きとした(スプレッドシートへの手動転記を想定、
    mvp-flow-draft.md「出力3」参照)。"""
    labels = [
        ("施工日", history_row.get("work_date")),
        ("機種系統・号数", history_row.get("model_type_and_capacity")),
        ("汚れ状況", history_row.get("dirt_condition")),
        ("追加施工", history_row.get("additional_treatment")),
        ("次回推奨時期", history_row.get("next_recommended_date")),
    ]
    return "\n".join(f"{label}: {value if value is not None else '(未記載)'}" for label, value in labels)


def format_generated_reply(instance: dict) -> str:
    """status=generatedの構造化出力を、出力1・出力2・出力3をまとめた1通の返信文に組み立てる。"""
    parts = [
        "【作業完了報告メッセージの下書き】",
        instance["completion_report"]["body"],
        "",
        "【お手入れ案内の下書き】",
        instance["care_guide"]["body"],
        "",
        "【作業履歴記録(スプレッドシート転記用)】",
        format_history_row_text(instance["history_row"]),
    ]
    return "\n".join(parts)


def format_reply_text(instance: dict) -> str:
    status = instance["status"]
    if status == "generated":
        return format_generated_reply(instance)
    if status == "out_of_scope":
        return instance["out_of_scope_message"]
    if status == "insufficient_input":
        return instance["missing_fields_request"]
    raise ValueError(f"unexpected status: {status!r}")


# ---------------------------------------------------------------------------
# 構造化出力の検証(スキーマ適合性・クロスフィールドルール・後処理ヒューリスティック)
# ---------------------------------------------------------------------------

def validate_llm_output(instance: dict) -> list[str]:
    """3段階の検証をまとめて行い、エラーメッセージのリストを返す(空リスト=検証OK)。"""
    errors = validate_against_schema(instance, SCHEMA)
    if errors:
        # スキーマ自体に適合しない場合、cross-fieldや後処理チェックはstatus等の前提が
        # 崩れているため実行しない(course-set-pasha/line-reservation-aiと同じ考え方)。
        return errors

    errors += validate_cross_field_rules(instance)
    if instance.get("status") == "generated":
        errors += run_all_checks(instance)
    return errors


# ---------------------------------------------------------------------------
# 1メモ単位の処理結果
# ---------------------------------------------------------------------------

@dataclass
class MemoProcessResult:
    handled: bool  # False=テキスト以外の単体イベント等、本フローの処理対象外だったため何もしなかった
    reply_sent: bool
    reply_text: Optional[str]
    validation_errors: list = field(default_factory=list)
    retried: bool = False  # True=1回目の検証エラー後、再生成を1回試みた


def _summarize_errors_for_retry(errors: list[str]) -> str:
    """再生成プロンプトに添える検証エラーの短い概要(実LLM接続後に使用)。"""
    return "; ".join(errors[:3])


def process_memo_event(
    event: dict,
    llm_call: LlmCallClient,
    reply_client: ReplyClient,
    *,
    usage_counter: Optional[UsageCounterProtocol] = None,
    plan: Optional[str] = None,
    month: Optional[str] = None,
) -> MemoProcessResult:
    """テキストメモ1件を処理する(署名検証等の受信基盤側の処理は別モジュールの前提)。

    設計上の判断(mvp-flow-draft.md準拠):
    1. message.type != "text" のイベント(画像単体送信等)は本フローの対象外とし、
       返信を送らずhandled=Falseで返す。
    2. LLM呼び出し結果を検証し、エラーがあれば同一入力で1回だけ再生成をリクエストする
       (course-set-pasha/line-reservation-aiのjson-output-retry-fallback.mdの
       「同一入力で1回だけ」方針を踏襲。再生成後もエラーが残る場合は安全側に倒し、
       定型の再送依頼文言を返す)。
    3. usage_counter・planが渡された場合のみ、月間生成回数カウント・上限接近通知
       (limit-approaching-notification-design.md)を行う。カウント対象はstatus=="generated"の
       場合のみとし、返信本文組み立て直後にインクリメントする。
       usage_counterがNoneの場合(未接続時)はカウント処理自体をスキップする。
    """
    message = event.get("message", {})
    if message.get("type") != "text":
        return MemoProcessResult(handled=False, reply_sent=False, reply_text=None)

    reply_token = event["replyToken"]
    memo_text = message["text"]

    instance = llm_call.generate(memo_text)
    errors = validate_llm_output(instance)
    retried = False

    if errors:
        retried = True
        instance = llm_call.generate(memo_text, retry_context=_summarize_errors_for_retry(errors))
        errors = validate_llm_output(instance)

    if errors:
        reply_client.reply(reply_token, VALIDATION_FAILURE_FALLBACK_MESSAGE)
        return MemoProcessResult(
            handled=True, reply_sent=True,
            reply_text=VALIDATION_FAILURE_FALLBACK_MESSAGE, validation_errors=errors, retried=retried,
        )

    reply_text = format_reply_text(instance)
    if instance["status"] == "generated" and usage_counter is not None and plan is not None:
        user_id = event.get("source", {}).get("userId")
        if user_id:
            count = usage_counter.increment(user_id, month or current_month_jst())
            notice = build_usage_notice(plan, count)
            if notice:
                reply_text = f"{reply_text}\n\n{notice}"

    reply_client.reply(reply_token, reply_text)
    return MemoProcessResult(handled=True, reply_sent=True, reply_text=reply_text, retried=retried)


def _demo() -> None:
    class StubLlmClient:
        """schema/validate_test_cases.pyのG1_basicフィクスチャ相当を返す固定スタブ。"""

        def generate(self, memo_text: str, retry_context: Optional[str] = None) -> dict:
            return {
                "status": "generated",
                "out_of_scope_message": None,
                "missing_fields_request": None,
                "completion_report": {
                    "body": "壁掛け型2.2kWのエアコンについて、フィルター・熱交換器・送風ファンまで分解洗浄いたしました。"
                            "カビ・ホコリの汚れは中程度でしたが、洗浄後はきれいな状態になっております。防カビコートも施工いたしました。",
                    "mentions_refrigerant_or_electrical": False,
                },
                "care_guide": {
                    "body": "フィルターは月1回程度を目安に、掃除機やご自身で水洗いいただくと効果的です。"
                            "次回の分解洗浄は来年同時期を目安にご検討ください。自己分解洗浄は内部の破損・感電等のリスクが"
                            "あるため、分解を伴う清掃は専門業者へのご依頼をおすすめします。",
                    "next_recommended_date_is_estimate": False,
                },
                "history_row": {
                    "work_date": "2026-08-09",
                    "model_type_and_capacity": "壁掛け型2.2kW",
                    "dirt_condition": "カビ・ホコリ汚れ中程度",
                    "additional_treatment": "防カビコートあり",
                    "next_recommended_date": "来年同時期",
                },
            }

    reply_client = InMemoryReplyClient()
    event = {
        "replyToken": "demo-reply-token",
        "message": {
            "type": "text",
            "text": "壁掛け型2.2kW、フィルター・熱交換器・送風ファンまで分解洗浄、カビ・ホコリ汚れ中程度、"
                    "防カビコート施工あり、次回推奨は来年同時期",
        },
    }
    result = process_memo_event(event, StubLlmClient(), reply_client)
    print(f"handled={result.handled} reply_sent={result.reply_sent}")
    print(result.reply_text)

    image_only_event = {"replyToken": "demo-reply-token-2", "message": {"type": "image"}}
    result2 = process_memo_event(image_only_event, StubLlmClient(), reply_client)
    print(f"\n[image-only event] handled={result2.handled}")


if __name__ == "__main__":
    _demo()
