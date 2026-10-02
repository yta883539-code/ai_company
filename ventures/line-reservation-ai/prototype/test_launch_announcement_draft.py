#!/usr/bin/env python3
"""launch_announcement_draft.pyの自動テスト(標準ライブラリのみ)。
python3 -m unittest test_launch_announcement_draft -v で実行可能。
"""

from __future__ import annotations

import unittest

from launch_announcement_draft import (
    FRIEND_ADD_URL_PLACEHOLDER,
    is_launch_announcement_trigger,
    render_launch_announcement_pop,
    render_launch_announcement_sns,
)

STORE_NAME = "Hair Salon Lino"
URL = "https://line.me/R/ti/p/@example-lino"


class RenderLaunchAnnouncementPopTests(unittest.TestCase):
    def test_standard_pop_includes_store_name_and_url(self):
        text = render_launch_announcement_pop(STORE_NAME, URL)
        self.assertIn(STORE_NAME, text)
        self.assertIn(URL, text)

    def test_unknown_tone_falls_back_to_standard(self):
        standard_text = render_launch_announcement_pop(STORE_NAME, URL, tone="standard")
        unknown_text = render_launch_announcement_pop(STORE_NAME, URL, tone="nonexistent")
        self.assertEqual(standard_text, unknown_text)

    def test_all_three_tones_are_distinct(self):
        texts = {
            tone: render_launch_announcement_pop(STORE_NAME, URL, tone=tone)
            for tone in ("formal", "standard", "casual")
        }
        self.assertEqual(len(set(texts.values())), 3)

    def test_empty_store_name_raises(self):
        with self.assertRaises(ValueError):
            render_launch_announcement_pop("", URL)

    def test_empty_friend_add_url_raises(self):
        with self.assertRaises(ValueError):
            render_launch_announcement_pop(STORE_NAME, "")


class RenderLaunchAnnouncementSnsTests(unittest.TestCase):
    def test_standard_sns_includes_generic_and_brand_hashtags(self):
        text = render_launch_announcement_sns(STORE_NAME, URL)
        self.assertIn("#LINE予約", text)
        self.assertIn("#ネット予約", text)
        self.assertIn("#HairSalonLino", text)

    def test_brand_hashtag_strips_spaces(self):
        text = render_launch_announcement_sns("さくら 整体院", URL)
        self.assertIn("#さくら整体院", text)

    def test_unknown_tone_falls_back_to_standard(self):
        standard_text = render_launch_announcement_sns(STORE_NAME, URL, tone="standard")
        unknown_text = render_launch_announcement_sns(STORE_NAME, URL, tone="nonexistent")
        self.assertEqual(standard_text, unknown_text)

    def test_all_three_tones_are_distinct(self):
        texts = {
            tone: render_launch_announcement_sns(STORE_NAME, URL, tone=tone)
            for tone in ("formal", "standard", "casual")
        }
        self.assertEqual(len(set(texts.values())), 3)

    def test_empty_store_name_raises(self):
        with self.assertRaises(ValueError):
            render_launch_announcement_sns("", URL)

    def test_empty_friend_add_url_raises(self):
        with self.assertRaises(ValueError):
            render_launch_announcement_sns(STORE_NAME, "")

    def test_no_region_hashtag_is_included_when_region_name_omitted(self):
        # design 4.2節: region_name省略時(既定値は空文字列)は従来通り地域タグを含めない。
        text = render_launch_announcement_sns(STORE_NAME, URL)
        hashtags = [word for word in text.split() if word.startswith("#")]
        self.assertEqual(len(hashtags), 3)

    def test_region_hashtag_is_appended_when_region_name_given(self):
        # design 9節: region_nameを渡すと地域タグが末尾に追加される。
        text = render_launch_announcement_sns(STORE_NAME, URL, region_name="渋谷")
        self.assertIn("#渋谷", text)
        hashtags = [word for word in text.split() if word.startswith("#")]
        self.assertEqual(len(hashtags), 4)

    def test_region_hashtag_strips_spaces(self):
        text = render_launch_announcement_sns(STORE_NAME, URL, region_name="渋谷 区")
        self.assertIn("#渋谷区", text)

    def test_empty_region_name_is_same_as_omitted(self):
        with_empty = render_launch_announcement_sns(STORE_NAME, URL, region_name="")
        without = render_launch_announcement_sns(STORE_NAME, URL)
        self.assertEqual(with_empty, without)


class IsLaunchAnnouncementTriggerTests(unittest.TestCase):
    def test_exact_keyword_matches(self):
        self.assertTrue(is_launch_announcement_trigger("告知文"))

    def test_surrounding_whitespace_is_ignored(self):
        self.assertTrue(is_launch_announcement_trigger("  告知文  \n"))

    def test_unrelated_text_does_not_match(self):
        self.assertFalse(is_launch_announcement_trigger("告知文を作りたい"))
        self.assertFalse(is_launch_announcement_trigger("FAQ"))
        self.assertFalse(is_launch_announcement_trigger(""))


class FriendAddUrlPlaceholderTests(unittest.TestCase):
    def test_placeholder_can_be_rendered_as_is(self):
        # design 4.1節: 実LINE公式アカウント開設前はプレースホルダのまま差し込むことを
        # 許容する暫定仕様(FRIEND_ADD_URL_PLACEHOLDER自体は空文字列ではないため
        # render_launch_announcement_pop/snsのValueErrorを起こさずそのまま使える)。
        text = render_launch_announcement_pop(STORE_NAME, FRIEND_ADD_URL_PLACEHOLDER)
        self.assertIn(FRIEND_ADD_URL_PLACEHOLDER, text)


if __name__ == "__main__":
    unittest.main()
