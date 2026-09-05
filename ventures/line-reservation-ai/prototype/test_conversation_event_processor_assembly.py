#!/usr/bin/env python3
"""conversation_event_processor_assembly.pyの単体テスト。
conversation-event-processor-assembly-design.md 4節で残っていた最上位の組み立て関数
build_conversation_event_processor_for_payload()を検証する。"""

import sys
import unittest
import unittest.mock
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    ConversationEventProcessor,
    InMemoryLinePushClient,
    MissingDestinationError,
)
from conversation_event_processor_assembly import (  # noqa: E402
    build_conversation_event_processor_for_payload,
    get_process_conversation_event_runtime_dependencies,
    main,
    process_conversation_event_from_payload,
)
from store_settings_save_flow import InMemoryStoreSettingsStore  # noqa: E402


def _payload(destination: str = "store-1") -> dict:
    return {"destination": destination, "events": []}


def _new_booking_event(destination: str = "store-1") -> dict:
    return {
        "destination": destination,
        "type": "message",
        "source": {"userId": "U1"},
        "message": {"text": "来週土曜カットでお願いします"},
    }


def _new_booking_llm_call() -> dict:
    return {
        "intent": "new_booking",
        "name": None,
        "menu": "カット",
        "datetime_candidate": "来週土曜の空き候補",
    }


class BuildConversationEventProcessorForPayloadTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStoreSettingsStore()
        self.store.set_business_hours_raw("store-1", "10:00-19:00")
        self.store.set_slot_interval_minutes("store-1", 30)
        self.store.set_owner_user_id("store-1", "U-owner")
        self.store.set_menu_durations("store-1", {"カット": 30})
        self.push_client = InMemoryLinePushClient()

    def test_returns_processor_wired_from_store_id(self):
        processor = build_conversation_event_processor_for_payload(
            _payload(), self.store, self.push_client
        )
        self.assertIsInstance(processor, ConversationEventProcessor)
        self.assertEqual(processor._store_id, "store-1")
        self.assertEqual(processor._owner_user_id, "U-owner")
        self.assertEqual(processor._menu_durations, {"カット": 30})

    def test_missing_business_hours_raw_raises(self):
        # business_hours_rawを設定していない未オンボーディング店舗
        self.store.set_owner_user_id("store-2", "U-owner-2")
        with self.assertRaises(ValueError):
            build_conversation_event_processor_for_payload(
                _payload("store-2"), self.store, self.push_client
            )

    def test_missing_destination_raises(self):
        with self.assertRaises(MissingDestinationError):
            build_conversation_event_processor_for_payload(
                {"events": []}, self.store, self.push_client
            )

    def test_processor_can_process_a_new_booking_message(self):
        processor = build_conversation_event_processor_for_payload(
            _payload(), self.store, self.push_client
        )
        now = datetime(2026, 8, 3, 10, 0)  # 月曜
        event = {"source": {"userId": "U1"}, "message": {"text": "来週土曜カットでお願いします"}}

        def llm_call() -> dict:
            return {
                "intent": "new_booking",
                "name": None,
                "menu": "カット",
                "datetime_candidate": "来週土曜の空き候補",
            }

        result = processor.process(event, llm_call, now)
        self.assertIsNotNone(result)
        self.assertTrue(self.push_client.sent)


