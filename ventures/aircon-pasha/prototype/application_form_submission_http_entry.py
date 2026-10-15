#!/usr/bin/env python3
"""
application-form-submission-http-entry-point-design.mdで設計した、GAS Webhookからの
実HTTPリクエストを受け取り、共有シークレット検証〜JSONパース〜
`application_form_submission_flow.handle_form_submission()`への委譲までを行う
受信処理の本体。

位置づけ:
- `cloud_function_webhook.receive_webhook()`と同じ「本体はbytes/dictのみを扱い
  実クラウド接続なしでテスト可能、`main(request)`だけが実`functions_framework`
  リクエストオブジェクトを扱う薄い配線」構成を踏襲する
  (薄い配線側は`cloud_function_application_form_submission.py`)。
- `user_id_linking.py`(連携コード発行)・`application_form_submission_flow.py`
  (ペイロード検証)の双方に依存するため、循環import回避のためどちらのモジュールにも
  追記せず本モジュールを新設した(course-set-pasha/prototype/application_form_
  submission_http_entry.pyと同じ位置づけ)。
- design 2節: 本ventureはフォーム送信が連携コードの発行契機のため(course-set-pashaとは
  逆向き)、成功時のレスポンスには発行した`linking_code`を含める。

設計の参照元: application-form-submission-http-entry-point-design.md
"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from application_form_submission_flow import handle_form_submission
from user_id_linking import LinkingCodeStoreProtocol, RandomChoiceSource


@dataclass
class FormSubmissionReceiveResult:
    """`receive_application_form_submission()`の結果。design 4節のレスポンス形状
    (`{"ok": bool, "linking_code": str|null, "error": str|null}`)とHTTPステータス
    コードを両方保持する。"""

    status_code: int
    ok: bool
    linking_code: Optional[str] = None
    error: Optional[str] = None

    def to_json_body(self) -> str:
        return json.dumps(
            {"ok": self.ok, "linking_code": self.linking_code, "error": self.error}
        )


def receive_application_form_submission(
    raw_body: bytes,
    secret_header: Optional[str],
    expected_secret: str,
    store: LinkingCodeStoreProtocol,
    now: datetime,
    rng: RandomChoiceSource,
) -> FormSubmissionReceiveResult:
    """design 3節・4節の処理順序(認証 → JSONパース → ペイロード検証・連携コード発行)を
    実装する。

    認証を最初に行う(ペイロード内容を検証する前に弾く)。`expected_secret`が空文字列
    (環境変数`FORM_WEBHOOK_SHARED_SECRET`未設定)の場合は、course-set-pasha版と同じく
    安全側に倒して常に401とする(空文字列同士の一致で誰でも通過できてしまう事故を
    避けるため)。
    """
    if not expected_secret or not secret_header or not hmac.compare_digest(
        secret_header, expected_secret
    ):
        return FormSubmissionReceiveResult(
            status_code=401, ok=False, error="shared secret missing or mismatched"
        )

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return FormSubmissionReceiveResult(
            status_code=400, ok=False, error="request body is not valid JSON"
        )

    if not isinstance(payload, dict):
        return FormSubmissionReceiveResult(
            status_code=400, ok=False, error="request body must be a JSON object"
        )

    result = handle_form_submission(payload, store, now, rng)
    if not result.ok:
        return FormSubmissionReceiveResult(status_code=400, ok=False, error=result.error)

    return FormSubmissionReceiveResult(
        status_code=200, ok=True, linking_code=result.linking_code
    )
