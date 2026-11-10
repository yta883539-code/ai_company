#!/usr/bin/env python3
"""
inquiry-form-http-entry-point-design.md(フェーズ109)で設計した、問い合わせフォームからの
実HTTPリクエストを受け取り、JSONパース〜`inquiry_form_intake.
handle_inquiry_form_submission()`への委譲〜Firestore `inquiry`コレクションへの書き込みまでを
行う受信処理の本体。

位置づけ:
- `stripe_webhook.receive_stripe_webhook()`と同じ「本体はbytes/dictのみを扱い実クラウド接続
  なしでテスト可能、`main(request)`だけが実`functions_framework`リクエストオブジェクトを扱う
  薄い配線」構成を踏襲する(薄い配線側は`cloud_function_submit_inquiry.py`)。
- design 2節: 本venture(event-komiguai-pasha)の`submit_inquiry`はブラウザから直接呼ばれる
  HTTPSトリガーであり、aircon-pasha版(GAS中継)のような共有シークレット検証は行わない。
- `created_at`(ドキュメント本体の文字列フィールド)は本関数が注入する。
  `inquiry_form_intake.handle_inquiry_form_submission()`自体は時刻取得を行わない設計
  (他venture共通の「時刻はDI」方針)のため、Cloud Run functionsのHTTPSトリガーに相当する
  本関数がその役割を担う。

設計の参照元: inquiry-form-http-entry-point-design.md、prototype/inquiry_form_intake.py
(フェーズ108)、prototype/stripe_webhook.py(フェーズ99)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from inquiry_collection_store import InquiryCollectionProtocol
from inquiry_form_intake import handle_inquiry_form_submission


@dataclass
class InquiryFormReceiveResult:
    """`receive_inquiry_form_submission()`の結果。design 3節のレスポンス形状
    (`{"ok": bool, "inquiry_id": str|null, "error": str|null}`)とHTTPステータスコードを
    両方保持する。"""

    status_code: int
    ok: bool
    inquiry_id: Optional[str] = None
    error: Optional[str] = None

    def to_json_body(self) -> str:
        return json.dumps(
            {"ok": self.ok, "inquiry_id": self.inquiry_id, "error": self.error}
        )


def receive_inquiry_form_submission(
    raw_body: bytes,
    *,
    collection: InquiryCollectionProtocol,
    idempotency_store=None,
    now: Optional[datetime] = None,
) -> InquiryFormReceiveResult:
    """design 3節・4節の処理順序(JSONパース → ペイロード検証・inquiry_id発行 →
    Firestore書き込み)を実装する。

    - JSON本文のパースに失敗、またはパース結果がdictでない場合は400を返す。
    - `inquiry_form_intake.handle_inquiry_form_submission()`が
      `status="missing_fields"`を返した場合、その`message`をそのまま`error`として400を返す。
      このときFirestoreへの書き込みは行わない。
    - `status="accepted"`の場合、`document`が`None`でない場合のみ`collection.add()`を呼ぶ
      (`None`の場合は同一`idempotency_key`での再送検知であり、先行リクエストが既に同内容で
      書き込み済みのため)。いずれの場合も200を返す(呼び出し元ブラウザにとっては
      「受付済み」という結果に差はないため、design 3節参照)。
    """
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return InquiryFormReceiveResult(
            status_code=400, ok=False, error="request body is not valid JSON"
        )

    if not isinstance(payload, dict):
        return InquiryFormReceiveResult(
            status_code=400, ok=False, error="request body must be a JSON object"
        )

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    result = handle_inquiry_form_submission(
        payload,
        resolved_now.isoformat(),
        idempotency_store=idempotency_store,
        now=resolved_now,
    )

    if result["status"] == "missing_fields":
        return InquiryFormReceiveResult(status_code=400, ok=False, error=result["message"])

    inquiry_id = result["inquiry_id"]
    document = result["document"]
    if document is not None:
        collection.add(inquiry_id, document)

    return InquiryFormReceiveResult(status_code=200, ok=True, inquiry_id=inquiry_id)


def _demo() -> None:
    from inquiry_collection_store import InMemoryInquiryCollection

    body = (
        '{"draft_id": "draft-demo", "customer_email": "demo@example.com", '
        '"category": "メール未着", "detail": "届きません"}'
    ).encode("utf-8")
    result = receive_inquiry_form_submission(body, collection=InMemoryInquiryCollection())
    print(f"status_code={result.status_code}, body={result.to_json_body()}")


if __name__ == "__main__":
    _demo()
