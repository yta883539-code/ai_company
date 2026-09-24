#!/usr/bin/env python3
import unittest

from chatbot_intent_router import append_faq_followup_hint, render_faq_guidance_message


class RenderFaqGuidanceMessageTests(unittest.TestCase):
    def test_mentions_faq_command(self):
        self.assertIn("FAQ", render_faq_guidance_message())

    def test_is_non_empty_and_stable(self):
        self.assertTrue(render_faq_guidance_message())
        self.assertEqual(render_faq_guidance_message(), render_faq_guidance_message())

    def test_does_not_include_item_specific_answer_text(self):
        # 設計上の要点2: 項目別のFAQ回答文(owner_faq_router.pyのQ1〜Q7本文)は含めず、
        # コマンドへの誘導文のみとする。
        message = render_faq_guidance_message()
        self.assertNotIn("トライアルはいつまで", message)


class AppendFaqFollowupHintTests(unittest.TestCase):
    def test_appends_hint_after_original_text(self):
        result = append_faq_followup_hint("完了報告書を生成しました。")
        self.assertTrue(result.startswith("完了報告書を生成しました。"))
        self.assertIn("FAQ", result)

    def test_preserves_original_text_unchanged(self):
        original = "本文"
        result = append_faq_followup_hint(original)
        self.assertNotEqual(result, original)
        self.assertIn(original, result)

    def test_empty_reply_text_still_appends_hint(self):
        result = append_faq_followup_hint("")
        self.assertIn("FAQ", result)


if __name__ == "__main__":
    unittest.main()
