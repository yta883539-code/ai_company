#!/usr/bin/env python3
"""stripe_webhook.pyの机上テスト(実Stripe/実クラウド接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他venture/prototypeディレクトリと同じ発見方式)。
"""

import hashlib
import hmac
import json
import unittest
from datetime import datetime, timedelta, timezone

from stripe_webhook import (
    InMemoryOneTimeDraftStore,
    InMemoryStripeEventIdStore,
    OneTimeDraft,
    handle_checkout_session_completed,
    receive_stripe_webhook,
    verify_stripe_signature,
)

SECRET = "whsec_test_secret"


def _sign(payload: bytes, timestamp: int, secret: str = SECRET) -> str:
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


class VerifyStripeSignatureTest(unittest.TestCase):
    def setUp(self):
        self.payload = b'{"id":"evt_1","type":"checkout.session.completed"}'
        self.now = 1_700_000_000

    def test_valid_signature_within_tolerance(self):
        header = _sign(self.payload, self.now)
        self.assertTrue(
            verify_stripe_signature(self.payload, header, SECRET, now=self.now)
        )

    def test_missing_header_is_rejected(self):
        self.assertFalse(verify_stripe_signature(self.payload, None, SECRET))
        self.assertFalse(verify_stripe_signature(self.payload, "", SECRET))

    def test_malformed_header_is_rejected(self):
        self.assertFalse(
            verify_stripe_signature(self.payload, "not-a-valid-header", SECRET)
        )
        self.assertFalse(
            verify_stripe_signature(self.payload, "t=123", SECRET)
        )

    def test_wrong_secret_is_rejected(self):
        header = _sign(self.payload, self.now, secret="whsec_wrong")
        self.assertFalse(
            verify_stripe_signature(self.payload, header, SECRET, now=self.now)
        )

    def test_signature_matches_but_timestamp_out_of_tolerance(self):
        old_timestamp = self.now - 301
        header = _sign(self.payload, old_timestamp)
        self.assertFalse(
            verify_stripe_signature(self.payload, header, SECRET, now=self.now)
        )

    def test_multiple_v1_signatures_rotation(self):
        correct = _sign(self.payload, self.now)
        _, v1_part = correct.split(",")
        header = f"t={self.now},v1=deadbeef,{v1_part}"
        self.assertTrue(
            verify_stripe_signature(self.payload, header, SECRET, now=self.now)
        )

    def test_v0_only_is_rejected(self):
        header = f"t={self.now},v0=deadbeef"
        self.assertFalse(
            verify_stripe_signature(self.payload, header, SECRET, now=self.now)
        )


def _checkout_event(
    event_id="evt_1",
    draft_id="draft_abc",
    checkout_session_id="cs_abc",
    email="organizer@example.com",
    payment_intent_id="pi_abc",
):
    return {
        "id": event_id,
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": draft_id,
                "id": checkout_session_id,
                "customer_details": {"email": email},
                "payment_intent": payment_intent_id,
            }
        },
    }


class HandleCheckoutSessionCompletedTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryOneTimeDraftStore()
        self.now = datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)

    def test_draft_not_found_is_rejected_without_write(self):
        result = handle_checkout_session_completed(
            _checkout_event(draft_id="missing_draft"), self.store, now=self.now
        )
        self.assertEqual(result.outcome, "draft_not_found")
        self.assertIsNone(self.store.get("missing_draft"))

    def test_missing_client_reference_id(self):
        event = _checkout_event()
        del event["data"]["object"]["client_reference_id"]
        result = handle_checkout_session_completed(event, self.store, now=self.now)
        self.assertEqual(result.outcome, "missing_fields")

    def test_awaiting_payment_draft_proceeds_and_is_written(self):
        self.store.seed(
            OneTimeDraft(
                draft_id="draft_abc",
                status="awaiting_payment",
                expires_at=self.now + timedelta(hours=12),
            )
        )
        result = handle_checkout_session_completed(
            _checkout_event(), self.store, now=self.now
        )
        self.assertEqual(result.outcome, "proceed_to_generation")
        self.assertEqual(result.customer_email, "organizer@example.com")
        self.assertEqual(result.checkout_session_id, "cs_abc")
        self.assertEqual(result.payment_intent_id, "pi_abc")
        stored = self.store.get("draft_abc")
        self.assertEqual(stored.checkout_session_id, "cs_abc")
        self.assertEqual(stored.customer_email, "organizer@example.com")
        self.assertEqual(stored.payment_intent_id, "pi_abc")

    def test_missing_payment_intent_is_stored_as_none(self):
        """design上はmode="payment"のCheckout Session完了イベントには常にpayment_intent
        が含まれる想定だが、欠落時にKeyError等で落ちず安全にNoneへフォールバックすることを
        確認する(generation_retry_and_refund.py側の防御的分岐と対になるテスト)。"""
        self.store.seed(
            OneTimeDraft(
                draft_id="draft_abc",
                status="awaiting_payment",
                expires_at=self.now + timedelta(hours=12),
            )
        )
        event = _checkout_event(payment_intent_id=None)
        del event["data"]["object"]["payment_intent"]
        result = handle_checkout_session_completed(event, self.store, now=self.now)
        self.assertEqual(result.outcome, "proceed_to_generation")
        self.assertIsNone(result.payment_intent_id)
        self.assertIsNone(self.store.get("draft_abc").payment_intent_id)

    def test_already_processed_draft_does_not_reprocess(self):
        self.store.seed(
            OneTimeDraft(
                draft_id="draft_abc",
                status="generated",
                expires_at=self.now + timedelta(hours=12),
            )
        )
        result = handle_checkout_session_completed(
            _checkout_event(), self.store, now=self.now
        )
        self.assertEqual(result.outcome, "already_processed")
        # ステータスが上書きされていないこと(生成の再実行を防ぐ)
        self.assertEqual(self.store.get("draft_abc").status, "generated")

    def test_expired_draft_is_marked_expired_after_payment(self):
        self.store.seed(
            OneTimeDraft(
                draft_id="draft_abc",
                status="awaiting_payment",
                expires_at=self.now - timedelta(hours=1),
            )
        )
        result = handle_checkout_session_completed(
            _checkout_event(), self.store, now=self.now
        )
        self.assertEqual(result.outcome, "expired")
        self.assertEqual(
            self.store.get("draft_abc").status, "expired_after_payment"
        )


