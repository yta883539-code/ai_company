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

from generation_retry_and_refund import (
    GenerationError,
    InMemoryEmailSender,
    InMemoryRefundClient,
)
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
        # 1回目の処理でdraftは"payment_confirmed"へ遷移する(フェーズ114、
        # mark_payment_confirmed()がstatus自体を書き換えるようになった)。
        # event_id_store側でも処理済みとして記録されていることを確認する。
        self.assertEqual(self.draft_store.get("draft_abc").status, "payment_confirmed")
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

    def test_generation_wiring_is_skipped_without_the_three_callbacks(self):
        # design フェーズ100「次回候補(2)」: generate_fn等を渡さない既存の呼び出し側
        # (フェーズ99までのテスト含む)は、挙動が変わらずgeneration_outcome=Noneのまま
        # であることの後方互換確認。statusは"payment_confirmed"で止まる(フェーズ114、
        # generate_fn未指定のため生成処理自体が走らず"generated"等へは進まない)。
        body = self._body(_checkout_event())
        header = _sign(body, int(self.now.timestamp()))
        result = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(result.checkout_result.outcome, "proceed_to_generation")
        self.assertIsNone(result.generation_outcome)
        self.assertEqual(self.draft_store.get("draft_abc").status, "payment_confirmed")

    def test_redelivered_webhook_during_generation_is_rejected(self):
        # フェーズ114で解消した論点そのものの回帰テスト: generate_fn等を渡さない
        # (≒LLM生成がまだ完了していない、または非同期化されている)状態で同一Webhookが
        # 再送された場合、1回目でstatusが"payment_confirmed"へ即時遷移しているため、
        # 2回目はevent_id_store・generated遷移のいずれにも頼らず
        # already_processedとして弾かれることを確認する。
        body = self._body(_checkout_event())
        header = _sign(body, int(self.now.timestamp()))

        first = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(first.checkout_result.outcome, "proceed_to_generation")

        second = receive_stripe_webhook(
            body, header, SECRET, draft_store=self.draft_store, now=self.now
        )
        self.assertEqual(second.checkout_result.outcome, "already_processed")
        self.assertEqual(self.draft_store.get("draft_abc").status, "payment_confirmed")

    def test_generation_wiring_succeeds_and_updates_draft_status(self):
        body = self._body(_checkout_event())
        header = _sign(body, int(self.now.timestamp()))

        def generate_fn(draft_id):
            self.assertEqual(draft_id, "draft_abc")
            return {"status": "generated", "checklist": ["ok"]}

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            draft_store=self.draft_store,
            now=self.now,
            generate_fn=generate_fn,
            refund_client=InMemoryRefundClient(),
            email_sender=InMemoryEmailSender(),
        )
        self.assertEqual(result.checkout_result.outcome, "proceed_to_generation")
        self.assertIsNotNone(result.generation_outcome)
        self.assertEqual(result.generation_outcome.outcome, "generated")
        self.assertEqual(self.draft_store.get("draft_abc").status, "generated")

    def test_generation_wiring_refunds_after_exhausting_retries(self):
        body = self._body(_checkout_event())
        header = _sign(body, int(self.now.timestamp()))

        def always_failing_generate_fn(draft_id):
            raise GenerationError("LLM API一時障害(机上テスト用)")

        refund_client = InMemoryRefundClient()
        email_sender = InMemoryEmailSender()

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            draft_store=self.draft_store,
            now=self.now,
            generate_fn=always_failing_generate_fn,
            refund_client=refund_client,
            email_sender=email_sender,
        )
        self.assertEqual(result.generation_outcome.outcome, "refunded")
        self.assertEqual(result.generation_outcome.attempts, 3)
        self.assertEqual(self.draft_store.get("draft_abc").status, "refunded")
        self.assertEqual(refund_client.calls, ["pi_abc"])
        self.assertEqual(len(email_sender.sent), 1)
        self.assertEqual(email_sender.sent[0]["to"], "organizer@example.com")

    def test_generation_wiring_is_not_invoked_for_non_proceed_outcomes(self):
        # already_processed(2回目以降の配信)の場合はgenerate_fn等が渡されていても
        # 生成処理を再実行しない(design 2-2節の冪等性ガードを本モジュールが上書きしない
        # ことの確認)。
        self.draft_store.get("draft_abc").status = "generated"
        body = self._body(_checkout_event())
        header = _sign(body, int(self.now.timestamp()))

        calls = []

        def generate_fn(draft_id):
            calls.append(draft_id)
            return {"status": "generated"}

        result = receive_stripe_webhook(
            body,
            header,
            SECRET,
            draft_store=self.draft_store,
            now=self.now,
            generate_fn=generate_fn,
            refund_client=InMemoryRefundClient(),
            email_sender=InMemoryEmailSender(),
        )
        self.assertEqual(result.checkout_result.outcome, "already_processed")
        self.assertIsNone(result.generation_outcome)
        self.assertEqual(calls, [])


class CreateDraftTest(unittest.TestCase):
    """draft-creation-and-event-memo-storage-design.md(フェーズ102)。Checkout Session
    作成前にevent_memoを保存するcreate_draft()の机上テスト。"""

    def setUp(self) -> None:
        self.store = InMemoryOneTimeDraftStore()
        self.memo = {
            "capacity": "300人",
            "entry_exit_points": "入場口1・退場口1(共用)",
            "admission_type": "自由入場",
        }

    def test_create_draft_sets_awaiting_payment_and_event_memo_by_default(self) -> None:
        self.store.create_draft("draft_new", event_memo=self.memo)
        draft = self.store.get("draft_new")
        self.assertIsNotNone(draft)
        self.assertEqual(draft.status, "awaiting_payment")
        self.assertEqual(draft.event_memo, self.memo)
        self.assertIsNone(draft.checkout_session_id)

    def test_create_draft_honors_explicit_expires_at_and_status(self) -> None:
        expires_at = datetime(2026, 11, 8, 0, 0, tzinfo=timezone.utc)
        self.store.create_draft(
            "draft_custom", event_memo=self.memo, expires_at=expires_at, status="awaiting_payment"
        )
        draft = self.store.get("draft_custom")
        self.assertEqual(draft.expires_at, expires_at)

    def test_created_draft_can_proceed_through_checkout_completion(self) -> None:
        # create_draft()で作成したドラフトが、既存のhandle_checkout_session_completed()
        # フロー(フェーズ99)と変わらず結合できることを確認する回帰テスト。
        self.store.create_draft("draft_flow", event_memo=self.memo)
        event = {
            "data": {
                "object": {
                    "client_reference_id": "draft_flow",
                    "id": "cs_flow",
                    "customer_details": {"email": "organizer@example.com"},
                    "payment_intent": "pi_flow",
                }
            }
        }
        result = handle_checkout_session_completed(event, self.store)
        self.assertEqual(result.outcome, "proceed_to_generation")
        draft = self.store.get("draft_flow")
        self.assertEqual(draft.event_memo, self.memo)
        self.assertEqual(draft.checkout_session_id, "cs_flow")


if __name__ == "__main__":
    unittest.main()
