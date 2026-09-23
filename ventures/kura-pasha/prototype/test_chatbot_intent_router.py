#!/usr/bin/env python3
"""chatbot_intent_router.pyのテスト。
chatbot-intent-classification-design.md 1節・3節、chatbot-intent-classification-
llm-prompt-draft.md「設計上の要点4」のマッピング層・エスカレーション通知・一言追加の
挙動を検証する。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from chatbot_intent_router import (  # noqa: E402
    CHATBOT_INTENT_VALUES,
    OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT,
    append_faq_followup_hint,
    faq_intent_to_code,
    format_chatbot_escalation_notification_message,
    render_chatbot_faq_response_message,
    route_chatbot_intent,
    send_chatbot_escalation_notification,
)
from owner_faq_router import (  # noqa: E402
    render_owner_faq_answer_message,
    render_owner_faq_menu_message,
)
from payment_suspension_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER  # noqa: E402
from subscription_cancellation_notification import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushDeliveryError,
)


class _FailingLinePushClient:
    def send_message(self, user_id: str, text: str) -> None:
        raise LinePushDeliveryError("simulated outage")


class ChatbotIntentValuesTest(unittest.TestCase):
    def test_matches_design_6_categories(self) -> None:
        # design 1節が定義する6分類と一致することを固定する回帰テスト。
        self.assertEqual(
            CHATBOT_INTENT_VALUES,
            {
                "memo_processing_request",
                "faq_plan",
                "faq_howto",
                "faq_cancel",
                "faq_contractor_transfer_overview",
                "other_needs_human",
            },
        )


class FaqIntentToCodeTest(unittest.TestCase):
    def test_faq_cancel_maps_to_q3(self) -> None:
        self.assertEqual(faq_intent_to_code("faq_cancel"), "Q3")

    def test_faq_contractor_transfer_overview_maps_to_q7(self) -> None:
        self.assertEqual(faq_intent_to_code("faq_contractor_transfer_overview"), "Q7")

    def test_faq_plan_has_no_single_code(self) -> None:
        # Q1・Q5・Q6の複数項目にまたがるため単一コードには定まらない。
        self.assertIsNone(faq_intent_to_code("faq_plan"))

    def test_faq_howto_has_no_single_code(self) -> None:
        # Q2・Q4・Q8・Q9の複数項目にまたがるため単一コードには定まらない。
        self.assertIsNone(faq_intent_to_code("faq_howto"))

    def test_non_faq_intents_have_no_code(self) -> None:
        self.assertIsNone(faq_intent_to_code("memo_processing_request"))
        self.assertIsNone(faq_intent_to_code("other_needs_human"))


class RenderChatbotFaqResponseMessageTest(unittest.TestCase):
    def test_faq_cancel_returns_q3_answer(self) -> None:
        self.assertEqual(
            render_chatbot_faq_response_message("faq_cancel"),
            render_owner_faq_answer_message("Q3"),
        )

    def test_faq_contractor_transfer_overview_returns_q7_answer(self) -> None:
        self.assertEqual(
            render_chatbot_faq_response_message("faq_contractor_transfer_overview"),
            render_owner_faq_answer_message("Q7"),
        )

    def test_faq_plan_returns_full_menu(self) -> None:
        # 単一項目を推測せず、メニュー全体を提示する。
        self.assertEqual(
            render_chatbot_faq_response_message("faq_plan"),
            render_owner_faq_menu_message(),
        )

    def test_faq_howto_returns_full_menu(self) -> None:
        self.assertEqual(
            render_chatbot_faq_response_message("faq_howto"),
            render_owner_faq_menu_message(),
        )

    def test_non_faq_intent_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            render_chatbot_faq_response_message("memo_processing_request")
        with self.assertRaises(ValueError):
            render_chatbot_faq_response_message("other_needs_human")


class AppendFaqFollowupHintTest(unittest.TestCase):
    def test_appends_hint_after_generation_reply_text(self) -> None:
        result = append_faq_followup_hint("生成した受注内容整理メモ本文")
        self.assertTrue(result.startswith("生成した受注内容整理メモ本文"))
        self.assertIn("他にご質問がありましたら", result)

    def test_original_text_is_unchanged_prefix(self) -> None:
        # 複合入力(受注メモ+FAQ質問)でFAQ部分が欠落しても、本体のメモ処理結果自体は
        # 改変されないことを固定する回帰テスト。
        original = "ブリティッシュ鞍 牛革 競技用 納期3ヶ月"
        result = append_faq_followup_hint(original)
        self.assertTrue(result.startswith(original))
        self.assertNotEqual(result, original)


class FormatChatbotEscalationNotificationMessageTest(unittest.TestCase):
    def test_embeds_user_id_and_memo_text(self) -> None:
        text = format_chatbot_escalation_notification_message(
            "u1", "この鞍のひび割れ、直りますかね"
        )
        self.assertIn("u1", text)
        self.assertIn("この鞍のひび割れ、直りますかね", text)
        self.assertIn("エスカレーション", text)

    def test_includes_repair_judgement_caveat(self) -> None:
        # design 3節: 本venture固有の「修理可否等の専門的判断への言及を含む可能性が
        # あります」という補足を含むことを固定する回帰テスト。
        text = format_chatbot_escalation_notification_message("u1", "相談内容")
        self.assertIn("修理可否等の専門的判断", text)


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


class RouteChatbotIntentTest(unittest.TestCase):
    def test_memo_processing_request_appends_hint(self) -> None:
        result = route_chatbot_intent(
            "memo_processing_request", generation_reply_text="生成した受注内容整理メモ本文"
        )
        self.assertEqual(result, append_faq_followup_hint("生成した受注内容整理メモ本文"))

    def test_memo_processing_request_without_text_raises(self) -> None:
        with self.assertRaises(ValueError):
            route_chatbot_intent("memo_processing_request")

    def test_faq_plan_returns_full_menu(self) -> None:
        self.assertEqual(
            route_chatbot_intent("faq_plan"),
            render_chatbot_faq_response_message("faq_plan"),
        )

    def test_faq_howto_returns_full_menu(self) -> None:
        self.assertEqual(
            route_chatbot_intent("faq_howto"),
            render_chatbot_faq_response_message("faq_howto"),
        )

    def test_faq_cancel_returns_faq_answer(self) -> None:
        self.assertEqual(
            route_chatbot_intent("faq_cancel"),
            render_chatbot_faq_response_message("faq_cancel"),
        )

    def test_faq_contractor_transfer_overview_returns_faq_answer(self) -> None:
        self.assertEqual(
            route_chatbot_intent("faq_contractor_transfer_overview"),
            render_chatbot_faq_response_message("faq_contractor_transfer_overview"),
        )

    def test_other_needs_human_notifies_owner_and_replies_to_customer(self) -> None:
        push = InMemoryLinePushClient()
        result = route_chatbot_intent(
            "other_needs_human",
            user_id="u1",
            memo_text="この鞍のひび割れ、直りますかね",
            push_client=push,
        )

        self.assertEqual(result, OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT)
        self.assertEqual(push.sent[0][0], OWNER_LINE_USER_ID_PLACEHOLDER)
        self.assertIn("この鞍のひび割れ、直りますかね", push.sent[0][1])

    def test_other_needs_human_replies_to_customer_even_if_notification_fails(
        self,
    ) -> None:
        # design 3節: 通知の成否にかかわらず、顧客への無応答は避ける。
        result = route_chatbot_intent(
            "other_needs_human",
            user_id="u1",
            memo_text="困っています",
            push_client=_FailingLinePushClient(),
        )
        self.assertEqual(result, OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT)

    def test_other_needs_human_missing_args_raises(self) -> None:
        with self.assertRaises(ValueError):
            route_chatbot_intent("other_needs_human")

    def test_unknown_intent_raises(self) -> None:
        with self.assertRaises(ValueError):
            route_chatbot_intent("not_a_real_intent")


if __name__ == "__main__":
    unittest.main()
