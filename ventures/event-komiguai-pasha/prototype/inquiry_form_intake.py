#!/usr/bin/env python3
"""
inquiry-handling-design.md(フェーズ15・4節)の残課題「問い合わせWebフォーム1画面・
Firestore `inquiry`コレクションへの書き込み自体の実装」(フェーズ87次回候補(2))に対応する。

位置づけ:
- inquiry_intake.py(フェーズ85)はFirestoreから読み出した`InquiryRecord`を受け取って
  返信方針を判定する「判定ロジック」であり、Webフォーム送信の生ペイロードをどう受け取り
  どう検証するかは対象外のままだった(同モジュールdocstring参照)。本モジュールは
  form_submission_intake.py(フェーズ2)と同じ位置づけで、そのフォーム受信側(入力検証・
  `inquiry/{inquiry_id}`ドキュメント組み立て)のみを担う。
- inquiry-handling-design.md 2節のフィールド定義(`draft_id`・`customer_email`・
  `category`・`detail`・`status`・`created_at`)に対応するドキュメントを組み立てるが、
  実Firestoreへの書き込み(`inquiry`コレクションへの実際のadd())・実タイムスタンプ取得は
  実GCP/Firestore作成(pending-approval.md記載)後の結線課題として残し、本モジュールは
  実クラウド接続なしで検証可能な「ペイロード→ドキュメント」変換のみを行う
  (form_submission_intake.handle_form_submissionと同じ「骨格」の考え方)。
- `category`はinquiry-handling-design.md 2節の4区分(メール未着/再送希望/返金希望/その他)
  に限定し、未知の値はinquiry_intake.build_inquiry_responseと同様にエラーとして拒否する
  (安全側: 想定外の区分をそのまま保存してしまうと3-1節の固定文言判定が効かなくなるため)。
- `created_at`は呼び出し側(実装時はCloud Run functionsのHTTPSトリガー)が渡す現在時刻の
  注入を前提とし、本モジュール自体は時刻取得を行わない(テスト容易性のため、
  他venture共通の「時刻はDI」方針を踏襲)。

設計の参照元: inquiry-handling-design.md(フェーズ15・2節・4節)、
prototype/inquiry_intake.py(フェーズ85)、prototype/form_submission_intake.py(フェーズ2)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from inquiry_intake import INQUIRY_CATEGORIES

# inquiry-handling-design.md 2節: draft_id・customer_email・categoryの3項目は必須
# (detailは自由記述のため未入力を許容する)。
REQUIRED_FORM_FIELDS = ("draft_id", "customer_email", "category")

FIELD_LABELS = {
    "draft_id": "お申込み時の受付番号(draft_id)",
    "customer_email": "ご連絡先メールアドレス",
    "category": "お問い合わせ区分",
}


@dataclass(frozen=True)
class InquiryFormInput:
    """Webフォーム送信の生入力(inquiry-handling-design.md 2節)。
    いずれも未入力はNoneで表す(parse_inquiry_form_payloadが空文字を正規化する)。"""

    draft_id: Optional[str] = None
    customer_email: Optional[str] = None
    category: Optional[str] = None
    detail: Optional[str] = None


def parse_inquiry_form_payload(raw_payload: dict) -> InquiryFormInput:
    """Webフォーム送信の生ペイロード(dict)をInquiryFormInputへ変換する。
    form_submission_intake.parse_form_payloadと同様、空文字・空白のみは未入力として扱う。"""

    def _clean(value: object) -> Optional[str]:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        return stripped if stripped else None

    return InquiryFormInput(
        draft_id=_clean(raw_payload.get("draft_id")),
        customer_email=_clean(raw_payload.get("customer_email")),
        category=_clean(raw_payload.get("category")),
        detail=_clean(raw_payload.get("detail")),
    )


def find_missing_required_fields(form: InquiryFormInput) -> list[str]:
    """REQUIRED_FORM_FIELDSのうち欠落している項目名を入力順に返す。欠落なしなら空リスト。"""

    missing = []
    for field in REQUIRED_FORM_FIELDS:
        if getattr(form, field) is None:
            missing.append(field)
    return missing


def build_missing_fields_message(missing_fields: list[str]) -> str:
    """欠落項目がある場合に画面へ表示する案内文(固定文言、AIは介さない)。
    form_submission_intake.build_insufficient_input_responseと同様、欠落項目の列挙のみ
    行い、推測で埋めない。"""

    if not missing_fields:
        raise ValueError("build_missing_fields_message requires at least one missing field")
    labels = "・".join(FIELD_LABELS[field] for field in missing_fields)
    return f"{labels}が未入力です。入力のうえ再度送信してください。"


def build_inquiry_document(form: InquiryFormInput, created_at: str) -> dict:
    """検証済みのInquiryFormInputから、inquiry-handling-design.md 2節の
    `inquiry/{inquiry_id}`ドキュメント相当のdictを組み立てる。

    引数:
    - created_at: 呼び出し側が注入する受付時刻(本モジュールは時刻取得を行わない)。

    必須項目の欠落・categoryが4区分外の場合はValueErrorを送出する(呼び出し側は
    find_missing_required_fieldsで事前にチェックした上で呼ぶ想定)。
    実際のFirestore `inquiry`コレクションへのadd()は本モジュールの対象外。
    """

    missing = find_missing_required_fields(form)
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    if form.category not in INQUIRY_CATEGORIES:
        raise ValueError(f"unknown inquiry category: {form.category}")

    return {
        "draft_id": form.draft_id,
        "customer_email": form.customer_email,
        "category": form.category,
        "detail": form.detail,
        "status": "received",
        "created_at": created_at,
        "resolvedAt": None,
    }


def handle_inquiry_form_submission(raw_payload: dict, created_at: str) -> dict:
    """Webフォーム送信の受信処理エントリーポイント(骨格)。
    form_submission_intake.handle_form_submissionと対になる、問い合わせフォーム側の入口。

    戻り値は次のいずれか:
    - 欠落項目がある場合: {"status": "missing_fields", "message": <案内文>}
      (この場合、呼び出し側はFirestoreへの書き込みを行わない)
    - 欠落なしの場合: {"status": "accepted", "document": <build_inquiry_documentの戻り値>}
      (呼び出し側がこのdocumentを実際に`inquiry`コレクションへadd()する想定。
      本モジュール自体はFirestore接続を行わない)
    """

    form = parse_inquiry_form_payload(raw_payload)
    missing = find_missing_required_fields(form)
    if missing:
        return {"status": "missing_fields", "message": build_missing_fields_message(missing)}
    return {"status": "accepted", "document": build_inquiry_document(form, created_at)}
