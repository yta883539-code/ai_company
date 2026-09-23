#!/usr/bin/env python3
"""
chatbot-intent-classification-design.md(フェーズ167)・chatbot-intent-classification-
llm-prompt-draft.md(フェーズ168)「残課題」に残っていた、(1) faq_intent_to_code()
マッピング層、(2) エスカレーション通知送信ヘルパー、(3) memo_processing_request判定時への
一言追加、を実行可能なコードに落とし込んだもの。

course-set-pashaのprototype/chatbot_intent_router.py(フェーズ236)と同じ設計方針
(分類結果が既に得られている前提で、分類「後」の配線のみを検証可能にする)を踏襲するが、
本ventureは6分類(course-set-pashaは5分類、複数職人プラン特有のfaq_plan/faq_howtoの
切り分けが異なる)である点、faq_contractor_transfer_overview(Q7相当)という本venture
固有のカテゴリを持つ点が異なる。

位置づけ: 実LLMによる意図分類自体(自由入力テキスト→6分類への分類)は本モジュールの対象外
(引き続き実LLM呼び出しを伴う承認待ち領域)。本モジュールは、分類結果(文字列)が既に得られて
いる前提での配線のみを扱う(payment_suspension_owner_notification.pyと同じ位置づけ)。

設計の参照元: chatbot-intent-classification-design.md、chatbot-intent-classification-
llm-prompt-draft.md
"""

from __future__ import annotations

from typing import Optional

from owner_faq_router import render_owner_faq_answer_message, render_owner_faq_menu_message
from payment_suspension_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER
from subscription_cancellation_notification import LinePushClient, LinePushDeliveryError

# design(chatbot-intent-classification-design.md)1節: LLMへの分類指示の出力値として
# 採用する6分類。
CHATBOT_INTENT_VALUES = frozenset(
    {
        "memo_processing_request",
        "faq_plan",
        "faq_howto",
        "faq_cancel",
        "faq_contractor_transfer_overview",
        "other_needs_human",
    }
)

# design 1節: faq_cancel→Q3、faq_contractor_transfer_overview→Q7は
# owner-operation-self-service-faq.mdの項目と1対1で対応する。faq_plan
# (Q1・Q5・Q6相当)・faq_howto(Q2・Q4・Q8・Q9相当)はいずれも複数項目にまたがり
# 1対1に定まらないため、このマッピングには含めず、
# render_chatbot_faq_response_message()側でメニュー全体を提示する。
_CHATBOT_INTENT_TO_FAQ_CODE: dict[str, str] = {
    "faq_cancel": "Q3",
    "faq_contractor_transfer_overview": "Q7",
}

_AMBIGUOUS_FAQ_INTENTS = frozenset({"faq_plan", "faq_howto"})


def faq_intent_to_code(intent: str) -> Optional[str]:
    """FAQ系の分類値のうち、owner_faq_router.pyの単一の項目コードへ1対1で変換できる
    もの(`faq_cancel`→Q3、`faq_contractor_transfer_overview`→Q7)のみ変換する。
    `faq_plan`・`faq_howto`は複数項目にまたがり単一コードに定まらないためNoneを返す
    (呼び出し元はrender_chatbot_faq_response_message()を使うこと)。FAQ系以外の
    分類値(`memo_processing_request`・`other_needs_human`)を渡した場合もNoneを返す。
    """
    return _CHATBOT_INTENT_TO_FAQ_CODE.get(intent)


def render_chatbot_faq_response_message(intent: str) -> str:
    """design 1節に基づき、FAQ系4分類(`faq_plan`/`faq_howto`/`faq_cancel`/
    `faq_contractor_transfer_overview`)に対する回答文言を組み立てる。回答文言自体の
    二重管理を避けるため、既存のowner_faq_router.pyの定型回答関数をそのまま呼び出す。

    `faq_plan`・`faq_howto`はどのQ番号を指しているか本文だけでは絞り込めないため、
    単一項目を推測で返すのではなくメニュー全体(render_owner_faq_menu_message())を
    提示し、契約者自身に該当項目を選んでもらう(course-set-pashaのfaq_howto扱いと
    同じ考え方)。

    FAQ系4分類以外(`memo_processing_request`・`other_needs_human`)を渡した場合は
    ValueError(呼び出し元は事前に分類値を判定済みの前提のため、フォールバックは
    設けない)。
    """
    code = faq_intent_to_code(intent)
    if code is not None:
        return render_owner_faq_answer_message(code)
    if intent in _AMBIGUOUS_FAQ_INTENTS:
        return render_owner_faq_menu_message()
    raise ValueError(f"FAQ系の分類値ではありません: {intent!r}")


# chatbot-intent-classification-llm-prompt-draft.md「設計上の要点4: 想定される
# 誤判定パターン(未検証)」節: 判定順位1により、受注メモとFAQ質問(プラン等)が同時に
# 含まれる複合入力はmemo_processing_requestに判定され、FAQ部分への回答が欠落する。
# course-set-pasha・aircon-pashaが採用した運用回避(生成結果の返答文末尾への一言追加)を
# 本venture向けにも適用する。
MEMO_PROCESSING_FAQ_FOLLOWUP_HINT = (
    "\n\n※プランや使い方、契約者交代など他にご質問がありましたら、続けてメッセージを"
    "お送りください。"
)


