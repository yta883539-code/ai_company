#!/usr/bin/env python3
"""chatbot_intent_router.pyのテスト。
chatbot-intent-classification-escalation-design.md 1節・3節のマッピング層・
エスカレーション通知の挙動を検証する。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from chatbot_intent_router import (  # noqa: E402
    CHATBOT_INTENT_VALUES,
    faq_intent_to_code,
    format_chatbot_escalation_notification_message,
    render_chatbot_faq_response_message,
    send_chatbot_escalation_notification,
)
from owner_faq_router import (  # noqa: E402
    render_owner_faq_answer_message,
    render_owner_faq_menu_message,
)
from payment_suspension_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER  # noqa: E402
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError  # noqa: E402


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class ChatbotIntentValuesTest(unittest.TestCase):
    def test_matches_design_5_categories(self) -> None:
        # design 1節が定義する5分類と一致することを固定する回帰テスト。
        self.assertEqual(
            CHATBOT_INTENT_VALUES,
            {
                "post_generation_request",
                "faq_pricing",
                "faq_howto",
                "faq_cancel_change",
                "other_needs_human",
            },
        )


class FaqIntentToCodeTest(unittest.TestCase):
    def test_faq_pricing_maps_to_q2(self) -> None:
        self.assertEqual(faq_intent_to_code("faq_pricing"), "Q2")

    def test_faq_cancel_change_maps_to_q3(self) -> None:
        self.assertEqual(faq_intent_to_code("faq_cancel_change"), "Q3")

    def test_faq_howto_has_no_single_code(self) -> None:
        # Q1・Q4〜Q6の複数項目にまたがるため単一コードには定まらない。
        self.assertIsNone(faq_intent_to_code("faq_howto"))

    def test_non_faq_intents_have_no_code(self) -> None:
        self.assertIsNone(faq_intent_to_code("post_generation_request"))
        self.assertIsNone(faq_intent_to_code("other_needs_human"))


class RenderChatbotFaqResponseMessageTest(unittest.TestCase):
    def test_faq_pricing_returns_q2_answer(self) -> None:
        self.assertEqual(
            render_chatbot_faq_response_message("faq_pricing"),
            render_owner_faq_answer_message("Q2"),
        )

    def test_faq_cancel_change_returns_q3_answer(self) -> None:
        self.assertEqual(
            render_chatbot_faq_response_message("faq_cancel_change"),
            render_owner_faq_answer_message("Q3"),
        )

    def test_faq_howto_returns_full_menu(self) -> None:
        # 単一項目を推測せず、メニュー全体を提示する。
        self.assertEqual(
            render_chatbot_faq_response_message("faq_howto"),
            render_owner_faq_menu_message(),
        )

    def test_non_faq_intent_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_chatbot_faq_response_message("post_generation_request")
        with self.assertRaises(ValueError):
            render_chatbot_faq_response_message("other_needs_human")


class FormatChatbotEscalationNotificationMessageTest(unittest.TestCase):
    def test_embeds_user_id_and_memo_text(self) -> None:
        text = format_chatbot_escalation_notification_message(
            "u1", "なんかいつもと違う気がする"
        )
        self.assertIn("u1", text)
        self.assertIn("なんかいつもと違う気がする", text)
        self.assertIn("エスカレーション", text)


class SendChatbotEscalationNotificationTest(unittest.TestCase):
    def test_sends_to_fixed_owner_destination(self) -> None:
        push = InMemoryLinePushClient()
        sent = send_chatbot_escalation_notification("u1", "困っています", push)

        self.assertTrue(sent)
        self.assertEqual(push.sent[0][0], OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertIn("u1", push.sent[0][1])
        self.assertIn("困っています", push.sent[0][1])

    def test_custom_owner_destination(self) -> None:
        push = InMemoryLinePushClient()
        send_chatbot_escalation_notification(
            "u1", "困っています", push, owner_line_user_id="owner-group-1"
        )
        self.assertEqual(push.sent[0][0], "owner-group-1")

    def test_delivery_failure_returns_false(self) -> None:
        sent = send_chatbot_escalation_notification(
            "u1", "困っています", _FailingLinePushClient()
        )
        self.assertFalse(sent)

    def test_repeated_messages_from_same_customer_each_send_independently(self) -> None:
        # design 3節「冪等性」: 送信済みフラグを持たず、都度通知する。
        push = InMemoryLinePushClient()
        send_chatbot_escalation_notification("u1", "1件目の相談", push)
        send_chatbot_escalation_notification("u1", "2件目の相談", push)

        self.assertEqual(len(push.sent), 2)
        self.assertIn("1件目の相談", push.sent[0][1])
        self.assertIn("2件目の相談", push.sent[1][1])


if __name__ == "__main__":
    unittest.main()
