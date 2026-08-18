#!/usr/bin/env python3
"""dunning_notification_scheduler.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_dunning_notification_scheduler -v で実行可能。
"""

from __future__ import annotations

import unittest
from datetime import datetime

from dunning_notification_scheduler import (
    DUNNING_CONFIG_A_7DAYS,
    DUNNING_CONFIG_B_14DAYS,
    DunningConfig,
    compute_dunning_schedule,
    render_dunning_message,
    render_payment_confirmed_in_grace_message,
    render_recovery_message,
)


class ComputeDunningScheduleTests(unittest.TestCase):
    def test_config_a_produces_detected_reminder_suspended(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)
        self.assertEqual([e.event_type for e in events], ["detected", "reminder", "suspended"])
        self.assertEqual(events[1].label, "final")
        self.assertEqual(events[1].scheduled_at, datetime(2026, 8, 21, 10, 0))  # 検知から4日後
        self.assertEqual(events[2].scheduled_at, datetime(2026, 8, 24, 10, 0))  # 検知から7日後

    def test_config_b_produces_midpoint_and_final_reminders(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)
        self.assertEqual(
            [e.event_type for e in events], ["detected", "reminder", "reminder", "suspended"]
        )
        self.assertEqual([e.label for e in events if e.event_type == "reminder"], ["midpoint", "final"])
        self.assertEqual(events[1].scheduled_at, datetime(2026, 8, 24, 10, 0))  # 検知から7日後
        self.assertEqual(events[2].scheduled_at, datetime(2026, 8, 28, 10, 0))  # 検知から11日後
        self.assertEqual(events[3].scheduled_at, datetime(2026, 8, 31, 10, 0))  # 検知から14日後

    def test_reminder_offsets_must_precede_grace_period(self):
        with self.assertRaises(ValueError):
            DunningConfig(name="invalid", grace_period_days=7, reminder_offsets=(7,))

    def test_reminder_offsets_must_be_ascending(self):
        with self.assertRaises(ValueError):
            DunningConfig(name="invalid", grace_period_days=14, reminder_offsets=(11, 7))

    def test_reminder_offsets_must_not_be_empty(self):
        with self.assertRaises(ValueError):
            DunningConfig(name="invalid", grace_period_days=7, reminder_offsets=())


class RenderDunningMessageTests(unittest.TestCase):
    URL = "https://example.com/billing"

    def test_detected_message_uses_config_grace_period(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)[0]
        text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL)
        self.assertIn("7日以内にお支払い方法", text)
        self.assertIn(self.URL, text)

    def test_detected_message_reflects_14day_config(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)[0]
        text = render_dunning_message(event, DUNNING_CONFIG_B_14DAYS, self.URL)
        self.assertIn("14日以内にお支払い方法", text)

    def test_config_a_final_reminder_says_3_days(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)[1]
        text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL)
        self.assertIn("このままですと3日後に新規のご予約受付", text)

    def test_config_b_final_reminder_also_says_3_days(self):
        # 11日後(終了3日前)に送るリマインドなので、猶予期間が14日でも文言は「3日後」のまま。
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)
        final_reminder = next(e for e in events if e.event_type == "reminder" and e.label == "final")
        text = render_dunning_message(final_reminder, DUNNING_CONFIG_B_14DAYS, self.URL)
        self.assertIn("このままですと3日後に新規のご予約受付", text)

    def test_config_b_midpoint_reminder_shows_elapsed_and_remaining_days(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)
        midpoint = next(e for e in events if e.event_type == "reminder" and e.label == "midpoint")
        text = render_dunning_message(midpoint, DUNNING_CONFIG_B_14DAYS, self.URL)
        self.assertIn("検知から7日が経過", text)
        self.assertIn("猶予期間は残り7日", text)

    def test_config_a_has_no_midpoint_reminder(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        events = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)
        labels = [e.label for e in events if e.event_type == "reminder"]
        self.assertNotIn("midpoint", labels)

    def test_suspended_message_is_config_independent(self):
        detected_at = datetime(2026, 8, 17, 10, 0)
        event_a = compute_dunning_schedule(detected_at, DUNNING_CONFIG_A_7DAYS)[-1]
        event_b = compute_dunning_schedule(detected_at, DUNNING_CONFIG_B_14DAYS)[-1]
        self.assertEqual(
            render_dunning_message(event_a, DUNNING_CONFIG_A_7DAYS, self.URL),
            render_dunning_message(event_b, DUNNING_CONFIG_B_14DAYS, self.URL),
        )

    def test_recovery_message_has_no_placeholders_and_takes_no_config(self):
        text = render_recovery_message()
        self.assertNotIn("{", text)
        self.assertIn("お支払いを確認しました", text)

    def test_in_grace_message_confirms_payment_without_claiming_resumption(self):
        text = render_payment_confirmed_in_grace_message()
        self.assertNotIn("{", text)
        self.assertIn("お支払いを確認しました", text)
        self.assertNotIn("再開", text)


