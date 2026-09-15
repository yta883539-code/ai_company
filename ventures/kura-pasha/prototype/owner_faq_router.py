"""契約者(工房主)向けセルフサービスFAQのLINEトークルーム内導線(フェーズ126)。

owner-operation-self-service-faq.md(フェーズ125)「次のステップ候補」、および
owner-faq-routing-design.md(本フェーズ新規作成)で採用したコマンド方式の実装。
line-reservation-aiのprototype/owner_faq_router.py(フェーズ続き233)と同じ設計
(LLM呼び出し・LINE送信・通知ログ記録のいずれも行わない純粋関数)を踏襲するが、
本venture固有のQ1〜Q8(owner-operation-self-service-faq.md)を対象とする点が異なる。

呼び出し元(cloud_function_webhook.pyのprocess_message_event())は、`user_id`が
`workshop_store.get_contractor_user_id(workshop_id)`と一致する場合のみ本モジュールの
関数を使った分岐を評価する。共同利用者(複数職人プランのメンバー)や一般の来店客に
相当する層は存在しない本venture固有の事情により、判定対象は契約者本人のみとなる
(owner-faq-routing-design.md 2節参照)。
"""

from __future__ import annotations

from typing import Optional

_FAQ_MENU_TRIGGER = "faq"

_FAQ_HEADINGS = {
    "Q1": "料金プランを変更したい(アップグレード/ダウングレード)",
    "Q2": "無料トライアルはいつまで?延長できる?",
    "Q3": "解約したい/解約後の再開はどうなる?",
    "Q4": "複数職人で共同利用したい/解約操作は誰が行える?",
    "Q5": "月間生成回数の上限に達した/超過分の課金はどうなる?",
    "Q6": "複数職人プランからダウングレードしたら、他の職人は使えなくなる?",
    "Q7": "工房の契約者(親方・代表)を交代したい(事業承継)",
    "Q8": "生成された受注内容整理・納品案内・お手入れ案内の内容がイメージと違う",
}

_FAQ_ANSWERS = {
    "Q1": (
        "プラン変更はカスタマーポータルから契約者様ご自身で行えます。変更後のプランは"
        "自動的に反映されますので、運営者側での手続きは不要です。複数職人プランからの"
        "ダウングレードについてはQ6もご確認ください。"
    ),
    "Q2": (
        "無料トライアルは「工房作成(契約・LINE連携完了)から30日間」または"
        "「最初の生成成功1回まで」のいずれか早い方までです。クレジットカード登録なしで"
        "開始できるため、その間に自動課金が発生することはありません。"
    ),
    "Q3": (
        "解約もカスタマーポータルから契約者様ご自身で手続きできます。解約は現在の"
        "請求期間終了時点で有効になり、それまでは通常通りご利用いただけます。複数職人"
        "プランの解約手続きは契約者様のみ行えます。LINEのブロックだけでは解約に"
        "ならない点にご注意ください。"
    ),
    "Q4": (
        "複数職人プランでは最大5名まで1つの工房を共同利用できます。ただし解約・"
        "ダウングレード操作は契約者様ご本人のみ行える仕組みです。共同利用者の方から"
        "解約等のご希望があった場合は、恐れ入りますが契約者様にご確認をお願いします。"
    ),
    "Q5": (
        "月間の生成回数上限に達しても生成自体は止まりません。上限超過分は従量課金"
        "(プランごとに150〜250円/回)で継続してご利用いただけます。"
    ),
    "Q6": (
        "複数職人プランから1名のみのプランへダウングレードした場合、メンバーの縮小は"
        "即時ではなく次回請求サイクル開始まで猶予されます。猶予期間中に継続利用される"
        "メンバーをご連絡いただかない場合、次回請求サイクル開始後は契約者様のみが"
        "ご利用いただける状態になります。"
    ),
    "Q7": (
        "複数職人プランに限り、工房に参加済みの職人へ契約者を交代できます。トーク"
        "ルームで「契約者を交代したい、後継ぎは◯◯」のようにお送りいただくと、"
        "対象者の確認後、契約者様からの再確認を経て交代が確定します(誤操作防止のため"
        "即時には反映されません)。1人のみのプランでは譲渡先が存在しないためご利用"
        "いただけません。"
    ),
    "Q8": (
        "採寸・型紙作成・革選定・縫製・仕上げ等の専門的な制作作業・判断は職人様ご本人が"
        "行っていただく前提です。本サービスは受注内容整理・納品案内・お手入れ案内の"
        "下書き作成支援にとどまります。送信するメモに馬体のサイズ・鞍の型・革の種類・"
        "金具仕様・用途・納期等を具体的にお書きいただくと、生成内容の精度が上がり"
        "やすくなります。"
    ),
}


def is_owner_faq_menu_trigger(text: Optional[str]) -> bool:
    """本文が「FAQ」トリガー(大文字小文字を区別しない、前後空白は無視)かどうか。"""
    if text is None:
        return False
    return text.strip().lower() == _FAQ_MENU_TRIGGER


def match_owner_faq_item_code(text: Optional[str]) -> Optional[str]:
    """本文が「Q1」〜「Q8」(大文字小文字を区別しない)に一致すれば正規化したコードを返す。"""
    if text is None:
        return None
    normalized = text.strip().upper()
    if normalized in _FAQ_HEADINGS:
        return normalized
    return None


def render_owner_faq_menu_message() -> str:
    """Q1〜Q8の見出し一覧を整形する。"""
    lines = ["よくあるご質問(番号を送信すると回答をお送りします)"]
    for code in sorted(_FAQ_HEADINGS):
        lines.append(f"{code}. {_FAQ_HEADINGS[code]}")
    return "\n".join(lines)


def render_owner_faq_answer_message(code: str) -> str:
    """指定コードの回答本文を整形する。未知のcodeはKeyError(呼び出し元は
    match_owner_faq_item_code()で事前検証済みの値のみ渡す前提のため、フォールバックは
    設けない、line-reservation-aiと同じ方針)。"""
    return f"{code}. {_FAQ_HEADINGS[code]}\n{_FAQ_ANSWERS[code]}"
