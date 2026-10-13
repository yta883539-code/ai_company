#!/usr/bin/env python3
"""
application-form-submission-http-entry-point-design.md 4節で設計した、GAS Webhookから
実際のPOSTリクエストを受け取る薄いCloud Functionsエントリポイント。

位置づけ:
- cloud_function_webhook.py・cloud_function_send_trial_end_notifications.py等と同じ
  「本体は依存注入でテスト可能、main(request)だけが実functions_frameworkリクエスト
  オブジェクトを扱う薄い配線」構成を踏襲する。
- 実Firestore接続(`user_profile`・`pending_links`コレクション)はGoogleフォーム+GAS
  Webhook自体がオーナー承認待ち(pending-approval.md承認待ち事項2)のため、現時点では
  `get_application_form_submission_runtime_dependencies()`が検証用のInMemory実装を返す。
  承認・実接続後は、この関数の中身を実Firestoreクライアントを返すように差し替えるだけで
  main()・receive_application_form_submission()双方を変更せずに接続できる。
- 共有シークレットは環境変数`FORM_WEBHOOK_SHARED_SECRET`から取得する
  (cloud_function_webhook.pyの`LINE_CHANNEL_SECRET`と同じパターン)。

設計の参照元: application-form-submission-http-entry-point-design.md
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from application_form_submission_flow import InMemoryUserProfileStore  # noqa: E402
from application_form_submission_http_entry import (  # noqa: E402
    receive_application_form_submission,
)
from user_id_linking import InMemoryLinkingCodeStore  # noqa: E402


def get_application_form_submission_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_send_deletion_candidate_
    final_confirmations.get_deletion_candidate_final_confirmation_runtime_dependencies()
    と対称の構成)。

    実Firestore接続は実GCPプロジェクト・Googleフォーム+GAS Webhook自体のオーナー承認後
    でなければ構築できないため、現時点では検証用のInMemory実装を返す。呼び出しごとに
    新規生成されるため、実Cloud Functions環境でも呼び出しをまたいで状態
    (発行済み連携コード・user_profile)が保持されない既知の限界が残る(他Cloud Function
    同様、実Firestore接続後に解消される)。
    """
    return {
        "profile_store": InMemoryUserProfileStore(),
        "linking_store": InMemoryLinkingCodeStore(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    `request.get_data()`でbytesを、`request.headers.get("X-Form-Webhook-Secret")`で
    共有シークレットヘッダを取得し、`receive_application_form_submission()`に委譲する。
    """
    body = request.get_data()
    secret_header = request.headers.get("X-Form-Webhook-Secret")
    expected_secret = os.environ.get("FORM_WEBHOOK_SHARED_SECRET", "")

    deps = get_application_form_submission_runtime_dependencies()
    result = receive_application_form_submission(
        body,
        secret_header,
        expected_secret,
        now=datetime.now(timezone.utc),
        **deps,
    )
    return result.to_json_body(), result.status_code


def _demo() -> None:
    class _StubRequest:
        def __init__(self, body: bytes, headers: dict) -> None:
            self._body = body
            self.headers = headers

        def get_data(self) -> bytes:
            return self._body

    os.environ["FORM_WEBHOOK_SHARED_SECRET"] = "demo-secret"
    body, status_code = main(
        _StubRequest(
            b'{"linking_code": "BADCODE", "gym_area_pairs_raw": "", "email": "a@b.com"}',
            {"X-Form-Webhook-Secret": "demo-secret"},
        )
    )
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
