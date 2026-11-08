#!/usr/bin/env python3
"""checkout_session_creation.pyの机上テスト(実Stripe/実クラウド接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他プロトタイプテストと同じ発見方式)。
"""

import unittest
from datetime import datetime, timedelta, timezone

from checkout_session_creation import (
    CheckoutSessionResult,
    create_checkout_session_for_event_memo,
)
from stripe_webhook import InMemoryOneTimeDraftStore


class StubCheckoutSessionClient:
    """Stripe Checkout Session作成呼び出しの記録のみを行うテスト用スタブ。"""

    def __init__(self, session_id="cs_test_1", checkout_url="https://checkout.stripe.com/cs_test_1"):
        self.session_id = session_id
        self.checkout_url = checkout_url
        self.calls = []

    def create_session(self, *, amount, currency, client_reference_id):
        self.calls.append(
            {
                "amount": amount,
                "currency": currency,
                "client_reference_id": client_reference_id,
            }
        )
        return CheckoutSessionResult(session_id=self.session_id, checkout_url=self.checkout_url)


VALID_PAYLOAD = {
    "capacity": "200人",
    "entry_exit_points": "入場口1・退場口1(共用)",
    "admission_type": "自由入場",
    "staffing": "",
    "outdoor_queue": None,
}

INSUFFICIENT_PAYLOAD = {
    "capacity": "200人",
    "entry_exit_points": "",
    "admission_type": None,
}


class CreateCheckoutSessionForEventMemoTest(unittest.TestCase):
    def setUp(self):
        self.draft_store = InMemoryOneTimeDraftStore()
        self.checkout_client = StubCheckoutSessionClient()
        self.fixed_now = datetime(2026, 11, 8, 8, 0, tzinfo=timezone.utc)
        self.draft_ids = iter(["11111111-1111-4111-8111-111111111111"])

    def _draft_id_factory(self):
        return next(self.draft_ids)

    def test_insufficient_input_does_not_create_draft_or_session(self):
        result = create_checkout_session_for_event_memo(
            INSUFFICIENT_PAYLOAD,
            self.draft_store,
            self.checkout_client,
            now=self.fixed_now,
            draft_id_factory=self._draft_id_factory,
        )

        self.assertEqual(result.outcome, "insufficient_input")
        self.assertIsNotNone(result.insufficient_input_response)
        self.assertEqual(
            result.insufficient_input_response["status"], "insufficient_input"
        )
        self.assertIsNone(result.draft_id)
        self.assertIsNone(result.checkout_session_id)
        # draftもCheckout Session呼び出しも発生しないこと(design 2節の前提)。
        self.assertEqual(len(self.draft_store._drafts), 0)
        self.assertEqual(self.checkout_client.calls, [])

    def test_valid_payload_creates_draft_then_checkout_session(self):
        result = create_checkout_session_for_event_memo(
            VALID_PAYLOAD,
            self.draft_store,
            self.checkout_client,
            now=self.fixed_now,
            draft_id_factory=self._draft_id_factory,
        )

        self.assertEqual(result.outcome, "checkout_session_created")
        self.assertEqual(result.draft_id, "11111111-1111-4111-8111-111111111111")
        self.assertEqual(result.draft_id_last4, "1111")
        self.assertEqual(result.checkout_session_id, "cs_test_1")
        self.assertEqual(result.checkout_url, "https://checkout.stripe.com/cs_test_1")

        # draftが先に作成され、event_memo(生ペイロード)がそのまま保存されていること。
        draft = self.draft_store.get(result.draft_id)
        self.assertIsNotNone(draft)
        self.assertEqual(draft.status, "awaiting_payment")
        self.assertEqual(draft.event_memo, VALID_PAYLOAD)
        self.assertEqual(draft.draft_id_last4, "1111")
        self.assertEqual(draft.expires_at, self.fixed_now + timedelta(hours=24))

        # Checkout Session作成が正しい引数(金額・通貨・client_reference_id=draft_id)で
        # 1回だけ呼ばれていること。
        self.assertEqual(len(self.checkout_client.calls), 1)
        call = self.checkout_client.calls[0]
        self.assertEqual(call["amount"], 500)
        self.assertEqual(call["currency"], "jpy")
        self.assertEqual(call["client_reference_id"], result.draft_id)

    def test_custom_ttl_hours_changes_expires_at(self):
        result = create_checkout_session_for_event_memo(
            VALID_PAYLOAD,
            self.draft_store,
            self.checkout_client,
            now=self.fixed_now,
            ttl_hours=1,
            draft_id_factory=self._draft_id_factory,
        )

        draft = self.draft_store.get(result.draft_id)
        self.assertEqual(draft.expires_at, self.fixed_now + timedelta(hours=1))

    def test_draft_created_before_checkout_session_call_order(self):
        # Checkout Session作成が失敗してもdraftは既に存在する、という順序(design 2節
        # 手順2→3)をスタブの副作用順で確認する。
        call_order = []

        class OrderTrackingDraftStore(InMemoryOneTimeDraftStore):
            def create_draft(self, draft_id, **kwargs):
                call_order.append("create_draft")
                super().create_draft(draft_id, **kwargs)

        class OrderTrackingCheckoutClient(StubCheckoutSessionClient):
            def create_session(self, **kwargs):
                call_order.append("create_session")
                return super().create_session(**kwargs)

        create_checkout_session_for_event_memo(
            VALID_PAYLOAD,
            OrderTrackingDraftStore(),
            OrderTrackingCheckoutClient(),
            now=self.fixed_now,
            draft_id_factory=self._draft_id_factory,
        )

        self.assertEqual(call_order, ["create_draft", "create_session"])

    def test_default_draft_id_factory_produces_uuid4_like_value(self):
        result = create_checkout_session_for_event_memo(
            VALID_PAYLOAD,
            self.draft_store,
            self.checkout_client,
            now=self.fixed_now,
        )
        # UUID4文字列表現(36文字、ハイフン4個)であることのみ確認する(厳密な
        # バージョン検証はdraft-id-last4-collision-design.mdの既存知見に委ねる)。
        self.assertEqual(len(result.draft_id), 36)
        self.assertEqual(result.draft_id.count("-"), 4)
        self.assertEqual(result.draft_id_last4, result.draft_id[-4:])


if __name__ == "__main__":
    unittest.main()
