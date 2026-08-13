#!/usr/bin/env python3
"""cloud_function_webhook.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(G1〜G3・OOS1・II1)を返すスタブLLMクライアントを
使い、status別の返信文組み立て・検証失敗時のフォールバックを確認する。
course-set-pasha/prototype/test_cloud_function_webhook.pyの構成を踏襲しつつ、本venture固有の
差異(署名検証・写真束ねロジックが存在しないためそれらのテストは対象外)を反映した。

実行方法: python3 -m unittest test_cloud_function_webhook -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from cloud_function_webhook import (  # noqa: E402
    VALIDATION_FAILURE_FALLBACK_MESSAGE,
    InMemoryReplyClient,
    format_reply_text,
    process_memo_event,
    validate_llm_output,
)


class FixtureLlmClient:
    """TEST_CASESから固定のインスタンスを返すスタブ(メモ本文は無視する)。"""

    def __init__(self, case_id, mutate=None):
        self.case_id = case_id
        self.mutate = mutate

    def generate(self, memo_text, retry_context=None):
        instance = dict(TEST_CASES[self.case_id])
        if self.mutate:
            instance = self.mutate(instance)
        return instance


class RetryThenFixLlmClient:
    """1回目はmutateで壊れた出力を返し、retry_context付きの2回目呼び出しでのみ
    正常な出力(case_id)を返すスタブ(リトライ成功パターンの検証用)。"""

    def __init__(self, case_id, mutate):
        self.case_id = case_id
        self.mutate = mutate
        self.calls = []

    def generate(self, memo_text, retry_context=None):
        self.calls.append(retry_context)
        instance = dict(TEST_CASES[self.case_id])
        if retry_context is None:
            instance = self.mutate(instance)
        return instance


class AlwaysBrokenLlmClient:
    """retry_contextの有無にかかわらず常に壊れた出力を返すスタブ
    (リトライしても解消しないパターンの検証用)。"""

    def __init__(self, case_id, mutate):
        self.case_id = case_id
        self.mutate = mutate
        self.calls = []

    def generate(self, memo_text, retry_context=None):
        self.calls.append(retry_context)
        return self.mutate(dict(TEST_CASES[self.case_id]))


def _make_event(reply_token="rt-1", text="壁掛け型2.2kW、フィルター・熱交換器・送風ファンまで分解洗浄"):
    return {
        "replyToken": reply_token,
        "message": {"type": "text", "text": text},
    }


class ProcessMemoEventTest(unittest.TestCase):
    def test_generated_case_sends_combined_reply(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(), FixtureLlmClient("G1_basic"), reply_client)

        self.assertTrue(result.handled)
        self.assertTrue(result.reply_sent)
        self.assertEqual(result.validation_errors, [])
        self.assertIn("【作業完了報告メッセージの下書き】", result.reply_text)
        self.assertIn("【お手入れ案内の下書き】", result.reply_text)
        self.assertIn("【作業履歴記録(スプレッドシート転記用)】", result.reply_text)
        self.assertEqual(len(reply_client.sent), 1)
        self.assertEqual(reply_client.sent[0], ("rt-1", result.reply_text))

    def test_generated_case_history_row_includes_model_and_dirt_condition(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(), FixtureLlmClient("G1_basic"), reply_client)

        row = TEST_CASES["G1_basic"]["history_row"]
        self.assertIn(row["model_type_and_capacity"], result.reply_text)
        self.assertIn(row["dirt_condition"], result.reply_text)

    def test_generated_case_with_null_fields_shows_placeholder(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="分解洗浄しました、汚れひどい"), FixtureLlmClient("G3_model_and_date_unextractable"), reply_client
        )
        self.assertTrue(result.reply_sent)
        self.assertIn("(未記載)", result.reply_text)

    def test_out_of_scope_case_returns_out_of_scope_message(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(text="予約を受け付けてほしい"), FixtureLlmClient("OOS1_reservation_question"), reply_client)

        self.assertEqual(result.reply_text, TEST_CASES["OOS1_reservation_question"]["out_of_scope_message"])

    def test_insufficient_input_case_returns_missing_fields_request(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(text="作業終わりました"), FixtureLlmClient("II1_no_work_content"), reply_client)

        self.assertEqual(result.reply_text, TEST_CASES["II1_no_work_content"]["missing_fields_request"])

    def test_schema_violation_falls_back_to_resend_request(self):
        def break_status(instance):
            instance = dict(instance)
            instance["status"] = "unexpected_status"
            return instance

        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic", mutate=break_status), reply_client
        )

        self.assertTrue(result.handled)
        self.assertTrue(result.reply_sent)
        self.assertEqual(result.reply_text, VALIDATION_FAILURE_FALLBACK_MESSAGE)
        self.assertTrue(result.validation_errors)
        self.assertTrue(result.retried)

    def test_post_generation_check_violation_falls_back_to_resend_request(self):
        def add_refrigerant_mention(instance):
            instance = dict(instance)
            instance["completion_report"] = dict(instance["completion_report"])
            instance["completion_report"]["mentions_refrigerant_or_electrical"] = True
            return instance

        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic", mutate=add_refrigerant_mention), reply_client
        )

        self.assertEqual(result.reply_text, VALIDATION_FAILURE_FALLBACK_MESSAGE)
        self.assertTrue(result.validation_errors)
        self.assertTrue(result.retried)

    def test_successful_first_attempt_is_not_marked_retried(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(), FixtureLlmClient("G1_basic"), reply_client)

        self.assertFalse(result.retried)

    def test_retry_succeeds_when_second_generation_is_valid(self):
        def break_status(instance):
            instance = dict(instance)
            instance["status"] = "unexpected_status"
            return instance

        reply_client = InMemoryReplyClient()
        llm_client = RetryThenFixLlmClient("G1_basic", mutate=break_status)
        result = process_memo_event(_make_event(), llm_client, reply_client)

        self.assertTrue(result.reply_sent)
        self.assertTrue(result.retried)
        self.assertEqual(result.validation_errors, [])
        self.assertIn("【作業完了報告メッセージの下書き】", result.reply_text)
        # 1回目はretry_context無し、2回目は検証エラーの概要付きで呼ばれる
        self.assertEqual(len(llm_client.calls), 2)
        self.assertIsNone(llm_client.calls[0])
        self.assertIsNotNone(llm_client.calls[1])

    def test_retry_still_failing_falls_back_after_exactly_one_retry(self):
        def break_status(instance):
            instance = dict(instance)
            instance["status"] = "unexpected_status"
            return instance

        reply_client = InMemoryReplyClient()
        llm_client = AlwaysBrokenLlmClient("G1_basic", mutate=break_status)
        result = process_memo_event(_make_event(), llm_client, reply_client)

        self.assertEqual(result.reply_text, VALIDATION_FAILURE_FALLBACK_MESSAGE)
        self.assertTrue(result.retried)
        # リトライは1回のみ(無限リトライしない)
        self.assertEqual(len(llm_client.calls), 2)

    def test_image_only_event_is_not_handled(self):
        reply_client = InMemoryReplyClient()
        event = {"replyToken": "rt-image", "message": {"type": "image"}}
        result = process_memo_event(event, FixtureLlmClient("G1_basic"), reply_client)

        self.assertFalse(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertEqual(reply_client.sent, [])


class ValidateLlmOutputTest(unittest.TestCase):
    def test_all_fixture_cases_pass_validation(self):
        for case_id, instance in TEST_CASES.items():
            with self.subTest(case=case_id):
                self.assertEqual(validate_llm_output(instance), [])

    def test_format_reply_text_raises_for_unknown_status(self):
        with self.assertRaises(ValueError):
            format_reply_text({"status": "unexpected_status"})


if __name__ == "__main__":
    unittest.main()
