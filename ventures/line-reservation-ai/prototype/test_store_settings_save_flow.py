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
    normalize_closed_dates,
    normalize_faq_info,
    normalize_menus,
    normalize_message_tone,
    normalize_repeat_customer_visit_threshold,
    normalize_weekday_business_hours_raw,
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


class NormalizeMessageToneTest(unittest.TestCase):
    def test_valid_values_pass_through(self):
        self.assertEqual(normalize_message_tone("formal"), "formal")
        self.assertEqual(normalize_message_tone("casual"), "casual")

    def test_invalid_or_missing_falls_back_to_standard(self):
        self.assertEqual(normalize_message_tone("丁寧"), "standard")
        self.assertEqual(normalize_message_tone(None), "standard")


class NormalizeRepeatCustomerVisitThresholdTest(unittest.TestCase):
    def test_extracts_digits_from_display_string(self):
        self.assertEqual(normalize_repeat_customer_visit_threshold("5回"), 5)

    def test_unparseable_falls_back_to_default_three(self):
        self.assertEqual(normalize_repeat_customer_visit_threshold("未定"), 3)
        self.assertEqual(normalize_repeat_customer_visit_threshold(None), 3)


class NormalizeFaqInfoTest(unittest.TestCase):
    def test_full_payload_is_normalized(self):
        faq_info = normalize_faq_info(
            {
                "faq_address": "  ○○駅から徒歩5分  ",
                "faq_parking_available": "あり",
                "faq_parking_capacity_raw": "3台",
                "faq_payment_methods": ["現金", "クレジット", "仮想通貨"],
            }
        )
        self.assertEqual(
            faq_info,
            {
                "address": "○○駅から徒歩5分",
                "parking": "あり(3台)",
                "paymentMethods": ["現金", "クレジット"],
            },
        )

    def test_parking_without_capacity_still_recorded_as_available(self):
        faq_info = normalize_faq_info(
            {"faq_parking_available": "あり", "faq_parking_capacity_raw": "未定"}
        )
        self.assertEqual(faq_info["parking"], "あり")

    def test_no_parking_is_recorded(self):
        faq_info = normalize_faq_info({"faq_parking_available": "なし"})
        self.assertEqual(faq_info["parking"], "なし")

    def test_empty_payload_leaves_fields_blank_not_erroring(self):
        faq_info = normalize_faq_info({})
        self.assertEqual(
            faq_info, {"address": "", "parking": "", "paymentMethods": []}
        )


class NormalizeWeekdayBusinessHoursRawTest(unittest.TestCase):
    def test_string_and_int_weekday_keys_are_both_accepted(self):
        result = normalize_weekday_business_hours_raw(
            {"weekday_business_hours_raw": {"5": "10:00-15:00", 6: "定休日"}}
        )
        self.assertEqual(result, {5: "10:00-15:00", 6: "定休日"})

    def test_out_of_range_and_non_integer_weekday_keys_are_dropped(self):
        result = normalize_weekday_business_hours_raw(
            {
                "weekday_business_hours_raw": {
                    "7": "10:00-15:00",
                    "-1": "10:00-15:00",
                    "月曜": "9:00-19:00",
                }
            }
        )
        self.assertEqual(result, {})

    def test_blank_or_non_string_values_are_dropped(self):
        result = normalize_weekday_business_hours_raw(
            {"weekday_business_hours_raw": {"0": "", "1": "   ", "2": 900}}
        )
        self.assertEqual(result, {})

    def test_toggle_off_or_missing_field_returns_empty_dict(self):
        self.assertEqual(normalize_weekday_business_hours_raw({}), {})
        self.assertEqual(
            normalize_weekday_business_hours_raw(
                {"weekday_business_hours_raw": "10:00-19:00"}
            ),
            {},
        )


class NormalizeClosedDatesTest(unittest.TestCase):
    def test_valid_dates_are_kept_in_order(self):
        result = normalize_closed_dates(
            {"closed_dates": ["2026-09-15", "2026-12-31"]}
        )
        self.assertEqual(result, ["2026-09-15", "2026-12-31"])

    def test_duplicate_dates_are_deduplicated_keeping_first_occurrence(self):
        result = normalize_closed_dates(
            {"closed_dates": ["2026-09-15", "2026-09-15", "2026-12-31"]}
        )
        self.assertEqual(result, ["2026-09-15", "2026-12-31"])

    def test_blank_and_non_string_entries_are_dropped(self):
        result = normalize_closed_dates(
            {"closed_dates": ["2026-09-15", "", "   ", None, 20260915]}
        )
        self.assertEqual(result, ["2026-09-15"])

    def test_missing_or_non_list_field_returns_empty_list(self):
        self.assertEqual(normalize_closed_dates({}), [])
        self.assertEqual(
            normalize_closed_dates({"closed_dates": "2026-09-15"}), []
        )


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

    def test_writes_message_tone_repeat_threshold_and_faq_info_to_store(self):
        self._call(
            payload=_complete_payload(
                message_tone_raw="formal",
                repeat_customer_visit_threshold_raw="5回",
                faq_address="○○駅から徒歩5分",
                faq_parking_available="あり",
                faq_parking_capacity_raw="3",
                faq_payment_methods=["現金"],
            )
        )
        self.assertEqual(self.store.get_message_tone("Uowner123"), "formal")
        self.assertEqual(
            self.store.get_repeat_customer_visit_threshold("Uowner123"), 5
        )
        self.assertEqual(
            self.store.get_faq_info("Uowner123"),
            {
                "address": "○○駅から徒歩5分",
                "parking": "あり(3台)",
                "paymentMethods": ["現金"],
            },
        )

    def test_writes_weekday_business_hours_raw_and_closed_dates_to_store(self):
        result = self._call(
            payload=_complete_payload(
                weekday_business_hours_raw={"5": "10:00-15:00"},
                closed_dates=["2026-09-15", "2026-09-15"],
            )
        )
        self.assertEqual(
            self.store.get_weekday_business_hours_raw("Uowner123"),
            {5: "10:00-15:00"},
        )
        self.assertEqual(
            self.store.get_closed_dates("Uowner123"), ["2026-09-15"]
        )
        self.assertEqual(result.weekday_business_hours_raw, {5: "10:00-15:00"})
        self.assertEqual(result.closed_dates, ["2026-09-15"])

    def test_optional_fields_default_when_omitted(self):
        result = self._call()
        self.assertEqual(result.message_tone, "standard")
        self.assertEqual(result.repeat_customer_visit_threshold, 3)
        self.assertEqual(
            result.faq_info, {"address": "", "parking": "", "paymentMethods": []}
        )
        self.assertEqual(result.weekday_business_hours_raw, {})
        self.assertEqual(result.closed_dates, [])
        self.assertEqual(self.store.get_message_tone("Uowner123"), "standard")

    def test_optional_fields_do_not_affect_dispatch_judgment(self):
        result = self._call(
            payload=_complete_payload(
                closed_weekdays=[0, 1, 2, 3, 4, 5, 6],
                message_tone_raw="formal",
                repeat_customer_visit_threshold_raw="10回",
            )
        )
        self.assertFalse(result.business_hours_configured)
        self.assertFalse(result.onboarding_completion_message_dispatched)
        # 判定には使われないが、書き込み自体は行われる。
        self.assertEqual(self.store.get_message_tone("Uowner123"), "formal")

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
