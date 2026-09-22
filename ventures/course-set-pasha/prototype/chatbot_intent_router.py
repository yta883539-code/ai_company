#!/usr/bin/env python3
"""
chatbot-intent-classification-escalation-design.mdで設計した「意図分類プロンプトの
具体的設計」「エスカレーション導線」のうち、次回以降の課題として残っていた
(1) faq_intent_to_code()マッピング層、(2) エスカレーション通知送信ヘルパー、を
実行可能なコードに落とし込んだもの。

位置づけ: 実LLMによる意図分類自体(自由入力テキスト→`post_generation_request`/
`faq_pricing`/`faq_howto`/`faq_cancel_change`/`other_needs_human`への分類)は本モジュールの
対象外(引き続き実LLM呼び出しを伴う承認待ち領域)。本モジュールは、分類結果(文字列)が
既に得られている前提で、(1)FAQ系3分類をowner_faq_router.pyの定型回答にどうマッピング
するか、(2)`other_needs_human`判定時にオーナーへどう通知するか、という分類「後」の
配線のみを検証可能にする(payment_suspension_owner_notification.pyと同じ位置づけ)。

設計の参照元: chatbot-intent-classification-escalation-design.md
"""

from __future__ import annotations

from typing import Optional

from owner_faq_router import render_owner_faq_answer_message, render_owner_faq_menu_message
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# design 3節: payment-suspension-owner-notification-design.mdが確立した固定送信先を
# そのまま踏襲する(本venture内で運営者宛送信先を複数箇所で個別定義しない)。
from payment_suspension_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER

# design 1節: LLMへの分類指示の出力値として採用する5分類。
CHATBOT_INTENT_VALUES = frozenset(
    {
        "post_generation_request",
        "faq_pricing",
        "faq_howto",
        "faq_cancel_change",
        "other_needs_human",
    }
)

# design 1節: faq_pricing→Q2、faq_cancel_change→Q3はowner-operation-self-service-faq.mdの
# 項目と1対1で対応する。faq_howtoのみQ1・Q4〜Q6の複数項目にまたがり1対1に定まらないため、
# このマッピングには含めず、render_chatbot_faq_response_message()側で個別に扱う。
_CHATBOT_INTENT_TO_FAQ_CODE: dict[str, str] = {
    "faq_pricing": "Q2",
    "faq_cancel_change": "Q3",
}


def faq_intent_to_code(intent: str) -> Optional[str]:
    """FAQ系の分類値(`faq_pricing`/`faq_cancel_change`)を、owner_faq_router.pyの
    単一の項目コードへ変換する。`faq_howto`は複数項目にまたがり単一コードに定まらない
    ためNoneを返す(呼び出し元はrender_chatbot_faq_response_message()を使うこと)。
    FAQ系以外の分類値(`post_generation_request`・`other_needs_human`)を渡した場合も
    Noneを返す。
    """
    return _CHATBOT_INTENT_TO_FAQ_CODE.get(intent)


# chatbot-intent-classification-llm-prompt-draft.md「想定される誤判定パターン」節:
# 判定順位1により、投稿文生成依頼とFAQ質問(料金プラン等)が同時に含まれる複合入力は
# post_generation_requestに判定され、FAQ部分への回答が欠落する。運用回避として、
# 投稿文生成結果の返答文の末尾に本一言を添え、FAQ相当の質問が埋もれていた場合でも
# 契約者自身が再度問い合わせられる導線を用意する。
POST_GENERATION_FAQ_FOLLOWUP_HINT = (
    "\n\n※料金プランや使い方など他にご質問がありましたら、続けてメッセージを"
    "お送りください。"
)


def append_faq_followup_hint(generation_reply_text: str) -> str:
    """post_generation_request判定時の返答文(投稿文生成結果)の末尾に、
    chatbot-intent-classification-llm-prompt-draft.md「想定される誤判定パターン」節の
    運用回避として一言を追加する。

    判定順位1により複合入力(投稿文生成依頼+FAQ質問)がpost_generation_requestに
    判定されFAQ部分の回答が欠落するケースを、質問を検知せず常に一言を添えることで
    回避する(どの入力がFAQ相当を含んでいたかをこの関数側で判定することはしない。
    判定を試みるとpost_generation_request最優先というフェイルセーフの単純さが崩れる
    ため、常時付与する設計とした)。

    呼び出し元は投稿文生成本体(実LLM接続がオーナー承認待ちのため未実装)の返答文
    組み立て処理を想定しており、本関数自体は文字列の末尾追加のみを行う純粋関数。
    """
    return generation_reply_text + POST_GENERATION_FAQ_FOLLOWUP_HINT