class ToneVariantTests(unittest.TestCase):
    """message-tone-variants.md準拠のトーン出し分け(formal/standard/casual)の検証。"""

    URL = "https://example.com/billing"

    def _events(self, config):
        return compute_dunning_schedule(datetime(2026, 8, 17, 10, 0), config)

    def test_unknown_tone_falls_back_to_standard(self):
        event = self._events(DUNNING_CONFIG_A_7DAYS)[0]
        standard_text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL, tone="standard")
        unknown_text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL, tone="polite")
        self.assertEqual(standard_text, unknown_text)

    def test_formal_tone_has_no_emoji_and_no_exclamation(self):
        emoji_chars = ("🙏", "🙌")
        for event in self._events(DUNNING_CONFIG_B_14DAYS):
            text = render_dunning_message(event, DUNNING_CONFIG_B_14DAYS, self.URL, tone="formal")
            self.assertNotIn("!", text)
            self.assertFalse(any(e in text for e in emoji_chars))
        for formal_text in (
            render_recovery_message(tone="formal"),
            render_payment_confirmed_in_grace_message(tone="formal"),
        ):
            self.assertNotIn("!", formal_text)
            self.assertFalse(any(e in formal_text for e in emoji_chars))

    def test_casual_tone_has_at_most_one_emoji_and_one_exclamation_per_message(self):
        emoji_chars = ("🙏", "🙌")
        for event in self._events(DUNNING_CONFIG_B_14DAYS):
            text = render_dunning_message(event, DUNNING_CONFIG_B_14DAYS, self.URL, tone="casual")
            self.assertLessEqual(text.count("!"), 1)
            self.assertLessEqual(sum(text.count(e) for e in emoji_chars), 1)
        for casual_text in (
            render_recovery_message(tone="casual"),
            render_payment_confirmed_in_grace_message(tone="casual"),
        ):
            self.assertLessEqual(casual_text.count("!"), 1)
            self.assertLessEqual(sum(casual_text.count(e) for e in emoji_chars), 1)

    def test_tone_does_not_change_variable_content(self):
        # 猶予日数・URL等の実質情報はトーンに関わらず同じでなければならない(message-tone-variants.md
        # 「3トーン共通で変えてはいけないもの」)。
        event = self._events(DUNNING_CONFIG_B_14DAYS)[0]
        for tone in ("formal", "standard", "casual"):
            text = render_dunning_message(event, DUNNING_CONFIG_B_14DAYS, self.URL, tone=tone)
            self.assertIn("14日以内にお支払い方法", text)
            self.assertIn(self.URL, text)

    def test_default_tone_is_standard(self):
        event = self._events(DUNNING_CONFIG_A_7DAYS)[0]
        default_text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL)
        standard_text = render_dunning_message(event, DUNNING_CONFIG_A_7DAYS, self.URL, tone="standard")
        self.assertEqual(default_text, standard_text)
        self.assertEqual(render_recovery_message(), render_recovery_message(tone="standard"))
        self.assertEqual(
            render_payment_confirmed_in_grace_message(),
            render_payment_confirmed_in_grace_message(tone="standard"),
        )


if __name__ == "__main__":
    unittest.main()
