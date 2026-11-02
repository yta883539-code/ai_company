#!/usr/bin/env python3
"""
operational-message-templates-draft.md(フェーズ81)で確定した運用メッセージ系
テンプレート(operational_message_templates.TEMPLATES)に対し、post_generation_checks.py
のEMOJI_PATTERN(厳守事項9の絵文字検出用正規表現)を再利用して絵文字不使用を検証する。
"""

import unittest

from operational_message_templates import TEMPLATES
from post_generation_checks import EMOJI_PATTERN


class TestOperationalMessageTemplatesNoEmoji(unittest.TestCase):
    def test_all_templates_have_no_emoji(self):
        for name, text in TEMPLATES.items():
            with self.subTest(template=name):
                self.assertIsNone(
                    EMOJI_PATTERN.search(text),
                    f"{name}: 絵文字が含まれています(厳守事項9違反の疑い)",
                )


if __name__ == "__main__":
    unittest.main()
