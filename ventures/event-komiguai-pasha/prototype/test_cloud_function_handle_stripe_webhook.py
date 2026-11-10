#!/usr/bin/env python3
"""cloud_function_handle_stripe_webhook.pyの机上テスト(実Cloud Functions環境・実クラウド
接続なし)。python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype
-p "test_*.py"から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import hashlib
import hmac
import json
import os
import time
import unittest

from cloud_function_handle_stripe_webhook import main


class _StubRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (aircon-pasha/course-set-pasha/prototype/test_stripe_webhook.py `_StubFlaskRequest`
    と対称)。"""

    def __init__(self, body: bytes, headers: dict) -> None:
        self._body = body
        self.headers = headers

    def get_data(self) -> bytes:
        return self._body


class MainTest(unittest.TestCase):
    ENV_SECRET = "demo-webhook-secret"

    def _signed_header(self, body: bytes, secret: str) -> str:
        timestamp = int(time.time())
        signed_payload = f"{timestamp}.{body.decode('utf-8')}".encode("utf-8")
        sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={sig}"

    def setUp(self):
        self._original_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
        os.environ["STRIPE_WEBHOOK_SECRET"] = self.ENV_SECRET

    def tearDown(self):
        if self._original_secret is None:
            os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        else:
            os.environ["STRIPE_WEBHOOK_SECRET"] = self._original_secret

    def test_valid_signature_unhandled_type_returns_200_ok(self):
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubRequest(
            body, {"Stripe-Signature": self._signed_header(body, self.ENV_SECRET)}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 200)
        self.assertEqual(response_body, "OK")

    def test_valid_signature_checkout_completed_without_matching_draft_returns_200(self):
        body = json.dumps(
            {
                "id": "evt_2",
                "type": "checkout.session.completed",
                "data": {"object": {"client_reference_id": "draft_unknown"}},
            }
        ).encode("utf-8")
        request = _StubRequest(
            body, {"Stripe-Signature": self._signed_header(body, self.ENV_SECRET)}
        )

        response_body, status_code = main(request)

        # draft_storeは呼び出しごとに新規生成されるインメモリ実装のため、draft_unknownは
        # 常に見つからない(draft_not_found)。署名検証・JSONパース・振り分け配線自体が
        # 正しく機能し200を返すことのみを確認する(design 3節の既知の限界)。
        self.assertEqual(status_code, 200)
        self.assertEqual(response_body, "OK")

    def test_invalid_signature_returns_401_with_error_body(self):
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubRequest(body, {"Stripe-Signature": "t=1,v1=invalid"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)
        self.assertEqual(response_body, "invalid_signature")

    def test_missing_signature_header_returns_401(self):
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubRequest(body, {})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)

    def test_missing_webhook_secret_env_returns_401(self):
        os.environ.pop("STRIPE_WEBHOOK_SECRET", None)
        body = json.dumps({"id": "evt_1", "type": "unhandled.event"}).encode("utf-8")
        request = _StubRequest(
            body, {"Stripe-Signature": self._signed_header(body, self.ENV_SECRET)}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)

    def test_invalid_json_body_returns_400(self):
        body = b"not json"
        request = _StubRequest(
            body, {"Stripe-Signature": self._signed_header(body, self.ENV_SECRET)}
        )

        response_body, status_code = main(request)

        self.assertEqual(status_code, 400)


if __name__ == "__main__":
    unittest.main()
