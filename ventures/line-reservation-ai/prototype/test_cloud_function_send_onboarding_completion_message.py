#!/usr/bin/env python3
"""cloud_function_send_onboarding_completion_message.pyの単体テスト。
onboarding-completion-message-design.md「残課題」の判定→整形→送信の配線を検証する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
)
from cloud_function_send_onboarding_completion_message import (  # noqa: E402
    handle_onboarding_completion_message_dispatch,
)
from store_profile_store import InMemoryStoreProfileStore  # noqa: E402


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated delivery failure")


class HandleOnboardingCompletionMessageDispatchTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStoreProfileStore()
        self.push_client = InMemoryLinePushClient()

    def _call(self, **overrides):
        params = dict(
            user_id="Uowner123",
            business_hours_configured=True,
            slot_interval_minutes=30,
            concurrent_capacity=1,
            menu_count=1,
            store=self.store,
            payment_page_url="https://example.com/pay/Uowner123",
            push_client=self.push_client,
        )
        params.update(overrides)
        return handle_onboarding_completion_message_dispatch(**params)

    def test_sends_message_when_required_fields_first_complete(self):
        dispatched = self._call()
        self.assertTrue(dispatched)
        self.assertEqual(len(self.push_client.sent), 1)
        user_id, text = self.push_client.sent[0]
        self.assertEqual(user_id, "Uowner123")
        self.assertIn("設定が完了しました", text)
        self.assertIn("https://example.com/pay/Uowner123", text)

    def test_does_not_send_when_fields_incomplete(self):
        dispatched = self._call(menu_count=0)
        self.assertFalse(dispatched)
        self.assertEqual(self.push_client.sent, [])

    def test_does_not_send_twice_for_same_store(self):
        self._call()
        dispatched_again = self._call()
        self.assertFalse(dispatched_again)
        self.assertEqual(len(self.push_client.sent), 1)

    def test_respects_message_tone(self):
        self._call(tone="casual")
        _, text = self.push_client.sent[0]
        self.assertIn("設定完了しました🎉", text)

    def test_send_failure_propagates_and_flag_stays_marked(self):
        self.push_client = _FailingLinePushClient()
        with self.assertRaises(LinePushDeliveryError):
            self._call()
        self.assertTrue(
            self.store.is_onboarding_completion_message_sent("Uowner123")
        )
        second_client = InMemoryLinePushClient()
        dispatched_again = self._call(push_client=second_client)
        self.assertFalse(dispatched_again)
        self.assertEqual(second_client.sent, [])


if __name__ == "__main__":
    unittest.main()