class ReceiveStripeWebhookTest(unittest.TestCase):
    def setUp(self):
        self.draft_store = InMemoryOneTimeDraftStore()
        self.now = datetime(2026, 11, 7, 0, 0, tzinfo=timezone.utc)
        self.draft_store.seed(
            OneTimeDraft(
                draft_id="draft_abc",
                status="awaiting_payment",
                expires_at=self.now + timedelta(hours=12),
            )
        )

    def _body(self, event: dict) -> bytes:
        return json.dumps(event).encode("utf-8")

    def test_invalid_signature_returns_401_without_touching_store(self):
        body = self._body(_checkout_event())
        result = receive_stripe_webhook(
            body,
            "t=1,v1=deadbeef",
            SECRET,
            draft_store=self.draft_store,
            now=self.now,
        )
        self.assertEqual(result.status_code, 401)
        self.assertEqual(self.draft_store.get("draft_abc").status, "awaiting_payment")

    def test_invalid_json_returns_400(self):
        body = b"not-json"
        header = _sign(body, int(self.now.timestamp()))
        result = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(result.status_code, 400)

    def test_checkout_session_completed_proceeds(self):
        body = self._body(_checkout_event())
        header = _sign(body, int(self.now.timestamp()))
        result = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.checkout_result.outcome, "proceed_to_generation")

    def test_other_event_type_is_ignored(self):
        event = {"id": "evt_2", "type": "payment_intent.created", "data": {"object": {}}}
        body = self._body(event)
        header = _sign(body, int(self.now.timestamp()))
        result = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.ignored_type, "payment_intent.created")

    def test_duplicate_event_id_is_rejected_without_reprocessing(self):
        event_id_store = InMemoryStripeEventIdStore()
        body = self._body(_checkout_event(event_id="evt_dup"))
        header = _sign(body, int(self.now.timestamp()))

        first = receive_stripe_webhook(
            body,
            header,
            SECRET,
            draft_store=self.draft_store,
            event_id_store=event_id_store,
            now=self.now,
        )
        self.assertEqual(first.checkout_result.outcome, "proceed_to_generation")
        # 1回目の処理でdraftは既にawaiting_payment以外のドラフト固有状態には遷移しない
        # (本モジュールはstatus自体を書き換えない、checkout_session_id等のみ書き込む)が、
        # event_id_store側では処理済みとして記録されていることを確認する。
        self.assertTrue(event_id_store.has_processed("evt_dup"))

        second = receive_stripe_webhook(
            body,
            header,
            SECRET,
            draft_store=self.draft_store,
            event_id_store=event_id_store,
            now=self.now,
        )
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.duplicate)
        self.assertIsNone(second.checkout_result)

    def test_without_event_id_store_duplicate_is_still_safe_via_status(self):
        # event_id_store省略時でも、1回目の処理後にテスト側でstatusをgeneratedへ進めて
        # おけば2回目はalready_processedとして弾かれる(design 2-2節の多層防御)。
        body = self._body(_checkout_event())
        header = _sign(body, int(self.now.timestamp()))

        first = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(first.checkout_result.outcome, "proceed_to_generation")

        self.draft_store.get("draft_abc").status = "generated"

        second = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(second.checkout_result.outcome, "already_processed")


if __name__ == "__main__":
    unittest.main()
