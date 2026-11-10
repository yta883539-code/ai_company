#!/usr/bin/env python3
"""
inquiry-form-http-entry-point-design.md(フェーズ109)4節で設計した、問い合わせフォームから
実際のPOSTリクエストを受け取る薄いCloud Functionsエントリポイント(`submit_inquiry`関数)。

位置づけ:
- `cloud_function_application_form_submission.py`(aircon-pasha)等と同じ「本体は依存注入で
  テスト可能、main(request)だけが実functions_frameworkリクエストオブジェクトを扱う薄い配線」
  構成を踏襲する。
- 実Firestore接続(`inquiry`コレクション・`idempotency_key_index`コレクション)は実GCPプロジェクト
  作成(pending-approval.md記載、オーナー承認待ち)後の課題のため、現時点では
  `get_submit_inquiry_runtime_dependencies()`が検証用のInMemory実装を返す。承認・実接続後は、
  この関数の中身を実Firestoreクライアントを返すように差し替えるだけで`main()`・
  `receive_inquiry_form_submission()`双方を変更せずに接続できる。
- 本venture(event-komiguai-pasha)の`submit_inquiry`はブラウザから直接呼ばれるHTTPSトリガー
  であり、aircon-pasha版のような共有シークレット検証は行わない(design 2節)。

設計の参照元: inquiry-form-http-entry-point-design.md
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore  # noqa: E402
from inquiry_collection_store import InMemoryInquiryCollection  # noqa: E402
from inquiry_form_http_entry import receive_inquiry_form_submission  # noqa: E402


def get_submit_inquiry_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(他Cloud Functionの
    get_*_runtime_dependencies()と対称の構成)。

    実Firestore接続は実GCPプロジェクト作成自体がオーナー承認後でなければ構築できないため、
    現時点では検証用のInMemory実装を返す。呼び出しごとに新規生成されるため、実Cloud
    Functions環境でも呼び出しをまたいで状態(受付済みinquiry・idempotency_key)が保持されない
    既知の限界が残る(他Cloud Function同様、実Firestore接続後に解消される)。
    """
    return {
        "collection": InMemoryInquiryCollection(),
        "idempotency_store": InMemoryIdempotencyKeyIndexStore(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    `request.get_data()`でbytesを取得し、`receive_inquiry_form_submission()`に委譲する。
    """
    body = request.get_data()
    deps = get_submit_inquiry_runtime_dependencies()
    result = receive_inquiry_form_submission(
        body, now=datetime.now(timezone.utc), **deps
    )
    return result.to_json_body(), result.status_code


def _demo() -> None:
    class _StubRequest:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def get_data(self) -> bytes:
            return self._body

    demo_body = (
        '{"draft_id": "draft-1", "customer_email": "a@b.com", '
        '"category": "メール未着"}'
    ).encode("utf-8")
    body, status_code = main(_StubRequest(demo_body))
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
