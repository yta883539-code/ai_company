#!/usr/bin/env python3
"""
webhook-processing-flow-design.mdで設計した、Webhook受信〜LLM呼び出し〜返信の
バックエンド処理フローを実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のGCPプロジェクト作成・Cloud Functionsのデプロイ、実LLM API・LINE Messaging API
  への接続は「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「受信したメモをどう解釈し、
  どのタイミングで何を検証し、どう返信文を組み立てるか」という処理ロジック自体を
  実クラウド接続なしで検証可能にしたもの(line-reservation-aiのengine.py・
  cloud_function_webhook.pyと同じ位置づけ)。
- LLM呼び出し(llm_call)・LINE返信送信(reply_client)はいずれも差し替え可能なProtocolとし、
  承認後は実クライアントに差し替えるだけで動作させられるように設計している。

設計の参照元: webhook-processing-flow-design.md
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from history_export import history_rows_to_csv_text  # noqa: E402
from post_generation_checks import run_all_checks  # noqa: E402
from validate_test_cases import (  # noqa: E402
    SCHEMA,
    validate_against_schema,
    validate_cross_field_rules,
)


# ---------------------------------------------------------------------------
# 署名検証(line-reservation-ai/prototype/cloud_function_webhook.pyから移植、変更なし)
# ---------------------------------------------------------------------------

def verify_line_signature(body: bytes, signature_header: Optional[str], channel_secret: str) -> bool:
    """X-Line-Signatureの検証(HMAC-SHA256 + Base64)。channel_secretの取得自体は
    LINE公式アカウント開設(オーナー承認待ち)後に得られる値のため、実際の検証はその後に行う。
    """
    import base64
    import hashlib
    import hmac

    if not signature_header:
        return False
    computed = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed_b64 = base64.b64encode(computed).decode("utf-8")
    return hmac.compare_digest(computed_b64, signature_header)


# ---------------------------------------------------------------------------
# LLM呼び出し・返信送信のProtocol(実クライアントとスタブ版の共通インターフェース)
# ---------------------------------------------------------------------------

class LlmCallClient(Protocol):
    def generate(self, memo_text: str, has_photo: bool, retry_context: Optional[str] = None) -> dict:
        """schema/output.schema.jsonに準拠した構造化出力(dict)を返す想定。

        retry_contextが渡された場合(1回目の検証エラー後の再生成時)、直前の出力の
        何が不正だったか(検証エラーの概要)を実LLM接続後にプロンプトへ添える想定
        (json-output-retry-fallback.mdの「同一入力で1回だけ再生成」方針に準拠)。
        """
        ...


class ReplyClient(Protocol):
    def reply(self, reply_token: str, message_text: str) -> None:
        ...


class InMemoryReplyClient:
    """実LINE API接続の代わりに送信内容を記録するだけの検証用クライアント。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def reply(self, reply_token: str, message_text: str) -> None:
        self.sent.append((reply_token, message_text))


# ---------------------------------------------------------------------------
# 返信本文の組み立て(status別)
# ---------------------------------------------------------------------------

VALIDATION_FAILURE_FALLBACK_MESSAGE = (
    "内容の確認中に問題が発生しました。お手数ですが、もう一度メモを送り直してください。"
)


