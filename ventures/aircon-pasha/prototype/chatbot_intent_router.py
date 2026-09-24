#!/usr/bin/env python3
"""
chatbot-intent-classification-llm-prompt-draft.md(フェーズ257)の「残課題」に残っていた
faq_guidance_candidate判定時の案内文組み立て、およびcompletion_report_request判定時への
一言追加(course-set-pashaのchatbot_intent_router.py append_faq_followup_hint()相当、
フェーズ238)を実装したもの(フェーズ258)。

位置づけ: 意図分類LLM(chatbot-intent-classification-llm-prompt-draft.md)が返す
category文字列を受け取り、実際に契約者へ返す文言を組み立てる後段処理の一部。
other_needs_human判定時のエスカレーション導線(運営者通知)はまだ設計されていないため
本モジュールには含めない(次回以降の課題)。分類結果を振り分ける入口関数
(course-set-pashaのroute_chatbot_intent()相当)もまだ実装せず、本フェーズでは
2つの純粋関数のみを追加する。実LLM呼び出し・実LINE送信は行わない。
"""

from __future__ import annotations

# chatbot-intent-classification-llm-prompt-draft.md「設計上の要点2」の方針どおり、
# FAQ項目別の回答文(owner_faq_router.pyのQ1〜Q7)は生成せず、既存のコマンド方式FAQへ
# 誘導する定型文のみを返す。項目を問わず同一文言。
_FAQ_GUIDANCE_MESSAGE = (
    "料金プラン・トライアル条件・解約/プラン変更・複数職人での共同利用・"
    "月間生成回数の上限・管理会社向けプランとの違いについては、「FAQ」と送信すると"
    "よくあるご質問の一覧からご確認いただけます。"
)

_FAQ_FOLLOWUP_HINT = "他にご質問がありましたら「FAQ」とお送りください。"


def render_faq_guidance_message() -> str:
    """faq_guidance_candidate判定時に返す案内文を組み立てる。"""
    return _FAQ_GUIDANCE_MESSAGE


def append_faq_followup_hint(reply_text: str) -> str:
    """completion_report_request判定時の返答文末尾に、FAQコマンドへの案内一言を
    付加する。chatbot-intent-classification-llm-prompt-draft.md「設計上の要点5」
    (完了報告メモとプラン質問等が同時に含まれる複合入力は判定順位1により
    completion_report_requestに判定され、FAQ案内が欠落する誤判定パターン)への
    運用回避として、判定結果に関わらず常に付加する。
    """
    return f"{reply_text}\n\n{_FAQ_FOLLOWUP_HINT}"