def render_chatbot_faq_response_message(intent: str) -> str:
    """design 1節に基づき、FAQ系3分類(`faq_pricing`/`faq_howto`/`faq_cancel_change`)に
    対する回答文言を組み立てる。回答文言自体の二重管理を避けるため、既存の
    owner_faq_router.pyの定型回答関数をそのまま呼び出す。

    `faq_howto`はQ1・Q4〜Q6のどれを指しているか本文だけでは絞り込めないため、単一項目を
    推測で返すのではなくメニュー全体(render_owner_faq_menu_message())を提示し、
    契約者自身に該当項目を選んでもらう。

    FAQ系3分類以外(`post_generation_request`・`other_needs_human`)を渡した場合は
    ValueError(呼び出し元は事前に分類値を判定済みの前提のため、フォールバックは
    設けない。この点はowner_faq_router.render_owner_faq_answer_message()の
    「未知のcodeはKeyError」という方針と同じ考え方)。
    """
    code = faq_intent_to_code(intent)
    if code is not None:
        return render_owner_faq_answer_message(code)
    if intent == "faq_howto":
        return render_owner_faq_menu_message()
    raise ValueError(f"FAQ系の分類値ではありません: {intent!r}")


# ---------------------------------------------------------------------------
# エスカレーション通知(design 3節)
# ---------------------------------------------------------------------------

CHATBOT_ESCALATION_NOTIFICATION_TEMPLATE = (
    "[コースセットパシャッと運営] 一次受付チャットボットからのエスカレーション\n"
    "\n"
    "以下の顧客からのメッセージが、FAQ・投稿文生成のいずれにも自動分類されませんでした。"
    "内容をご確認のうえ、必要に応じて個別にご対応ください。\n"
    "\n"
    "顧客ID: {user_id}\n"
    "メッセージ本文: {memo_text}"
)


def format_chatbot_escalation_notification_message(user_id: str, memo_text: str) -> str:
    """design 3節の通知文言に、顧客IDとメッセージ本文を埋め込んで組み立てる。"""
    return CHATBOT_ESCALATION_NOTIFICATION_TEMPLATE.format(user_id=user_id, memo_text=memo_text)


def send_chatbot_escalation_notification(
    user_id: str,
    memo_text: str,
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> bool:
    """design 3節「送信経路」本体。`other_needs_human`と判定されたメッセージ受信時に
    都度(日次バッチではなく即時)呼び出される想定。

    payment_suspension_owner_notification.pyの送信関数群とは異なり、本件は
    メッセージ単位のイベント通知であり冪等性のための送信済みフラグを持たない
    (design 3節「冪等性」: 同一顧客からの連続したother_needs_human判定はそれぞれ
    別メッセージとして都度通知する)。そのため戻り値も送信成功可否のbool一つのみとし、
    SendPaymentSuspensionOwnerNotificationsResultのような集計結果は持たない。

    送信失敗時はFalseを返すのみで、状態の書き込み・再試行キューへの登録は行わない
    (design時点で該当の永続化先が未設計のため。1メッセージ単位の即時通知という性質上、
    次回の同顧客からのメッセージで自然に再通知の機会が生まれる)。
    """
    text = format_chatbot_escalation_notification_message(user_id, memo_text)
    try:
        push_client.send_message(owner_line_user_id, text)
    except LinePushDeliveryError:
        return False
    return True


# design 3節「顧客への応答との関係」: other_needs_human判定時も無応答のまま放置せず、
# 顧客自身には定型の受付応答を返す(運営者宛のCHATBOT_ESCALATION_NOTIFICATION_TEMPLATEとは
# 別の、顧客向け文面)。
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
    """分類結果(`intent`)を受け取り、`_reply_with_retry()`等の既存の顧客への返信経路に
    そのまま渡せる最終的な返信文を1本にまとめる、分類「後」の配線の入口。

    これまで個別に検証済みだった以下3つのヘルパーを、design.mdが定める5分類それぞれの
    扱いに沿ってディスパッチするのみで、いずれのヘルパーの内部ロジックも変更しない。

    - `post_generation_request`: 投稿文生成本体(実LLM接続がオーナー承認待ちのため
      本モジュールの対象外)が組み立てた`generation_reply_text`を必須引数として受け取り、
      `append_faq_followup_hint()`を適用して返す。
    - `faq_pricing`/`faq_howto`/`faq_cancel_change`: `render_chatbot_faq_response_message()`
      をそのまま返す。
    - `other_needs_human`: `send_chatbot_escalation_notification()`で運営者へ即時通知した
      上で(`push_client`必須)、顧客には`OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT`を返す。
      通知の送信成否(戻り値のbool)はログ・監視目的で呼び出し元に判断を委ね、本関数は
      通知の成否にかかわらず同じ定型応答を顧客に返す(design 3節が「無応答のまま放置
      しない」ことを主眼としているため、通知送信の失敗を理由に顧客への応答を変えない)。
    """
    if intent == "post_generation_request":
        if generation_reply_text is None:
            raise ValueError(
                "post_generation_requestにはgeneration_reply_textが必須です"
            )
        return append_faq_followup_hint(generation_reply_text)
    if intent in _CHATBOT_INTENT_TO_FAQ_CODE or intent == "faq_howto":
        return render_chatbot_faq_response_message(intent)
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


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    for intent in ("faq_pricing", "faq_howto", "faq_cancel_change"):
        print(f"--- {intent} ---")
        print(render_chatbot_faq_response_message(intent))

    push = InMemoryLinePushClient()
    sent = send_chatbot_escalation_notification(
        "u1", "なんかいつもと違う気がするんですけど", push
    )
    print(f"escalation sent={sent}")
    print(f"push: {push.sent[-1]}")


if __name__ == "__main__":
    _demo()
