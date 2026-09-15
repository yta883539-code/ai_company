#!/usr/bin/env python3
"""
owner-faq-routing-design.mdを実行可能なコードに落とし込んだもの。

位置づけ: owner-operation-self-service-faq.mdのQ1〜Q6を、契約者(ジムオーナー・
セッター)がLINEのトークルームで「FAQ」→「Q1」のようにキーワードを送るだけで
参照できるようにするコマンド方式の実装。LLM呼び出し・LINE送信・状態参照を一切
持たない純粋関数のみで構成する(line-reservation-ai・kura-pashaの
owner_faq_router.pyと同一のインターフェース)。呼び出し元は
cloud_function_webhook.py `process_memo_event()`。
"""

from __future__ import annotations

from typing import Optional

# owner-operation-self-service-faq.md Q1〜Q6を、LINEメッセージ本文として送信するのに
# 適した簡潔な文面に整理し直したもの(内部設計ドキュメントのファイル名は含めない)。
_OWNER_FAQ_ITEMS: dict[str, tuple[str, str]] = {
    "Q1": (
        "料金プランを変更したい(アップグレード/ダウングレード)",
        "トークルームで「プランを変更したい」とお伝えいただくと、お手続きページの"
        "リンクをご案内します。プラン変更はご自身で完結でき、運営者側の作業は"
        "不要です。変更後のプラン反映も自動で行われます。",
    ),
    "Q2": (
        "無料トライアルはいつまで?延長できる?",
        "初回の投稿文生成成功から14日間、または生成5回到達のいずれか早い方まで"
        "無料です。トライアル終了が近づくとLINE通知が届き、自動課金は行われません。"
        "終了時点で有料プランへご登録がなければ生成が一時停止するだけで、意図しない"
        "請求は発生しません。延長は現時点で仕組み化されておらず、個別相談が必要な"
        "場合は運営者へお問い合わせください。",
    ),
    "Q3": (
        "解約したい/解約後の再開はどうなる?",
        "トークルームで「解約したい」とお伝えいただくと、お手続きページのリンクを"
        "ご案内します。解約は現在の請求期間終了時点で有効になり、それまでは通常通り"
        "ご利用いただけます。LINEをブロックしただけでは解約になりませんのでご注意"
        "ください。",
    ),
    "Q4": (
        "複数セッターでの共同利用をしたい(セッター複数プラン)",
        "複数ジムを掛け持ちする場合は、オンボーディング時に複数ジム・エリアを"
        "ご登録いただくだけでご利用いただけます。複数の異なるスタッフで同一契約の"
        "利用枠を共有したい場合は運用方法が異なりますので、運営者へご相談ください。",
    ),
    "Q5": (
        "月間生成回数の上限に達した/超過分の課金はどうなる?",
        "上限到達時に生成が止まることはなく、プランごとの単価(120〜150円/回)での"
        "従量課金で引き続きご利用いただけます。新規オープンや大型大会前など一時的に"
        "生成回数が増える場面でもサービスが使えなくなることはありません。上限が"
        "近づくとその旨を通知いたします。",
    ),
    "Q6": (
        "生成された投稿文・告知文の内容がイメージと違う",
        "課題入れ替え内容やグレーディングの最終判断はセッター様ご自身の確認事項と"
        "なります。送信するメモの粒度(エリア・テープ色・難易度帯・本数・ムーブの"
        "特徴を具体的に書く)を調整いただくと、生成内容の精度が上がりやすくなります。"
        "個別の生成結果の修正代行は運営者側では行っておりません。",
    ),
}

# メニュー一覧に表示する順序(dictの挿入順に依存しないよう明示する)。
_OWNER_FAQ_ORDER = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")

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
    lines = ["【コースセットパシャッと】よくあるご質問", "", "番号を送信すると回答を表示します(例: Q1)。", ""]
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