def format_generated_reply(instance: dict) -> str:
    """status=generatedの構造化出力を、出力1・出力2・出力3をまとめた1通の返信文に組み立てる。"""
    sns_post = instance["sns_post"]
    line_web_notice = instance["line_web_notice"]
    history_rows = instance["history_rows"]

    sns_body = sns_post["body"]
    hashtags_line = " ".join(sns_post["hashtags"])
    csv_text = history_rows_to_csv_text(history_rows)

    parts = [
        "【SNS投稿文の下書き】",
        sns_body if not hashtags_line else f"{sns_body}\n{hashtags_line}",
        "",
        "【LINE/Web告知文の下書き】",
        line_web_notice["body"],
        "",
        "【更新履歴(スプレッドシート転記用)】",
        csv_text.rstrip("\n"),
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
        # 崩れているため実行しない(line-reservation-aiのjson-output-retry-fallback.mdの
        # 「構文崩れは一律escalation合成」と同じ考え方で、以降の詳細検証をスキップする)。
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
    handled: bool  # False=画像単体イベント等、本フローの処理対象外だったため何もしなかった
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
) -> MemoProcessResult:
    """LINEのmessageイベント1件を処理する(署名検証済みの前提)。

    設計上の判断(webhook-processing-flow-design.md準拠):
    1. message.type != "text" のイベント(画像単体送信等)は本フローの対象外とし、
       返信を送らずhandled=Falseで返す。
    2. has_photoはイベント側の付随情報として受け取る(束ね方自体は残課題、
       webhook-processing-flow-design.md「残課題」参照)。
    3. LLM呼び出し結果を検証し、エラーがあれば同一入力で1回だけ再生成をリクエストする
       (json-output-retry-fallback.mdの「同一入力で1回だけ」方針をline-reservation-aiと
       同じ形で採用。再生成後もエラーが残る場合は安全側に倒し、定型の再送依頼文言を返す)。
    """
    message = event.get("message", {})
    if message.get("type") != "text":
        return MemoProcessResult(handled=False, reply_sent=False, reply_text=None)

    reply_token = event["replyToken"]
    memo_text = message["text"]
    has_photo = bool(event.get("hasPhoto", False))

    instance = llm_call.generate(memo_text, has_photo)
    errors = validate_llm_output(instance)
    retried = False

    if errors:
        retried = True
        instance = llm_call.generate(memo_text, has_photo, retry_context=_summarize_errors_for_retry(errors))
        errors = validate_llm_output(instance)

    if errors:
        reply_client.reply(reply_token, VALIDATION_FAILURE_FALLBACK_MESSAGE)
        return MemoProcessResult(
            handled=True, reply_sent=True,
            reply_text=VALIDATION_FAILURE_FALLBACK_MESSAGE, validation_errors=errors, retried=retried,
        )

    reply_text = format_reply_text(instance)
    reply_client.reply(reply_token, reply_text)
    return MemoProcessResult(handled=True, reply_sent=True, reply_text=reply_text, retried=retried)


def _demo() -> None:
    class StubLlmClient:
        """schema/validate_test_cases.pyのG1フィクスチャ相当を返す固定スタブ。"""

        def generate(self, memo_text: str, has_photo: bool, retry_context: Optional[str] = None) -> dict:
            return {
                "status": "generated",
                "out_of_scope_message": None,
                "missing_fields_request": None,
                "sns_post": {
                    "body": "【課題入れ替えのお知らせ】エリアAに新着課題8本追加しました。",
                    "hashtags": ["#ボルダリング", "#新着課題"],
                    "mentions_photo": has_photo,
                },
                "line_web_notice": {"body": "エリアA:新着8本(黄テープ帯)を追加しました。"},
                "history_rows": [
                    {
                        "revision_date": "2026-08-09",
                        "area": "エリアA",
                        "tape_color_or_grade_band": "黄テープ",
                        "count": 8,
                        "feature_keywords": ["ダイナミック"],
                    },
                ],
                "unchanged_areas": [],
            }

    reply_client = InMemoryReplyClient()
    event = {
        "replyToken": "demo-reply-token",
        "message": {"type": "text", "text": "エリアA 黄テープ 8本新規、2026/8/9改訂"},
        "hasPhoto": False,
    }
    result = process_memo_event(event, StubLlmClient(), reply_client)
    print(f"handled={result.handled} reply_sent={result.reply_sent}")
    print(result.reply_text)

    image_only_event = {"replyToken": "demo-reply-token-2", "message": {"type": "image"}}
    result2 = process_memo_event(image_only_event, StubLlmClient(), reply_client)
    print(f"\n[image-only event] handled={result2.handled}")


if __name__ == "__main__":
    _demo()
