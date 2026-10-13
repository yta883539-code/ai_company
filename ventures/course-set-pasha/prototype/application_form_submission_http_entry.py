#!/usr/bin/env python3
"""
application-form-submission-http-entry-point-design.mdで設計した、GAS Webhookからの
実HTTPリクエストを受け取り、共有シークレット検証〜JSONパース〜
`user_id_linking.handle_form_submission_with_linking_code()`への委譲までを行う
受信処理の本体。

位置づけ:
- `cloud_function_webhook.receive_webhook()`と同じ「本体はbytes/dictのみを扱い
  実クラウド接続なしでテスト可能、`main(request)`だけが実`functions_framework`
  リクエストオブジェクトを扱う薄い配線」構成を踏襲する
  (薄い配線側は`cloud_function_application_form_submission.py`)。
- `user_id_linking.py`(連携コード解決)・`application_form_submission_flow.py`
  (Protocol定義)の双方に依存するため、循環import回避のためどちらのモジュールにも
  追記せず本モジュールを新設した。

設計の参照元: application-form-submission-http-entry-point-design.md
"""

from __future__ import annotations

import hmac
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from application_form_submission_flow import UserProfileStoreProtocol
from user_id_linking import LinkingCodeStoreProtocol, handle_form_submission_with_linking_code


@dataclass
class FormSubmissionReceiveResult:
    """`receive_application_form_submission()`の結果。design 3節のレスポンス形状
    (`{"ok": bool, "error": str|null}`)とHTTPステータスコードを両方保持する。"""

    status_code: int
    ok: bool
    error: Optional[str] = None

    def to_json_body(self) -> str:
        return json.dumps({"ok": self.ok, "error": self.error})


def receive_application_form_submission(
    raw_body: bytes,
    secret_header: Optional[str],
    expected_secret: str,
    profile_store: UserProfileStoreProtocol,
    linking_store: LinkingCodeStoreProtocol,
    now: datetime,
) -> FormSubmissionReceiveResult:
    """design 2節・3節の処理順序(認証 → JSONパース → ペイロード検証・書き込み)を実装する。

    認証を最初に行う(ペイロード内容を検証する前に弾く)。`expected_secret`が空文字列
    (環境変数`FORM_WEBHOOK_SHARED_SECRET`未設定)の場合は、
    `cloud_function_webhook.receive_webhook()`の`channel_secret`未設定時と異なり、
    本モジュールでは安全側に倒して常に401とする(空文字列同士の一致で誰でも
    通過できてしまう事故を避けるため。LINE側は実装済みの署名検証ロジックが別途
    `channel_secret`以外の要素〈署名そのもの〉も使うため同じ扱いにはできないが、
    本モジュールの認証はヘッダ文字列の一致のみに依存するため、空シークレットの
    許容は実質的に無認証運用になってしまう)。
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

    result = handle_form_submission_with_linking_code(
        payload, profile_store, linking_store, now
    )
    if not result.ok:
        return FormSubmissionReceiveResult(status_code=400, ok=False, error=result.error)

    return FormSubmissionReceiveResult(status_code=200, ok=True)
