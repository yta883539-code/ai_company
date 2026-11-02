#!/usr/bin/env python3
"""
inquiry-handling-design.md(フェーズ15・3-1節フェーズ83)で確定した、問い合わせ3類型
(メール未着・TTL失効前再送/TTL失効後再送/品質不満返金)への対応方針をコード化する処理の骨格。
README.md次回候補(フェーズ84)「問い合わせフォーム自体の実装後、類型1・2の固定文言が
機械チェック対象に正しく組み込まれるかを検証」に向け、フォーム実装そのものより先に、
受け付けた問い合わせ(category・draft_id等)から類型を判定し返信文/オーナー向け要約を
組み立てる判定ロジック自体を先行して実装する(フォーム1画面・Firestore書き込みの実装自体は
inquiry-handling-design.md 4節の「次回以降の課題」のまま残す)。

位置づけ:
- inquiry-handling-design.md 2節の問い合わせ区分(メール未着/再送希望/返金希望/その他)を
  受け取り、`one_time_draft`の存在有無(TTL失効前か後か、呼び出し側がFirestore照会して
  渡す)から3-1節の類型1〜3のいずれかを判定する。
- 類型1・2はoperational_message_templates.TEMPLATESの固定文言(inquiry_reply_resend_
  before_ttl・inquiry_reply_resend_after_ttl)をそのまま使い、都度のAI生成に委ねる範囲
  (類型1のresult_page_url差し込みのみ)に限定する(3-1節の方針どおり、文面自体はAIに
  都度書き起こさせない)。
- 類型3(品質不満による返金希望)は顧客向け返信文を生成せず、問い合わせ内容と(渡されれば)
  生成結果を並記した「オーナー判断用の要約」のみを返す(2節3項・3-1節3の方針どおり)。
- 「その他」区分はinquiry-handling-design.mdのいずれの類型にも明示的に対応付けられていない
  (設計文書が定義する3類型は「メール未着/再送希望」「返金希望」のみを対象としており、
  「その他」の扱いは本設計の対象外のまま残されている)。本モジュールでは安全側に倒し、
  固定文言による自動返信は行わず、オーナーへの手動確認を要求する扱いとする。この扱い自体の
  設計文書への反映(inquiry-handling-design.mdへの明記)は次回候補として残す。
- 実際のメール送信・Stripe返金実行はいずれも外部サービスへの実行アクションのため、
  pending-approval.mdの既存方針どおり本モジュールは下書き・要約の組み立てまでに留め、
  実行自体は行わない。

設計の参照元: inquiry-handling-design.md(フェーズ15・61・83)、
prototype/operational_message_templates.py(フェーズ26)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from operational_message_templates import TEMPLATES

# inquiry-handling-design.md 2節の問い合わせ区分(4区分)。
INQUIRY_CATEGORIES = ("メール未着", "再送希望", "返金希望", "その他")

# inquiry-handling-design.md 3-1節で固定文言とした2類型(都度のAI生成は行わない)。
_RESEND_CATEGORIES = ("メール未着", "再送希望")


@dataclass(frozen=True)
class InquiryRecord:
    """inquiry-handling-design.md 2節のFirestore `inquiry/{inquiry_id}`相当の入力。
    実際のFirestoreドキュメント全体ではなく、本判定ロジックが必要とする項目のみを持つ。"""

    draft_id: str
    category: str
    detail: Optional[str] = None


def build_inquiry_response(
    inquiry: InquiryRecord,
    draft_exists: bool,
    result_page_url: Optional[str] = None,
    generation_result_text: Optional[str] = None,
) -> dict:
    """問い合わせ内容から類型を判定し、返信方針を組み立てる。

    引数:
    - draft_exists: 呼び出し側が`one_time_draft/{draft_id}`をFirestoreで照会した結果
      (TTL失効前でドキュメントが存在するか)。本モジュール自体はFirestore接続を行わない。
    - result_page_url: 類型1(TTL失効前再送)のときのみ必須。固定文言への差し込み用。
    - generation_result_text: 類型3(品質不満返金)のとき、並記する生成結果があれば渡す
      (3-1節3「問い合わせ内容と当該draft_idの生成結果を並べて提示する」の並記部分)。
      呼び出し側が生成結果を未取得の場合はNoneのままでよく、その場合は要約内で
      draft_idを示すのみに留める。

    戻り値は常に次のキーを持つdict:
    - response_type: "resend_before_ttl" / "resend_after_ttl" / "quality_refund_request" /
      "uncategorized"
    - customer_reply: 顧客にそのまま送付できる固定文言(類型1・2のみ非None)
    - owner_summary: オーナー判断用の要約(類型3・「その他」のみ非None)
    - requires_owner_action: 実際の送信・返金実行前にオーナーが行うべきこと
    """

    if inquiry.category not in INQUIRY_CATEGORIES:
        raise ValueError(f"unknown inquiry category: {inquiry.category}")

    if inquiry.category in _RESEND_CATEGORIES:
        return _build_resend_response(inquiry, draft_exists, result_page_url)

    if inquiry.category == "返金希望":
        return {
            "response_type": "quality_refund_request",
            "customer_reply": None,
            "owner_summary": _build_owner_summary(inquiry, generation_result_text),
            "requires_owner_action": "owner_judgment_required",
        }

    # "その他": inquiry-handling-design.mdが類型を定義していない区分(モジュール docstring参照)。
    return {
        "response_type": "uncategorized",
        "customer_reply": None,
        "owner_summary": _build_owner_summary(inquiry, generation_result_text),
        "requires_owner_action": "manual_review_required",
    }


def _build_resend_response(
    inquiry: InquiryRecord, draft_exists: bool, result_page_url: Optional[str]
) -> dict:
    if draft_exists:
        if not result_page_url:
            raise ValueError(
                "result_page_url is required when draft_exists is True "
                "(resend_before_ttl template needs it)"
            )
        return {
            "response_type": "resend_before_ttl",
            "customer_reply": TEMPLATES["inquiry_reply_resend_before_ttl"].format(
                result_page_url=result_page_url
            ),
            "owner_summary": None,
            "requires_owner_action": "send_after_confirmation",
        }

    return {
        "response_type": "resend_after_ttl",
        "customer_reply": TEMPLATES["inquiry_reply_resend_after_ttl"],
        "owner_summary": None,
        "requires_owner_action": "send_after_confirmation",
    }


def _build_owner_summary(inquiry: InquiryRecord, generation_result_text: Optional[str]) -> str:
    detail = inquiry.detail or "(自由記述欄は未入力)"
    summary = (
        f"draft_id={inquiry.draft_id} の問い合わせ(区分: {inquiry.category})。\n"
        f"問い合わせ内容: {detail}"
    )
    if generation_result_text:
        summary += f"\n当該draft_idの生成結果: {generation_result_text}"
    else:
        summary += "\n当該draft_idの生成結果は未取得のため、オーナーが別途確認してください。"
    summary += "\n対応方針(返金可否・個別返信の有無等)はオーナーが個別に判断してください。"
    return summary
