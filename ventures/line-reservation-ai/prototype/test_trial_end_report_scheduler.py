#!/usr/bin/env python3
"""trial_end_report_scheduler.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_trial_end_report_scheduler -v で実行可能。
"""

from __future__ import annotations

import unittest

from trial_end_report_scheduler import (
    TrialUsageSummary,
    render_trial_end_report_message,
)


class TrialUsageSummaryTests(unittest.TestCase):
    def test_estimated_hours_saved_rounds_to_one_decimal(self):
        summary = TrialUsageSummary(booking_count=32, auto_handled_inquiry_count=18)
        # 18件 * 7.5分 = 135分 = 2.25時間 -> round()の浮動小数点丸め(銀行丸め)により2.2時間
        self.assertEqual(summary.estimated_hours_saved, 2.2)

    def test_zero_auto_handled_count_yields_zero_hours(self):
        summary = TrialUsageSummary(booking_count=5, auto_handled_inquiry_count=0)
        self.assertEqual(summary.estimated_hours_saved, 0.0)

    def test_negative_booking_count_raises(self):
        with self.assertRaises(ValueError):
            TrialUsageSummary(booking_count=-1, auto_handled_inquiry_count=0)

    def test_negative_auto_handled_count_raises(self):
        with self.assertRaises(ValueError):
            TrialUsageSummary(booking_count=0, auto_handled_inquiry_count=-1)


class RenderTrialEndReportMessageTests(unittest.TestCase):
    URL = "https://example.com/billing"

    def test_standard_message_includes_all_three_metrics(self):
        summary = TrialUsageSummary(booking_count=32, auto_handled_inquiry_count=18)
        text = render_trial_end_report_message(summary, self.URL)
        self.assertIn("処理した予約件数: 32件", text)
        self.assertIn("自動対応できたお問い合わせ: 18件", text)
        self.assertIn("概算の削減対応時間: 約2.2時間", text)
        self.assertIn(self.URL, text)
        self.assertIn("自動課金されません", text)

    def test_whole_number_hours_render_without_decimal(self):
        # 8件 * 7.5分 = 60分 = 1.0時間 -> "1時間"と表示("1.0時間"にはしない)
        summary = TrialUsageSummary(booking_count=10, auto_handled_inquiry_count=8)
        text = render_trial_end_report_message(summary, self.URL)
        self.assertIn("概算の削減対応時間: 約1時間", text)

    def test_formal_tone_uses_stronger_honorific(self):
        summary = TrialUsageSummary(booking_count=1, auto_handled_inquiry_count=1)
        text = render_trial_end_report_message(summary, self.URL, tone="formal")
        self.assertIn("お選びくださいませ", text)

    def test_casual_tone_allows_emoji(self):
        summary = TrialUsageSummary(booking_count=1, auto_handled_inquiry_count=1)
        text = render_trial_end_report_message(summary, self.URL, tone="casual")
        self.assertIn("🎉", text)

    def test_unknown_tone_falls_back_to_standard(self):
        summary = TrialUsageSummary(booking_count=1, auto_handled_inquiry_count=1)
        standard_text = render_trial_end_report_message(summary, self.URL, tone="standard")
        unknown_text = render_trial_end_report_message(summary, self.URL, tone="nonexistent")
        self.assertEqual(standard_text, unknown_text)


if __name__ == "__main__":
    unittest.main()
