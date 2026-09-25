#!/usr/bin/env python3
import unittest

from blocked_but_billing_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER
from chatbot_intent_router import (
    CHATBOT_INTENT_VALUES,
    OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT,
    append_faq_followup_hint,
    build_chatbot_escalation_notification_flex_message,
    format_chatbot_escalation_notification_message,
    render_faq_guidance_message,
    route_chatbot_intent,
    send_chatbot_escalation_notification,
)
from trial_end_scheduler import InMemoryLinePushClient, LinePushDeliveryError


class _FailingLinePushClient:
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        raise LinePushDeliveryError("simulated outage")


class ChatbotIntentValuesTest(unittest.TestCase):
    def test_matches_design_3_categories(self):
        self.assertEqual(
            CHATBOT_INTENT_VALUES,
            {
                "completion_report_request",
                "faq_guidance_candidate",
                "other_needs_human",
            },
        )


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


class FormatChatbotEscalationNotificationMessageTest(unittest.TestCase):
    def test_embeds_user_id_and_memo_text(self):
        text = format_chatbot_escalation_notification_message(
            "u1", "なんかいつもと違う気がする"
        )
        self.assertIn("u1", text)
        self.assertIn("なんかいつもと違う気がする", text)

    def test_flex_message_body_includes_escalation_alt_text(self):
        contents = build_chatbot_escalation_notification_flex_message(
            "u1", "なんかいつもと違う気がする"
        )
        self.assertIn("エスカレーション", str(contents))


class SendChatbotEscalationNotificationTest(unittest.TestCase):
    def test_sends_to_fixed_owner_destination(self):
        push = InMemoryLinePushClient()
        sent = send_chatbot_escalation_notification("u1", "困っています", push)

        self.assertTrue(sent)
        self.assertEqual(push.sent[0][0], OWNER_LINE_USER_ID_PLACEHOLDER)
        contents_text = str(push.sent[0][2])
        self.assertIn("u1", contents_text)
        self.assertIn("困っています", contents_text)

    def test_custom_owner_destination(self):
        push = InMemoryLinePushClient()
        send_chatbot_escalation_notification(
            "u1", "困っています", push, owner_line_user_id="owner-group-1"
        )
        self.assertEqual(push.sent[0][0], "owner-group-1")

    def test_delivery_failure_returns_false(self):
        sent = send_chatbot_escalation_notification(
            "u1", "困っています", _FailingLinePushClient()
        )
        self.assertFalse(sent)

    def test_repeated_messages_from_same_user_each_send_independently(self):
        push = InMemoryLinePushClient()
        send_chatbot_escalation_notification("u1", "1件目の相談", push)
        send_chatbot_escalation_notification("u1", "2件目の相談", push)

        self.assertEqual(len(push.sent), 2)
        self.assertIn("1件目の相談", str(push.sent[0][2]))
        self.assertIn("2件目の相談", str(push.sent[1][2]))


class RouteChatbotIntentTest(unittest.TestCase):
    def test_completion_report_request_appends_hint(self):
        result = route_chatbot_intent(
            "completion_report_request", generation_reply_text="完了報告書を生成しました。"
        )
        self.assertEqual(result, append_faq_followup_hint("完了報告書を生成しました。"))

    def test_completion_report_request_without_text_raises(self):
        with self.assertRaises(ValueError):
            route_chatbot_intent("completion_report_request")

    def test_faq_guidance_candidate_returns_guidance_message(self):
        self.assertEqual(
            route_chatbot_intent("faq_guidance_candidate"), render_faq_guidance_message()
        )

    def test_other_needs_human_notifies_owner_and_replies_to_customer(self):
        push = InMemoryLinePushClient()
        result = route_chatbot_intent(
            "other_needs_human",
            user_id="u1",
            memo_text="なんかいつもと違う気がする",
            push_client=push,
        )

        self.assertEqual(result, OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT)
        self.assertEqual(push.sent[0][0], OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertIn("なんかいつもと違う気がする", str(push.sent[0][2]))

    def test_other_needs_human_replies_to_customer_even_if_notification_fails(self):
        result = route_chatbot_intent(
            "other_needs_human",
            user_id="u1",
            memo_text="困っています",
            push_client=_FailingLinePushClient(),
        )
        self.assertEqual(result, OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT)

    def test_other_needs_human_without_required_args_raises(self):
        with self.assertRaises(ValueError):
            route_chatbot_intent("other_needs_human")

    def test_unknown_intent_raises(self):
        with self.assertRaises(ValueError):
            route_chatbot_intent("something_else")


if __name__ == "__main__":
    unittest.main()