def append_faq_followup_hint(generation_reply_text: str) -> str:
    """memo_processing_request判定時の返答文(受注内容整理・納品案内・お手入れ案内
    生成結果)の末尾に、上記の運用回避として一言を追加する。

    判定順位1により複合入力(受注メモ+FAQ質問)がmemo_processing_requestに判定され
    FAQ部分の回答が欠落するケースを、質問を検知せず常に一言を添えることで回避する
    (どの入力がFAQ相当を含んでいたかをこの関数側で判定することはしない。判定を試みると
    「受注メモらしき内容が少しでも含まれればmemo_processing_requestを最優先する」という
    フェイルセーフの単純さが崩れるため、常時付与する設計とした。course-set-pashaの
    append_faq_followup_hint()と同じ考え方)。

    呼び出し元は受注内容整理・納品案内・お手入れ案内の生成本体(実LLM接続がオーナー承認
    待ちのため未実装)の返答文組み立て処理を想定しており、本関数自体は文字列の末尾追加
    のみを行う純粋関数。
    """
    return generation_reply_text + MEMO_PROCESSING_FAQ_FOLLOWUP_HINT


# ---------------------------------------------------------------------------
# エスカレーション通知(chatbot-intent-classification-design.md 3節)
# ---------------------------------------------------------------------------

CHATBOT_ESCALATION_NOTIFICATION_TEMPLATE = (
    "[鞍パシャッと運営] 一次受付チャットボットからのエスカレーション\n"
    "\n"
    "以下の職人様からのメッセージが、FAQ・メモ処理のいずれにも自動分類されませんでした"
    "(修理可否等の専門的判断への言及を含む可能性があります)。内容をご確認のうえ、"
    "必要に応じて個別にご対応ください。\n"
    "\n"
    "職人ID: {user_id}\n"
    "メッセージ本文: {memo_text}"
)


def format_chatbot_escalation_notification_message(user_id: str, memo_text: str) -> str:
    """design 3節の通知文言(本venture固有の「修理可否等の専門的判断への言及を含む
    可能性があります」の一文を含む)に、職人IDとメッセージ本文を埋め込んで組み立てる。"""
    return CHATBOT_ESCALATION_NOTIFICATION_TEMPLATE.format(user_id=user_id, memo_text=memo_text)


def send_chatbot_escalation_notification(
    user_id: str,
    memo_text: str,
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> bool:
    """design 3節「送信経路」本体。`other_needs_human`と判定されたメッセージ受信時に
    都度(日次バッチではなく即時)呼び出される想定。

    design 3節「冪等性」: 1メッセージにつき1通知、送信済みフラグによる重複排除の仕組みは
    不要(course-set-pashaと同じ判断)。そのため戻り値も送信成功可否のbool一つのみ。

    送信失敗時はFalseを返すのみで、状態の書き込み・再試行キューへの登録は行わない
    (design時点で該当の永続化先が未設計のため。1メッセージ単位の即時通知という性質上、
    次回の同職人からのメッセージで自然に再通知の機会が生まれる)。
    """
    text = format_chatbot_escalation_notification_message(user_id, memo_text)
    try:
        push_client.send_message(owner_line_user_id, text)
    except LinePushDeliveryError:
        return False
    return True


# design 3節「顧客への応答との関係」: other_needs_human判定時も無応答のまま放置せず、
# 職人自身には定型の受付応答を返す(運営者宛のCHATBOT_ESCALATION_NOTIFICATION_TEMPLATEとは
# 別の、職人向け文面)。
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
    """分類結果(`intent`)を受け取り、既存の顧客への返信経路にそのまま渡せる最終的な
    返信文を1本にまとめる、分類「後」の配線の入口。

    - `memo_processing_request`: 受注内容整理・納品案内・お手入れ案内の生成本体(実LLM
      接続がオーナー承認待ちのため本モジュールの対象外)が組み立てた
      `generation_reply_text`を必須引数として受け取り、`append_faq_followup_hint()`を
      適用して返す。
    - `faq_plan`/`faq_howto`/`faq_cancel`/`faq_contractor_transfer_overview`:
      `render_chatbot_faq_response_message()`をそのまま返す。
    - `other_needs_human`: `send_chatbot_escalation_notification()`で運営者へ即時通知した
      上で(`push_client`必須)、職人には`OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT`を返す。
      通知の送信成否(戻り値のbool)はログ・監視目的で呼び出し元に判断を委ね、本関数は
      通知の成否にかかわらず同じ定型応答を職人に返す(design 3節が「無応答のまま放置
      しない」ことを主眼としているため、通知送信の失敗を理由に職人への応答を変えない)。

    なお本関数は、chatbot-intent-classification-design.md 0節が定める「解約意図検知・
    契約者譲渡意図検知は本関数より常に手前で実行する」分岐順序が既に守られている前提で
    呼び出される(いずれかが検知された場合、呼び出し元は本関数を呼ばず既存の状態遷移
    処理にそのまま委ねる)。本関数自体はその順序を検証しない。
    """
    if intent == "memo_processing_request":
        if generation_reply_text is None:
            raise ValueError(
                "memo_processing_requestにはgeneration_reply_textが必須です"
            )
        return append_faq_followup_hint(generation_reply_text)
    if intent in _CHATBOT_INTENT_TO_FAQ_CODE or intent in _AMBIGUOUS_FAQ_INTENTS:
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
    from subscription_cancellation_notification import InMemoryLinePushClient

    for intent in ("faq_plan", "faq_howto", "faq_cancel", "faq_contractor_transfer_overview"):
        print(f"--- {intent} ---")
        print(render_chatbot_faq_response_message(intent))

    push = InMemoryLinePushClient()
    sent = send_chatbot_escalation_notification(
        "u1", "この鞍のひび割れ、直りますかね", push
    )
    print(f"escalation sent={sent}")
    print(f"push: {push.sent[-1]}")


if __name__ == "__main__":
    _demo()
