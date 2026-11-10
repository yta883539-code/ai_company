#!/usr/bin/env python3
import unittest

from fan_pass_store import InMemoryFanPassStore
from generation_request_handler import receive_generation_request
from one_time_pass_store import InMemoryOneTimePassStore


class _FakeLlmClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate(self, raw_input: dict) -> dict:
        self.calls.append(raw_input)
        return {"status": "ok", "itinerary_draft": "stub"}


class _FakeGenerationLog:
    def __init__(self) -> None:
        self.recorded: list[str] = []

    def record(self, internal_id: str) -> None:
        self.recorded.append(internal_id)


class ReceiveGenerationRequestTests(unittest.TestCase):
    def test_missing_access_token_returns_400(self) -> None:
        result = receive_generation_request(
            InMemoryFanPassStore(),
            InMemoryOneTimePassStore(),
            _FakeGenerationLog(),
            _FakeLlmClient(),
            None,
            {},
            now=1000,
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "missing_access_token")

    def test_blank_access_token_returns_400(self) -> None:
        result = receive_generation_request(
            InMemoryFanPassStore(),
            InMemoryOneTimePassStore(),
            _FakeGenerationLog(),
            _FakeLlmClient(),
            "   ",
            {},
            now=1000,
        )
        self.assertEqual(result.status_code, 400)

    def test_unknown_access_token_returns_404(self) -> None:
        result = receive_generation_request(
            InMemoryFanPassStore(),
            InMemoryOneTimePassStore(),
            _FakeGenerationLog(),
            _FakeLlmClient(),
            "not-registered",
            {},
            now=1000,
        )
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.error, "unknown_access_token")

    def test_canceled_fan_pass_returns_403(self) -> None:
        store = InMemoryFanPassStore()
        internal_id, access_token = store.create(
            email="fan@example.com",
            stripe_customer_id="cus_1",
            stripe_subscription_id="sub_1",
        )
        store.update_subscription_status(internal_id, status="canceled")
        llm_client = _FakeLlmClient()

        result = receive_generation_request(
            store,
            InMemoryOneTimePassStore(),
            _FakeGenerationLog(),
            llm_client,
            access_token,
            {},
            now=1000,
        )

        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.error, "subscription_canceled")
        self.assertEqual(llm_client.calls, [])

    def test_active_fan_pass_generates_and_records_log(self) -> None:
        store = InMemoryFanPassStore()
        internal_id, access_token = store.create(
            email="fan@example.com",
            stripe_customer_id="cus_2",
            stripe_subscription_id="sub_2",
        )
        llm_client = _FakeLlmClient()
        generation_log = _FakeGenerationLog()

        result = receive_generation_request(
            store,
            InMemoryOneTimePassStore(),
            generation_log,
            llm_client,
            access_token,
            {"venue": "example-hall"},
            now=1000,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.output, {"status": "ok", "itinerary_draft": "stub"})
        self.assertEqual(llm_client.calls, [{"venue": "example-hall"}])
        self.assertEqual(generation_log.recorded, [internal_id])

    def test_one_time_pass_generates_and_marks_consumed(self) -> None:
        store = InMemoryOneTimePassStore()
        internal_id, access_token = store.create(
            stripe_checkout_session_id="cs_1", created_at=1000
        )
        llm_client = _FakeLlmClient()
        generation_log = _FakeGenerationLog()

        result = receive_generation_request(
            InMemoryFanPassStore(),
            store,
            generation_log,
            llm_client,
            access_token,
            {},
            now=1500,
        )

        self.assertEqual(result.status_code, 200)
        self.assertEqual(llm_client.calls, [{}])
        # 都度プランは月次カウント対象外(generation-count-design.md 2節)。
        self.assertEqual(generation_log.recorded, [])
        self.assertIsNotNone(store.get_by_access_token(access_token).consumed_at)
        self.assertEqual(store.get_by_access_token(access_token).consumed_at, 1500)

    def test_already_consumed_one_time_pass_returns_403_without_calling_llm(self) -> None:
        store = InMemoryOneTimePassStore()
        internal_id, access_token = store.create(
            stripe_checkout_session_id="cs_2", created_at=1000
        )
        store.mark_consumed(internal_id, consumed_at=1200)
        llm_client = _FakeLlmClient()

        result = receive_generation_request(
            InMemoryFanPassStore(),
            store,
            _FakeGenerationLog(),
            llm_client,
            access_token,
            {},
            now=1300,
        )

        self.assertEqual(result.status_code, 403)
        self.assertEqual(result.error, "already_consumed")
        self.assertEqual(llm_client.calls, [])

    def test_expired_one_time_pass_returns_404_even_if_not_consumed(self) -> None:
        store = InMemoryOneTimePassStore()
        _internal_id, access_token = store.create(
            stripe_checkout_session_id="cs_3", created_at=1000
        )
        llm_client = _FakeLlmClient()

        result = receive_generation_request(
            InMemoryFanPassStore(),
            store,
            _FakeGenerationLog(),
            llm_client,
            access_token,
            {},
            now=1000 + 24 * 60 * 60,
        )

        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.error, "unknown_access_token")
        self.assertEqual(llm_client.calls, [])

    def test_expired_and_consumed_one_time_pass_returns_404_not_403(self) -> None:
        store = InMemoryOneTimePassStore()
        internal_id, access_token = store.create(
            stripe_checkout_session_id="cs_4", created_at=1000
        )
        store.mark_consumed(internal_id, consumed_at=1100)
        llm_client = _FakeLlmClient()

        result = receive_generation_request(
            InMemoryFanPassStore(),
            store,
            _FakeGenerationLog(),
            llm_client,
            access_token,
            {},
            now=1000 + 24 * 60 * 60,
        )

        # design.md 4節: expiresAt超過はconsumedAtの状態によらず404(期限切れと「そもそも
        # 存在しない」を区別させない)。403より404が優先される。
        self.assertEqual(result.status_code, 404)
        self.assertEqual(result.error, "unknown_access_token")
        self.assertEqual(llm_client.calls, [])


if __name__ == "__main__":
    unittest.main()
