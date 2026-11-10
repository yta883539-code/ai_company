#!/usr/bin/env python3
"""
submit-event-form-http-entry-point-design.md(フェーズ110)で設計した、Webフォームからの
実HTTPリクエストを受け取り、JSONパース〜`checkout_session_creation.
create_checkout_session_for_event_memo()`への委譲〜HTTPレスポンス整形までを行う
受信処理の本体。

位置づけ:
- `inquiry_form_http_entry.receive_inquiry_form_submission()`と同じ「本体はbytes/dictの
  みを扱い実クラウド接続なしでテスト可能、`main(request)`だけが実`functions_framework`
  リクエストオブジェクトを扱う薄い配線」構成を踏襲する(薄い配線側は
  `cloud_function_submit_event_form.py`)。
- design 2節: `outcome="insufficient_input"`はクライアント側のリクエスト不備ではなく
  正常系の分岐として扱うため、`inquiry_form_http_entry.py`のmissing_fields応答(400)とは
  異なり200で返す。

設計の参照元: submit-event-form-http-entry-point-design.md、
prototype/checkout_session_creation.py(フェーズ67〜105)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from checkout_session_creation import (
    StripeCheckoutSessionClientProtocol,
    create_checkout_session_for_event_memo,
)


@dataclass
class EventFormReceiveResult:
    """`receive_event_form_submission()`の結果。design 2節のレスポンス形状
    (checkout_session_created: `{"ok": true, "draft_id": str, "checkout_url": str}`、
    insufficient_input: schema/output.schema.jsonの`status="insufficient_input"`応答
    そのもの、エラー: `{"ok": false, "error": str}`)とHTTPステータスコードを両方保持する。"""

    status_code: int
    body: dict

    def to_json_body(self) -> str:
        return json.dumps(self.body)


def receive_event_form_submission(
    raw_body: bytes,
    *,
    draft_store,
    checkout_client: StripeCheckoutSessionClientProtocol,
    base_url: str,
    idempotency_store=None,
    now: Optional[datetime] = None,
) -> EventFormReceiveResult:
    """design 2節の処理順序(JSONパース → `create_checkout_session_for_event_memo()`への
    委譲 → outcome別のレスポンス整形)を実装する。

    - JSON本文のパースに失敗、またはパース結果がdictでない場合は400を返す。
    - `outcome="insufficient_input"`の場合、`insufficient_input_response`をそのまま200で
      返す(design 2節: 主催者の入力不備はフォーム側に表示する正常系の応答)。
    - `outcome="checkout_session_created"`の場合、`draft_id`・`checkout_url`のみを
      200で返す。
    """
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return EventFormReceiveResult(
            status_code=400, body={"ok": False, "error": "request body is not valid JSON"}
        )

    if not isinstance(payload, dict):
        return EventFormReceiveResult(
            status_code=400,
            body={"ok": False, "error": "request body must be a JSON object"},
        )

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    result = create_checkout_session_for_event_memo(
        payload,
        draft_store,
        checkout_client,
        base_url,
        now=resolved_now,
        idempotency_store=idempotency_store,
    )

    if result.outcome == "insufficient_input":
        return EventFormReceiveResult(status_code=200, body=result.insufficient_input_response)

    return EventFormReceiveResult(
        status_code=200,
        body={"ok": True, "draft_id": result.draft_id, "checkout_url": result.checkout_url},
    )


def _demo() -> None:
    from checkout_session_creation import InMemoryCheckoutSessionClient
    from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore
    from stripe_webhook import InMemoryOneTimeDraftStore

    body = (
        '{"capacity": "300人", "entry_exit_points": "入場口2・退場口1", '
        '"admission_type": "自由入場"}'
    ).encode("utf-8")
    result = receive_event_form_submission(
        body,
        draft_store=InMemoryOneTimeDraftStore(),
        checkout_client=InMemoryCheckoutSessionClient(),
        base_url="https://example.invalid",
        idempotency_store=InMemoryIdempotencyKeyIndexStore(),
    )
    print(f"status_code={result.status_code}, body={result.to_json_body()}")


if __name__ == "__main__":
    _demo()
