#!/usr/bin/env python3
"""
submit-event-form-http-entry-point-design.md(フェーズ110)3節で設計した、Webフォームから
実際のPOSTリクエストを受け取る薄いCloud Functionsエントリポイント(`submit_event_form`関数)。

位置づけ:
- `cloud_function_submit_inquiry.py`(フェーズ109)と同じ「本体は依存注入でテスト可能、
  main(request)だけが実functions_frameworkリクエストオブジェクトを扱う薄い配線」構成を
  踏襲する。
- 実Firestore接続(`one_time_draft`・`idempotency_key_index`コレクション)・実Stripe接続・
  実ドメイン(`base_url`)確定はいずれも実GCPプロジェクト作成・実Stripeアカウント作成
  (pending-approval.md記載、オーナー承認待ち)後の課題のため、現時点では
  `get_submit_event_form_runtime_dependencies()`が検証用のInMemory実装・プレースホルダ
  URLを返す。承認・実接続後は、この関数の中身を実クライアントを返すように差し替えるだけで
  `main()`・`receive_event_form_submission()`双方を変更せずに接続できる。

設計の参照元: submit-event-form-http-entry-point-design.md
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from checkout_session_creation import InMemoryCheckoutSessionClient  # noqa: E402
from checkout_session_http_entry import receive_event_form_submission  # noqa: E402
from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore  # noqa: E402
from stripe_webhook import InMemoryOneTimeDraftStore  # noqa: E402

# web-form-hosting-selection.md参照、実ドメイン確定前のプレースホルダ(design 3節)。
PLACEHOLDER_BASE_URL = "https://example.invalid"


def get_submit_event_form_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(`get_submit_inquiry_runtime_dependencies()`と
    対称の構成)。

    実Firestore・実Stripe接続はいずれもオーナー承認後でなければ構築できないため、
    現時点では検証用のInMemory実装・プレースホルダURLを返す。呼び出しごとに新規生成
    されるため、実Cloud Functions環境でも呼び出しをまたいで状態(draft・idempotency_key)
    が保持されない既知の限界が残る(他Cloud Function同様、実接続後に解消される)。
    """
    return {
        "draft_store": InMemoryOneTimeDraftStore(),
        "checkout_client": InMemoryCheckoutSessionClient(),
        "base_url": PLACEHOLDER_BASE_URL,
        "idempotency_store": InMemoryIdempotencyKeyIndexStore(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    `request.get_data()`でbytesを取得し、`receive_event_form_submission()`に委譲する。
    """
    body = request.get_data()
    deps = get_submit_event_form_runtime_dependencies()
    result = receive_event_form_submission(body, now=datetime.now(timezone.utc), **deps)
    return result.to_json_body(), result.status_code


def _demo() -> None:
    class _StubRequest:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def get_data(self) -> bytes:
            return self._body

    demo_body = (
        '{"capacity": "300人", "entry_exit_points": "入場口2・退場口1", '
        '"admission_type": "自由入場"}'
    ).encode("utf-8")
    body, status_code = main(_StubRequest(demo_body))
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
