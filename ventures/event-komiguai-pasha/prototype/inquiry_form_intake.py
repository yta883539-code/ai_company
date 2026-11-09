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

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

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


def _default_inquiry_id_factory() -> str:
    # checkout_session_creation._default_draft_id_factory(フェーズ53)と同じUUID4方式。
    # inquiry_idは`inquiry/{inquiry_id}`のドキュメントIDであり、ドキュメント内の
    # `draft_id`フィールド(問い合わせ対象の受付番号)とは別物。
    return str(uuid.uuid4())


def handle_inquiry_form_submission(
    raw_payload: dict,
    created_at: str,
    *,
    idempotency_store=None,
    now: Optional[datetime] = None,
    inquiry_id_factory: Callable[[], str] = _default_inquiry_id_factory,
) -> dict:
    """Webフォーム送信の受信処理エントリーポイント(骨格)。
    form_submission_intake.handle_form_submission・checkout_session_creation.
    create_checkout_session_for_event_memo(フェーズ107)と対になる、問い合わせフォーム側の入口。

    `idempotency_store`(idempotency_key_index_store.IdempotencyKeyIndexStoreProtocol相当、
    省略可)を渡した場合、`raw_payload["idempotency_key"]`をキーに`collection="inquiry"`で
    `reserve_or_get()`を呼ぶ(フェーズ107の`one_time_draft`側と同型の衝突検知)。同一
    `idempotency_key`での再送(二重クリック・ネットワーク再試行等)が検知された場合は
    既存の`inquiry_id`を返し、`document`はNoneとする(=呼び出し側はFirestoreへの
    add()を行わない。先行リクエストが既に同内容で書き込み済みのため)。`idempotency_store`
    省略時・`idempotency_key`未送信時は従来どおり常に新規`inquiry_id`を発行する(後方互換)。
    `now`はidempotency_key_index側の`created_at`(datetime型、design.md 3節)用の受付時刻で、
    ドキュメント本体の`created_at`(呼び出し側がフォーマット済みの文字列で渡す引数、既存どおり)
    とは別物(フェーズ107のcheckout_session_creation.resolved_nowと同じ役割分担)。
    `idempotency_store`利用時に省略した場合は`datetime.now(timezone.utc)`を用いる。

    戻り値は次のいずれか:
    - 欠落項目がある場合: {"status": "missing_fields", "message": <案内文>}
      (この場合、呼び出し側はFirestoreへの書き込みを行わない)
    - 欠落なしの場合: {"status": "accepted", "inquiry_id": <str>,
      "document": <build_inquiry_documentの戻り値> または None(重複検知時)}
      (呼び出し側はdocumentがNoneでない場合のみ、`inquiry/{inquiry_id}`へadd()する想定。
      本モジュール自体はFirestore接続を行わない)
    """

    form = parse_inquiry_form_payload(raw_payload)
    missing = find_missing_required_fields(form)
    if missing:
        return {"status": "missing_fields", "message": build_missing_fields_message(missing)}

    candidate_inquiry_id = inquiry_id_factory()
    idempotency_key = raw_payload.get("idempotency_key")
    inquiry_id = candidate_inquiry_id
    if idempotency_store is not None and idempotency_key:
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        inquiry_id = idempotency_store.reserve_or_get(
            idempotency_key,
            collection="inquiry",
            document_id=candidate_inquiry_id,
            created_at=resolved_now,
        )

    if inquiry_id != candidate_inquiry_id:
        # 既存のidempotency_keyが既にinquiry_idを確保済み(フェーズ107の
        # draft_id != candidate_draft_idと同型)。先行リクエストが同内容で書き込み済み
        # のはずなので、今回はドキュメントを再構築せずdocument=Noneを返す。
        return {"status": "accepted", "inquiry_id": inquiry_id, "document": None}

    document = build_inquiry_document(form, created_at)
    return {"status": "accepted", "inquiry_id": inquiry_id, "document": document}