class ProcessConversationEventFromPayloadTest(unittest.TestCase):
    """process_conversation_event_from_payload()(フェーズ続き196)の検証。
    build_conversation_event_processor_for_payload()とhandle_process_conversation_event()を
    1件のpayloadから順に呼び出すCloud Function B本体の配線。"""

    def setUp(self):
        self.store = InMemoryStoreSettingsStore()
        self.store.set_business_hours_raw("store-1", "10:00-19:00")
        self.store.set_slot_interval_minutes("store-1", 30)
        self.store.set_owner_user_id("store-1", "U-owner")
        self.store.set_menu_durations("store-1", {"カット": 30})
        self.push_client = InMemoryLinePushClient()
        self.now = datetime(2026, 8, 3, 10, 0)  # 月曜

    def test_message_event_returns_200_and_pushes(self):
        result = process_conversation_event_from_payload(
            _new_booking_event(), self.store, self.push_client, _new_booking_llm_call, self.now
        )
        self.assertEqual(result.status_code, 200)
        self.assertTrue(self.push_client.sent)

    def test_missing_destination_returns_400_without_raising(self):
        payload = {"type": "message", "source": {"userId": "U1"}, "message": {"text": "こんにちは"}}
        result = process_conversation_event_from_payload(
            payload, self.store, self.push_client, _new_booking_llm_call, self.now
        )
        self.assertEqual(result.status_code, 400)

    def test_unonboarded_store_returns_400_without_raising(self):
        self.store.set_owner_user_id("store-2", "U-owner-2")
        result = process_conversation_event_from_payload(
            _new_booking_event("store-2"), self.store, self.push_client, _new_booking_llm_call, self.now
        )
        self.assertEqual(result.status_code, 400)

    def test_unknown_event_type_returns_200_ignored(self):
        payload = {"destination": "store-1", "type": "postback"}
        result = process_conversation_event_from_payload(
            payload, self.store, self.push_client, _new_booking_llm_call, self.now
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.detail, "ignored")


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ
    (checkout_session._StubFlaskRequest・stripe_webhook_entry_point._StubFlaskRequestと
    対称。本エンドポイントはCloud Tasksからのpush配信を受けるためJSONボディのみを扱う)。"""

    def __init__(self, json_body):
        self._json_body = json_body

    def get_json(self, silent: bool = False):
        return self._json_body


class GetProcessConversationEventRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_expected_keys(self):
        deps = get_process_conversation_event_runtime_dependencies()
        self.assertEqual(set(deps.keys()), {"store", "push_client", "llm_call"})
        self.assertIsInstance(deps["store"], InMemoryStoreSettingsStore)
        self.assertIsInstance(deps["push_client"], InMemoryLinePushClient)

    def test_llm_call_placeholder_raises_not_implemented(self):
        deps = get_process_conversation_event_runtime_dependencies()
        with self.assertRaises(NotImplementedError):
            deps["llm_call"]()


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント)のテスト(フェーズ続き197)。
    process_conversation_event_from_payload()自体の分岐は
    ProcessConversationEventFromPayloadTestで既にカバー済みのため、ここではCloud Tasksの
    JSONボディ取り出し配線・欠落時の空dictフォールバックのみを検証する。"""

    def test_missing_destination_payload_returns_400(self):
        request = _StubFlaskRequest({"type": "message"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 400)

    def test_empty_body_does_not_raise_and_returns_400(self):
        request = _StubFlaskRequest(None)

        response_body, status_code = main(request)

        self.assertEqual(status_code, 400)

    def test_llm_call_not_implemented_surfaces_as_500(self):
        payload = {
            "destination": "store-1",
            "type": "message",
            "source": {"userId": "U1"},
            "message": {"text": "来週土曜カットでお願いします"},
        }
        store = InMemoryStoreSettingsStore()
        store.set_business_hours_raw("store-1", "10:00-19:00")
        store.set_slot_interval_minutes("store-1", 30)
        store.set_owner_user_id("store-1", "U-owner")
        store.set_menu_durations("store-1", {"カット": 30})

        # get_process_conversation_event_runtime_dependencies()と同じ組み合わせのうち
        # storeのみ差し替えて、未実装のllm_callがdispatch経路で実際に呼ばれることを確認する。
        deps = get_process_conversation_event_runtime_dependencies()
        deps["store"] = store
        with unittest.mock.patch(
            "conversation_event_processor_assembly."
            "get_process_conversation_event_runtime_dependencies",
            return_value=deps,
        ):
            request = _StubFlaskRequest(payload)
            response_body, status_code = main(request)

        self.assertEqual(status_code, 500)
        self.assertIn("llm_call is not implemented yet", response_body)


if __name__ == "__main__":
    unittest.main()
