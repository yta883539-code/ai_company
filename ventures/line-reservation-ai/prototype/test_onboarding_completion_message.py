#!/usr/bin/env python3
"""onboarding_completion_message.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_onboarding_completion_message -v で実行可能。
"""

from __future__ import annotations

import unittest

from onboarding_completion_message import render_onboarding_completion_message


class RenderOnboardingCompletionMessageTests(unittest.TestCase):
    URL = "https://example.com/billing"

    def test_standard_message_includes_url_and_no_auto_charge_note(self):
        text = render_onboarding_completion_message(self.URL)
        self.assertIn(self.URL, text)
        self.assertIn("自動課金されません", text)
        self.assertIn("設定が完了しました", text)

    def test_formal_tone_uses_stronger_honorific(self):
        text = render_onboarding_completion_message(self.URL, tone="formal")
        self.assertIn("お切り替えいただけます", text)

    def test_casual_tone_allows_emoji(self):
        text = render_onboarding_completion_message(self.URL, tone="casual")
        self.assertIn("🎉", text)

    def test_unknown_tone_falls_back_to_standard(self):
        standard_text = render_onboarding_completion_message(self.URL, tone="standard")
        unknown_text = render_onboarding_completion_message(self.URL, tone="nonexistent")
        self.assertEqual(standard_text, unknown_text)

    def test_empty_payment_page_url_raises(self):
        with self.assertRaises(ValueError):
            render_onboarding_completion_message("")

    def test_none_payment_page_url_raises(self):
        with self.assertRaises(ValueError):
            render_onboarding_completion_message(None)

    def test_all_three_tones_are_distinct(self):
        formal = render_onboarding_completion_message(self.URL, tone="formal")
        standard = render_onboarding_completion_message(self.URL, tone="standard")
        casual = render_onboarding_completion_message(self.URL, tone="casual")
        self.assertNotEqual(formal, standard)
        self.assertNotEqual(standard, casual)
        self.assertNotEqual(formal, casual)

    def test_trial_and_paid_plan_words_not_rephrased_across_tones(self):
        for tone in ("formal", "standard", "casual"):
            text = render_onboarding_completion_message(self.URL, tone=tone)
            self.assertIn("トライアル", text)
            self.assertIn("有料プラン", text)


if __name__ == "__main__":
    unittest.main()
