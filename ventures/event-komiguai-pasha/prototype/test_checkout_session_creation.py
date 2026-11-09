#!/usr/bin/env python3
"""checkout_session_creation.pyの机上テスト(実Stripe/実クラウド接続なし)。
python3 -m unittest discover -s ventures/event-komiguai-pasha/prototype -p "test_*.py"
から実行される想定(他プロトタイプテストと同じ発見方式)。
"""

import unittest
from datetime import datetime, timedelta, timezone

from checkout_session_creation import (
    STRIPE_PRODUCT_NAME_JA,
    CheckoutSessionResult,
    build_stripe_checkout_session_params,
    create_checkout_session_for_event_memo,
)
from idempotency_key_index_store import InMemoryIdempotencyKeyIndexStore
from stripe_webhook import InMemoryOneTimeDraftStore


class StubCheckoutSessionClient:
    """Stripe Checkout Session作成呼び出しの記録のみを行うテスト用スタブ。"""

    def __init__(self, session_id="cs_test_1", checkout_url="https://checkout.stripe.com/cs_test_1"):
        self.session_id = session_id
        self.checkout_url = checkout_url
        self.calls = []

    def create_session(
        self, *, amount, currency, client_reference_id, success_url, cancel_url
    ):
        self.calls.append(
            {
                "amount": amount,
                "currency": currency,
                "client_reference_id": client_reference_id,
                "success_url": success_url,
                "cancel_url": cancel_url,
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
            "https://example.run.app",
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
            "https://example.run.app",
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
        self.assertEqual(
            call["success_url"],
            f"https://example.run.app/result/{result.draft_id}",
        )
        self.assertEqual(call["cancel_url"], "https://example.run.app/")

    def test_custom_ttl_hours_changes_expires_at(self):
        result = create_checkout_session_for_event_memo(
            VALID_PAYLOAD,
            self.draft_store,
            self.checkout_client,
            "https://example.run.app",
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
            "https://example.run.app",
            now=self.fixed_now,
            draft_id_factory=self._draft_id_factory,
        )

        self.assertEqual(call_order, ["create_draft", "create_session"])

    def test_idempotency_key_reserves_new_draft_when_first_seen(self):
        idempotency_store = InMemoryIdempotencyKeyIndexStore()
        payload = dict(VALID_PAYLOAD, idempotency_key="idem-key-1")

        result = create_checkout_session_for_event_memo(
            payload,
            self.draft_store,
            self.checkout_client,
            "https://example.run.app",
            now=self.fixed_now,
            draft_id_factory=self._draft_id_factory,
            idempotency_store=idempotency_store,
        )

        self.assertEqual(result.outcome, "checkout_session_created")
        self.assertEqual(result.draft_id, "11111111-1111-4111-8111-111111111111")
        draft = self.draft_store.get(result.draft_id)
        self.assertIsNotNone(draft)
        self.assertEqual(len(self.draft_store._drafts), 1)

    def test_idempotency_key_reuses_existing_draft_without_recreating(self):
        idempotency_store = InMemoryIdempotencyKeyIndexStore()
        payload = dict(VALID_PAYLOAD, idempotency_key="idem-key-1")

        first = create_checkout_session_for_event_memo(
            payload,
            self.draft_store,
            self.checkout_client,
            "https://example.run.app",
            now=self.fixed_now,
            draft_id_factory=self._draft_id_factory,
            idempotency_store=idempotency_store,
        )

        # 2回目の送信(同一idempotency_key、二重クリック・再試行を想定)。
        # draft_id_factory()が別のUUIDを返しても、既存のdraft_idが優先されること。
        second_draft_ids = iter(["22222222-2222-4222-8222-222222222222"])
        result = create_checkout_session_for_event_memo(
            payload,
            self.draft_store,
            self.checkout_client,
            "https://example.run.app",
            now=self.fixed_now,
            draft_id_factory=lambda: next(second_draft_ids),
            idempotency_store=idempotency_store,
        )

        self.assertEqual(result.outcome, "checkout_session_created")
        # 新規draft_idは発行されず、1回目と同じdraft_idが再利用されること。
        self.assertEqual(result.draft_id, first.draft_id)
        # create_draft()は1回目のみ呼ばれ、draftは1件のみ存在すること(重複作成されない)。
        self.assertEqual(len(self.draft_store._drafts), 1)
        # Checkout Session作成は2回とも発生し、いずれもclient_reference_id=既存draft_id
        # であること(design フェーズ70 7.2節: Checkout Session自体はidempotency_keyに
        # 紐づかず、二重決済にはつながらない)。
        self.assertEqual(len(self.checkout_client.calls), 2)
        self.assertEqual(self.checkout_client.calls[1]["client_reference_id"], first.draft_id)

    def test_missing_idempotency_key_falls_back_to_always_creating_new_draft(self):
        # idempotency_storeを渡しても、payloadにidempotency_keyが無ければ従来どおり
        # 常に新規draftを作成する(後方互換)。
        idempotency_store = InMemoryIdempotencyKeyIndexStore()
        draft_ids = iter(
            [
                "11111111-1111-4111-8111-111111111111",
                "22222222-2222-4222-8222-222222222222",
            ]
        )

        for _ in range(2):
            create_checkout_session_for_event_memo(
                VALID_PAYLOAD,
                self.draft_store,
                self.checkout_client,
                "https://example.run.app",
                now=self.fixed_now,
                draft_id_factory=lambda: next(draft_ids),
                idempotency_store=idempotency_store,
            )

        self.assertEqual(len(self.draft_store._drafts), 2)

    def test_default_draft_id_factory_produces_uuid4_like_value(self):
        result = create_checkout_session_for_event_memo(
            VALID_PAYLOAD,
            self.draft_store,
            self.checkout_client,
            "https://example.run.app",
            now=self.fixed_now,
        )
        # UUID4文字列表現(36文字、ハイフン4個)であることのみ確認する(厳密な
        # バージョン検証はdraft-id-last4-collision-design.mdの既存知見に委ねる)。
        self.assertEqual(len(result.draft_id), 36)
        self.assertEqual(result.draft_id.count("-"), 4)
        self.assertEqual(result.draft_id_last4, result.draft_id[-4:])


class BuildStripeCheckoutSessionParamsTest(unittest.TestCase):
    def test_builds_payment_mode_params_with_inline_price_data(self):
        params = build_stripe_checkout_session_params(
            amount=500,
            currency="jpy",
            client_reference_id="11111111-1111-4111-8111-111111111111",
            success_url="https://example.run.app/result/11111111-1111-4111-8111-111111111111",
            cancel_url="https://example.run.app/",
        )

        self.assertEqual(params["mode"], "payment")
        self.assertEqual(
            params["client_reference_id"],
            "11111111-1111-4111-8111-111111111111",
        )
        self.assertEqual(
            params["success_url"],
            "https://example.run.app/result/11111111-1111-4111-8111-111111111111",
        )
        self.assertEqual(params["cancel_url"], "https://example.run.app/")
        # 事前作成済みPrice IDは使わず、price_dataインラインで金額・商品名を指定する
        # 方式(stripe-checkout-session-params-design.md)。
        self.assertNotIn("price", params["line_items"][0])
        price_data = params["line_items"][0]["price_data"]
        self.assertEqual(price_data["currency"], "jpy")
        self.assertEqual(price_data["unit_amount"], 500)
        self.assertEqual(price_data["product_data"]["name"], STRIPE_PRODUCT_NAME_JA)
        self.assertEqual(params["line_items"][0]["quantity"], 1)

    def test_does_not_include_customer_email(self):
        # checkout-session-success-cancel-url-design.md(フェーズ104)の方針どおり、
        # customer_emailはStripe Checkoutページ標準の入力欄に委ね、paramsには含めない。
        params = build_stripe_checkout_session_params(
            amount=500,
            currency="jpy",
            client_reference_id="draft-1",
            success_url="https://example.run.app/result/draft-1",
            cancel_url="https://example.run.app/",
        )
        self.assertNotIn("customer_email", params)


if __name__ == "__main__":
    unittest.main()
