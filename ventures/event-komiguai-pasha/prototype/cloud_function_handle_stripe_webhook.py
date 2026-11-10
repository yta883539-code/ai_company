#!/usr/bin/env python3
"""
handle-stripe-webhook-http-entry-point-design.md(フェーズ111)で設計した、Stripeからの
実Webhook POSTリクエストを受け取る薄いCloud Functionsエントリポイント(`handle_stripe_
webhook`関数)。

位置づけ:
- `cloud_function_submit_event_form.py`(フェーズ110)・`cloud_function_submit_inquiry.py`
  (フェーズ109)と同じ「本体は依存注入でテスト可能、main(request)だけが実
  functions_frameworkリクエストオブジェクトを扱う薄い配線」構成を踏襲する。
- 業務ロジック本体(署名検証・冪等性チェック・振り分け)は`stripe_webhook.
  receive_stripe_webhook()`(フェーズ99)にそのまま委ねる。本モジュールは
  実リクエストオブジェクトからのbody・`Stripe-Signature`ヘッダ・webhook secret
  (環境変数`STRIPE_WEBHOOK_SECRET`)の取り出し配線のみを新規に扱う。
- `generate_fn`・`refund_client`・`email_sender`は本フェーズでは渡さない(design 3節参照)。
  実Stripeアカウント作成・実メール送信手段確定後の別課題として残す。

設計の参照元: handle-stripe-webhook-http-entry-point-design.md
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stripe_webhook import (  # noqa: E402
    InMemoryOneTimeDraftStore,
    InMemoryStripeEventIdStore,
    receive_stripe_webhook,
)


def get_handle_stripe_webhook_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(`get_submit_event_form_runtime_
    dependencies()`・`get_submit_inquiry_runtime_dependencies()`と対称の構成)。

    実Firestore接続はオーナー承認後でなければ構築できないため、現時点では検証用の
    InMemory実装を返す。呼び出しごとに新規生成されるため、実Cloud Functions環境でも
    呼び出しをまたいで状態(draft・処理済みevent_id)が保持されない既知の限界が残る
    (他Cloud Function同様、実接続後に解消される)。
    """
    return {
        "draft_store": InMemoryOneTimeDraftStore(),
        "event_id_store": InMemoryStripeEventIdStore(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、Stripe版)。

    `request.get_data()`でbody、`request.headers.get("Stripe-Signature")`で署名
    ヘッダを取り出し、環境変数`STRIPE_WEBHOOK_SECRET`(未設定時は空文字列=常に署名
    検証失敗)と合わせて`receive_stripe_webhook()`に委譲する(aircon-pasha/
    course-set-pasha版`stripe_webhook.main()`と対称の構成)。

    `status_code`が200の場合は本文`"OK"`を返し、それ以外の場合は`result.error`を
    そのまま本文として返す(design 2節: Stripe側はステータスコードのみで再送判定する
    ため、JSON化せずプレーンテキストで十分という既存方針を踏襲する)。
    """
    body = request.get_data()
    signature_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    result = receive_stripe_webhook(
        body,
        signature_header,
        webhook_secret,
        **get_handle_stripe_webhook_runtime_dependencies(),
    )

    if result.status_code == 200:
        return "OK", 200
    return (result.error or "error"), result.status_code


def _demo() -> None:
    import hashlib
    import hmac
    import time

    class _StubRequest:
        def __init__(self, body: bytes, headers: dict) -> None:
            self._body = body
            self.headers = headers

    secret = "whsec_demo_secret"
    os.environ["STRIPE_WEBHOOK_SECRET"] = secret
    payload = b'{"id":"evt_demo","type":"unhandled.event"}'
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={sig}"
    body, status_code = main(_StubRequest(payload, {"Stripe-Signature": header}))
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
