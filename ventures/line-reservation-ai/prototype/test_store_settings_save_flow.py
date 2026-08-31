#!/usr/bin/env python3
"""store_settings_save_flow.pyの単体テスト。
store-settings-save-flow-design.mdで設計した、owner-settings-wireframe.mdの保存処理から
オンボーディング完了判定への結線を検証する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import InMemoryLinePushClient  # noqa: E402
from store_settings_save_flow import (  # noqa: E402
    InMemoryStoreSettingsStore,
    handle_store_settings_submission,
    normalize_menus,
)


def _complete_payload(**overrides):
    payload = dict(
        user_id="Uowner123",
        closed_weekdays=[6],
        business_hours_raw="10:00-19:00",
        slot_interval_minutes_raw="30分",
        concurrent_capacity_raw="1",
        menus=[{"name": "カット", "duration_minutes": 60}],
    )
    payload.update(overrides)
    return payload


class NormalizeMenusTest(unittest.TestCase):
    def test_drops_menus_with_empty_or_missing_name(self):
        normalized = normalize_menus(
            [
                {"name": "カット", "duration_minutes": 60},
                {"name": "  ", "duration_minutes": 30},
                {"duration_minutes": 30},
                "not-a-dict",
            ]
        )
        self.assertEqual(normalized, [{"name": "カット", "duration_minutes": 60}])

    def test_non_list_input_returns_empty_list(self):
        self.assertEqual(normalize_menus(None), [])
        self.assertEqual(normalize_menus("カット"), [])


class HandleStoreSettingsSubmissionTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStoreSettingsStore()
        self.push_client = InMemoryLinePushClient()

    def _call(self, payload=None, **kwargs):
        params = dict(
            payload=payload if payload is not None else _complete_payload(),
            store=self.store,
            payment_page_url="https://example.com/pay/Uowner123",
            push_client=self.push_client,
        )
        params.update(kwargs)
        return handle_store_settings_submission(**params)

    def test_rejects_missing_user_id(self):
        result = self._call(payload=_complete_payload(user_id=""))
        self.assertFalse(result.ok)
        self.assertIn("user_id", result.error)
        self.assertEqual(self.push_client.sent, [])

    def test_rejects_non_list_closed_weekdays(self):
        result = self._call(payload=_complete_payload(closed_weekdays="6"))
        self.assertFalse(result.ok)
        self.assertIn("closed_weekdays", result.error)

    def test_writes_normalized_fields_to_store(self):
        self._call()
        self.assertEqual(
            self.store.get_business_hours_raw("Uowner123"), "10:00-19:00"
        )
        self.assertEqual(self.store.get_closed_weekdays("Uowner123"), [6])
        self.assertEqual(self.store.get_slot_interval_minutes("Uowner123"), 30)
        self.assertEqual(self.store.get_concurrent_capacity("Uowner123"), 1)
        self.assertEqual(
            self.store.get_menus("Uowner123"),
            [{"name": "カット", "duration_minutes": 60}],
        )

    def test_dispatches_onboarding_completion_message_when_first_complete(self):
        result = self._call()
        self.assertTrue(result.ok)
        self.assertTrue(result.business_hours_configured)
        self.assertEqual(result.slot_interval_minutes, 30)
        self.assertEqual(result.concurrent_capacity, 1)
        self.assertEqual(result.menu_count, 1)
        self.assertTrue(result.onboarding_completion_message_dispatched)
        self.assertEqual(len(self.push_client.sent), 1)

    def test_does_not_dispatch_when_all_days_closed(self):
        result = self._call(
            payload=_complete_payload(closed_weekdays=[0, 1, 2, 3, 4, 5, 6])
        )
        self.assertFalse(result.business_hours_configured)
        self.assertFalse(result.onboarding_completion_message_dispatched)
        self.assertEqual(self.push_client.sent, [])

    def test_does_not_dispatch_when_menus_empty(self):
        result = self._call(payload=_complete_payload(menus=[]))
        self.assertFalse(result.onboarding_completion_message_dispatched)
        self.assertEqual(self.push_client.sent, [])

    def test_unparseable_slot_interval_is_treated_as_unset_but_still_saved_fields(
        self,
    ):
        result = self._call(
            payload=_complete_payload(slot_interval_minutes_raw="未定")
        )
        self.assertIsNone(result.slot_interval_minutes)
        self.assertFalse(result.onboarding_completion_message_dispatched)
        # 予約枠の間隔以外の項目は正しく保存され続ける(部分的な入力ミスで
        # 他の設定項目まで巻き込んで失敗しない、design 5節の全体上書き方針とは別軸の話)。
        self.assertEqual(self.store.get_menus("Uowner123"), [
            {"name": "カット", "duration_minutes": 60}
        ])

    def test_does_not_dispatch_twice_for_same_store(self):
        self._call()
        second_push_client = InMemoryLinePushClient()
        result_again = self._call(push_client=second_push_client)
        self.assertFalse(result_again.onboarding_completion_message_dispatched)
        self.assertEqual(second_push_client.sent, [])


if __name__ == "__main__":
    unittest.main()
