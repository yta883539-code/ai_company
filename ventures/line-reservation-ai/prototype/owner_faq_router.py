#!/usr/bin/env python3
"""
owner-faq-routing-design.mdを実行可能なコードに落とし込んだもの。

位置づけ: owner-operation-self-service-faq.mdのQ1〜Q6を、オーナーがLINEの
トークルームで「FAQ」→「Q1」のようにキーワードを送るだけで参照できるようにする
コマンド方式の実装。LLM呼び出し・LINE送信を一切持たない純粋関数のみで構成する
(呼び出し元はcloud_function_process_event.py `_maybe_handle_owner_faq_command()`)。
"""

from __future__ import annotations

from typing import Optional

# owner-operation-self-service-faq.md Q1〜Q6を、LINEメッセージ本文として送信するのに
# 適した簡潔な文面に整理し直したもの(内部設計ドキュメントのファイル名は含めない)。
_OWNER_FAQ_ITEMS: dict[str, tuple[str, str]] = {
    "Q1": (
        "メニュー内容や料金を変更したい",
        "「メニュー設定」ページから、ご自身でいつでも追加・編集・削除できます。"
        "運営者側の作業は不要です。料金の「表示する/しない」もここで切り替えられ、"
        "変更内容はお客様への自動応答にすぐ反映されます。",
    ),
    "Q2": (
        "営業時間・定休日を変更したい",
        "「営業情報設定」ページから変更できます。曜日ごとに営業時間を変える設定や"
        "休憩時間の追加もご自身で完結します。ただし曜日ごとに営業時間を変えている場合、"
        "お客様からの営業時間に関する質問は自動応答の対象外となり、運営者またはオーナー様への"
        "問い合わせとして転送されます。これは不具合ではなく仕様です。",
    ),
    "Q3": (
        "プランを変更・解約したい",
        "「プラン・お支払い状況」ページから、ご自身でプラン変更・解約の手続きができます。"
        "運営者側の手作業は不要です。",
    ),
    "Q4": (
        "無料トライアルはいつまで?延長できる?",
        "トライアル終了が近づくと自動でLINE通知が届きます。自動課金は行われないため、"
        "トライアル終了時点で何もしなければ利用が制限モードに移行するだけで、"
        "意図しない請求は発生しません。延長は現時点で仕組み化されておらず、"
        "個別相談が必要な場合は運営者へお問い合わせください。",
    ),
    "Q5": (
        "お客様への「確認して連絡します」という返答について",
        "これは不具合ではなく、店舗未登録の情報や個別事情の判断が必要な質問"
        "(医療・健康相談、料金交渉、クレーム等)、または曜日別営業時間を設定している"
        "店舗への営業時間質問などで意図的に発生する挙動です。転送された質問は"
        "オーナー様ご自身がお客様へ直接ご返信ください。運営者側での代理対応は行いません。",
    ),
    "Q6": (
        "複数スタッフでの予約枠管理をしたい(プロプラン)",
        "プロプランでは複数スタッフ枠の管理に対応しています。切り替えは"
        "「プラン・お支払い状況」ページから行えます。",
    ),
    "Q7": (
        "お客様への「LINEで予約できます」という告知文を作りたい",
        "トークルームで「告知文」と送信すると、店頭POP用の文言とSNS投稿用の文言の"
        "下書きをその場で生成します。運営者側の作業は不要です。店舗名が未登録の場合は"
        "「営業情報設定」ページでの登録を先にご案内します。",
    ),
}

# メニュー一覧に表示する順序(dictの挿入順に依存しないよう明示する)。
_OWNER_FAQ_ORDER = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7")

_MENU_TRIGGER_KEYWORD = "FAQ"


def is_owner_faq_menu_trigger(text: str) -> bool:
    """本文がFAQメニュー表示のトリガーキーワードと一致するか判定する。
    大文字小文字を区別せず、前後の空白は無視する。
    """
    return text.strip().upper() == _MENU_TRIGGER_KEYWORD


def match_owner_faq_item_code(text: str) -> Optional[str]:
    """本文が「Q1」〜「Q6」のいずれかと一致するか判定し、一致すれば正規化した
    コード(例: "Q1")を返す。一致しなければNone。大文字小文字は区別しない。
    """
    normalized = text.strip().upper()
    if normalized in _OWNER_FAQ_ITEMS:
        return normalized
    return None


def render_owner_faq_menu_message() -> str:
    """Q1〜Q6の見出し一覧を整形する。"""
    lines = ["【予約とれる君】オーナー向けFAQ", "", "番号を送信すると回答を表示します(例: Q1)。", ""]
    for code in _OWNER_FAQ_ORDER:
        label, _ = _OWNER_FAQ_ITEMS[code]
        lines.append(f"{code} {label}")
    return "\n".join(lines)


def render_owner_faq_answer_message(code: str) -> str:
    """指定コードの回答本文を整形する。未知のcodeはKeyError
    (呼び出し元はmatch_owner_faq_item_code()で事前に検証済みの値のみ渡す前提のため、
    フォールバックは設けない)。
    """
    label, answer = _OWNER_FAQ_ITEMS[code]
    return f"{code}. {label}\n\n{answer}\n\n他の質問を見る場合は「FAQ」と送信してください。"
