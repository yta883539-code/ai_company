#!/usr/bin/env python3
"""
chatbot-intent-classification-llm-prompt-draft.md(フェーズ257)の「残課題」に残っていた
faq_guidance_candidate判定時の案内文組み立て、およびcompletion_report_request判定時への
一言追加(course-set-pashaのchatbot_intent_router.py append_faq_followup_hint()相当、
フェーズ238)を実装したもの(フェーズ258)。

フェーズ259: chatbot-intent-classification-escalation-design.mdで設計した
other_needs_human判定時のエスカレーション導線(運営者への即時通知)、および3分類を
実際に振り分ける入口関数route_chatbot_intent()(course-set-pashaのroute_chatbot_
intent()相当)を追加した。

位置づけ: 意図分類LLM(chatbot-intent-classification-llm-prompt-draft.md)が返す
category文字列を受け取り、実際に契約者へ返す文言を組み立てる後段処理。実LLM呼び出し・
実LINE送信は行わない。cloud_function_webhook.py側からの実結線は次回以降の課題として残す。
"""

from __future__ import annotations

from typing import Optional

from blocked_but_billing_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# design 1節の3分類。
CHATBOT_INTENT_VALUES = frozenset(
    {
        "completion_report_request",
        "faq_guidance_candidate",
        "other_needs_human",
    }
)

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


# ---------------------------------------------------------------------------
# エスカレーション通知(chatbot-intent-classification-escalation-design.md 3節)
# ---------------------------------------------------------------------------

CHATBOT_ESCALATION_NOTIFICATION_ALT_TEXT = (
    "[エアコンパシャッと運営] 一次受付チャットボットからのエスカレーション"
)


def format_chatbot_escalation_notification_message(user_id: str, memo_text: str) -> str:
    """design 3節の通知文言(本文部分)に、契約者IDとメッセージ本文を埋め込んで
    組み立てる。build_chatbot_escalation_notification_flex_message()のbody本文にも
    そのまま使う。"""
    return (
        "以下の契約者からのメッセージが、FAQ・完了報告書生成のいずれにも自動分類され"
        "ませんでした。内容をご確認のうえ、必要に応じて個別にご対応ください。\n"
        f"契約者ID: {user_id}\n"
        f"メッセージ本文: {memo_text}"
    )


def build_chatbot_escalation_notification_flex_message(user_id: str, memo_text: str) -> dict:
    """design 3節: ボタンを持たない、テキストのみのbubble形式のFlex Messageを組み立てる
    (payment_suspension_owner_notification.build_payment_suspension_owner_
    notification_flex_message()と同じ構成。本ventureの運営者通知はいずれもこの
    bubble形式に統一されている)。"""
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": CHATBOT_ESCALATION_NOTIFICATION_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": format_chatbot_escalation_notification_message(user_id, memo_text),
                    "wrap": True,
                    "margin": "md",
                },
            ],
        },
    }


def send_chatbot_escalation_notification(
    user_id: str,
    memo_text: str,
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> bool:
    """design 3節「送信経路」本体。other_needs_humanと判定されたメッセージ受信時に
    都度(日次バッチではなく即時)呼び出される想定。design 2節のとおり送信済みフラグは
    持たず、同一契約者からの連続したother_needs_human判定もそれぞれ都度通知する。

    送信失敗時はFalseを返すのみで、状態の書き込み・再試行キューへの登録は行わない
    (design時点で該当の永続化先が未設計のため)。
    """
    contents = build_chatbot_escalation_notification_flex_message(user_id, memo_text)
    try:
        push_client.send_flex_message(
            owner_line_user_id, CHATBOT_ESCALATION_NOTIFICATION_ALT_TEXT, contents
        )
    except LinePushDeliveryError:
        return False
    return True


# design 4節: other_needs_human判定時も無応答のまま放置せず、契約者自身には
# CHATBOT_ESCALATION_NOTIFICATION_TEMPLATE(運営者宛)とは別の定型受付応答を返す。
OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT = (
    "お問い合わせありがとうございます。担当者が内容を確認しご連絡しますので、"
    "少々お待ちください。"
)


def route_chatbot_intent(
    intent: str,
    *,
    generation_reply_text: Optional[str] = None,
    user_id: Optional[str] = None,
    memo_text: Optional[str] = None,
    push_client: Optional[LinePushClient] = None,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> str:
    """分類結果(`intent`)を受け取り、契約者への既存の返信経路にそのまま渡せる最終的な
    返信文を1本にまとめる、分類「後」の配線の入口(design 5節、course-set-pashaの
    route_chatbot_intent()相当)。

    - `completion_report_request`: 完了報告書生成本体(実LLM接続がオーナー承認待ちの
      ため本モジュールの対象外)が組み立てた`generation_reply_text`を必須引数として
      受け取り、`append_faq_followup_hint()`を適用して返す。
    - `faq_guidance_candidate`: `render_faq_guidance_message()`をそのまま返す
      (本ventureは3分類のみのため、course-set-pasha版のようなFAQ項目別コード変換は
      不要)。
    - `other_needs_human`: `send_chatbot_escalation_notification()`で運営者へ即時
      通知した上で(`push_client`必須)、契約者には`OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_
      TEXT`を返す。通知の送信成否(戻り値のbool)はログ・監視目的で呼び出し元に判断を
      委ね、本関数は通知の成否にかかわらず同じ定型応答を返す(design 5節が「無応答の
      まま放置しない」ことを主眼としているため)。
    """
    if intent == "completion_report_request":
        if generation_reply_text is None:
            raise ValueError(
                "completion_report_requestにはgeneration_reply_textが必須です"
            )
        return append_faq_followup_hint(generation_reply_text)
    if intent == "faq_guidance_candidate":
        return render_faq_guidance_message()
    if intent == "other_needs_human":
        if user_id is None or memo_text is None or push_client is None:
            raise ValueError(
                "other_needs_humanにはuser_id・memo_text・push_clientが必須です"
            )
        send_chatbot_escalation_notification(
            user_id, memo_text, push_client, owner_line_user_id=owner_line_user_id
        )
        return OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT
    raise ValueError(f"未知の分類値です: {intent!r}")
