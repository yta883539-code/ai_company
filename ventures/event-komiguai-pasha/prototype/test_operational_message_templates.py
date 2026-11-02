#!/usr/bin/env python3
"""
operational-message-templates-draft.md(フェーズ81)で確定した運用メッセージ系
テンプレート(operational_message_templates.TEMPLATES)に対し、post_generation_checks.py
のEMOJI_PATTERN(厳守事項9の絵文字検出用正規表現)・HEADING_BRACKET_PATTERN
(tone-and-manner-guideline.md方針4の見出し記法【】検出用正規表現、フェーズ82)を
再利用して絵文字不使用・見出し記法不使用を検証する。
"""

import unittest

from operational_message_templates import TEMPLATES
from post_generation_checks import EMOJI_PATTERN, HEADING_BRACKET_PATTERN


class TestOperationalMessageTemplatesNoEmoji(unittest.TestCase):
    def test_all_templates_have_no_emoji(self):
        for name, text in TEMPLATES.items():
            with self.subTest(template=name):
                self.assertIsNone(
                    EMOJI_PATTERN.search(text),
                    f"{name}: 絵文字が含まれています(厳守事項9違反の疑い)",
                )


class TestOperationalMessageTemplatesNoHeadingBrackets(unittest.TestCase):
    def test_all_templates_have_no_heading_brackets(self):
        for name, text in TEMPLATES.items():
            with self.subTest(template=name):
                self.assertIsNone(
                    HEADING_BRACKET_PATTERN.search(text),
                    f"{name}: 見出し記法【】が含まれています(tone-and-manner-guideline.md方針4違反の疑い)",
                )


if __name__ == "__main__":
    unittest.main()
