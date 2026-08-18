#!/usr/bin/env python3
"""cloud_function_webhook.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(G1〜G4・OOS1・II1)を返すスタブLLMクライアントを
使い、status別の返信文組み立て・検証失敗時のフォールバックを確認する。

実行方法: python3 -m unittest test_cloud_function_webhook -v
"""

import base64
import hashlib
import hmac
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from cloud_function_webhook import (  # noqa: E402
    API_FAILURE_FALLBACK_MESSAGE,
    PLAN_MONTHLY_LIMITS,
    VALIDATION_FAILURE_FALLBACK_MESSAGE,
    InMemoryReplyClient,
    InMemoryUsageCounter,
    LlmApiError,
    ReplyApiError,
    build_usage_notice,
    format_reply_text,
    merge_text_and_photo_events,
    process_memo_event,
    validate_llm_output,
    verify_line_signature,
)


class FixtureLlmClient:
    """TEST_CASESから固定のインスタンスを返すスタブ(メモ本文・has_photoは無視する)。"""

    def __init__(self, case_id, mutate=None):
        self.case_id = case_id
        self.mutate = mutate

    def generate(self, memo_text, has_photo, retry_context=None):
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

    def generate(self, memo_text, has_photo, retry_context=None):
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

    def generate(self, memo_text, has_photo, retry_context=None):
        self.calls.append(retry_context)
        return self.mutate(dict(TEST_CASES[self.case_id]))


class FlakyOnceLlmClient:
    """1回目のgenerate()呼び出しでLlmApiErrorを送出し、2回目(即時リトライ)は
    正常な出力を返すスタブ(api-call-failure-handling.md方針1のリトライ成功パターン)。"""

    def __init__(self, case_id):
        self.case_id = case_id
        self.calls = 0

    def generate(self, memo_text, has_photo, retry_context=None):
        self.calls += 1
        if self.calls == 1:
            raise LlmApiError("simulated timeout")
        return dict(TEST_CASES[self.case_id])


class AlwaysFailingLlmClient:
    """常にLlmApiErrorを送出するスタブ(即時リトライしても解消しないパターンの検証用)。"""

    def __init__(self):
        self.calls = 0

    def generate(self, memo_text, has_photo, retry_context=None):
        self.calls += 1
        raise LlmApiError("simulated persistent failure")


class FlakyOnceReplyClient:
    """1回目のreply()呼び出しでReplyApiErrorを送出し、2回目(即時リトライ)は成功する
    スタブ(api-call-failure-handling.md方針2のリトライ成功パターン)。"""

    def __init__(self):
        self.calls = 0
        self.sent = []

    def reply(self, reply_token, message_text):
        self.calls += 1
        if self.calls == 1:
            raise ReplyApiError("simulated timeout")
        self.sent.append((reply_token, message_text))


class AlwaysFailingReplyClient:
    """常にReplyApiErrorを送出するスタブ(Push API等の代替手段が無いため、2回とも
    失敗した場合にreply_sent=Falseで諦める挙動の検証用)。"""

    def __init__(self):
        self.calls = 0

    def reply(self, reply_token, message_text):
        self.calls += 1
        raise ReplyApiError("simulated persistent failure")


def _make_event(reply_token="rt-1", text="エリアA 黄テープ 8本新規、2026/8/9改訂", has_photo=False, user_id=None):
    event = {
        "replyToken": reply_token,
        "message": {"type": "text", "text": text},
        "hasPhoto": has_photo,
    }
    if user_id:
        event["source"] = {"userId": user_id}
    return event


class ProcessMemoEventTest(unittest.TestCase):
    def test_generated_case_sends_combined_reply(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(), FixtureLlmClient("G1_basic"), reply_client)

        self.assertTrue(result.handled)
        self.assertTrue(result.reply_sent)
        self.assertEqual(result.validation_errors, [])
        self.assertIn("【SNS投稿文の下書き】", result.reply_text)
        self.assertIn("【LINE/Web告知文の下書き】", result.reply_text)
        self.assertIn("【更新履歴(スプレッドシート転記用)】", result.reply_text)
        self.assertEqual(len(reply_client.sent), 1)
        self.assertEqual(reply_client.sent[0], ("rt-1", result.reply_text))

    def test_generated_multi_area_case_includes_all_rows_in_csv(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="エリアB・エリアC同時更新"), FixtureLlmClient("G4_multi_area_single_memo"), reply_client
        )
        self.assertTrue(result.reply_sent)
        for row in TEST_CASES["G4_multi_area_single_memo"]["history_rows"]:
            self.assertIn(row["area"], result.reply_text)

    def test_out_of_scope_case_returns_out_of_scope_message(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(text="会員になりたい"), FixtureLlmClient("OOS1_membership_question"), reply_client)

        self.assertEqual(result.reply_text, TEST_CASES["OOS1_membership_question"]["out_of_scope_message"])

    def test_insufficient_input_case_returns_missing_fields_request(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(text="更新しました"), FixtureLlmClient("II1_no_area_no_count"), reply_client)

        self.assertEqual(result.reply_text, TEST_CASES["II1_no_area_no_count"]["missing_fields_request"])

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
        def add_out_of_scope_topic(instance):
            instance = dict(instance)
            instance["sns_post"] = dict(instance["sns_post"])
            instance["sns_post"]["body"] = instance["sns_post"]["body"] + " ご予約はこちらから。"
            return instance

        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic", mutate=add_out_of_scope_topic), reply_client
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
        self.assertIn("【SNS投稿文の下書き】", result.reply_text)
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

    def test_llm_api_failure_recovers_after_one_retry(self):
        reply_client = InMemoryReplyClient()
        llm_client = FlakyOnceLlmClient("G1_basic")
        result = process_memo_event(_make_event(), llm_client, reply_client)

        self.assertTrue(result.reply_sent)
        self.assertFalse(result.api_failure)
        self.assertIn("【SNS投稿文の下書き】", result.reply_text)
        self.assertEqual(llm_client.calls, 2)

    def test_llm_api_failure_falls_back_after_exactly_one_retry(self):
        reply_client = InMemoryReplyClient()
        llm_client = AlwaysFailingLlmClient()
        result = process_memo_event(_make_event(), llm_client, reply_client)

        self.assertTrue(result.handled)
        self.assertTrue(result.reply_sent)
        self.assertTrue(result.api_failure)
        self.assertEqual(result.reply_text, API_FAILURE_FALLBACK_MESSAGE)
        # リトライは1回のみ(即時1回、待機なし)
        self.assertEqual(llm_client.calls, 2)
        self.assertEqual(reply_client.sent, [("rt-1", API_FAILURE_FALLBACK_MESSAGE)])

    def test_reply_api_failure_recovers_after_one_retry(self):
        reply_client = FlakyOnceReplyClient()
        result = process_memo_event(_make_event(), FixtureLlmClient("G1_basic"), reply_client)

        self.assertTrue(result.reply_sent)
        self.assertEqual(reply_client.calls, 2)
        self.assertEqual(len(reply_client.sent), 1)

    def test_reply_api_failure_gives_up_after_one_retry_without_crashing(self):
        reply_client = AlwaysFailingReplyClient()
        result = process_memo_event(_make_event(), FixtureLlmClient("G1_basic"), reply_client)

        self.assertTrue(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertIsNone(result.reply_text)
        # Push API等の代替送達手段が無いため、即時1回のリトライで諦める
        self.assertEqual(reply_client.calls, 2)

    def test_image_only_event_is_not_handled(self):
        reply_client = InMemoryReplyClient()
        event = {"replyToken": "rt-image", "message": {"type": "image"}}
        result = process_memo_event(event, FixtureLlmClient("G1_basic"), reply_client)

        self.assertFalse(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertEqual(reply_client.sent, [])


def _text_event(user_id, text, reply_token="rt-text"):
    return {
        "replyToken": reply_token,
        "source": {"userId": user_id},
        "message": {"type": "text", "text": text},
    }


def _image_event(user_id):
    return {"source": {"userId": user_id}, "message": {"type": "image"}}


class BuildUsageNoticeTest(unittest.TestCase):
    """limit-approaching-notification-design.md 3〜4節の境界値(残り2回到達・上限超過)の検証。"""

    def test_no_notice_when_far_from_limit(self):
        self.assertIsNone(build_usage_notice("ライト", 1))

    def test_notice_at_two_remaining(self):
        # ライトプランは月8回まで(pricing-plan.md)。残り2回 = 6回目消費時点。
        notice = build_usage_notice("ライト", 6)
        self.assertEqual(notice, "※今月の生成回数は残り2回です(上限到達後は1回あたり150円の追加料金がかかります)")

    def test_no_notice_at_one_remaining(self):
        # 残り2回の1回のみ通知する方針(3節)のため、残り1回時点では追加通知しない。
        self.assertIsNone(build_usage_notice("ライト", 7))

    def test_no_notice_exactly_at_limit(self):
        self.assertIsNone(build_usage_notice("ライト", 8))

    def test_notice_when_over_limit(self):
        notice = build_usage_notice("ライト", 9)
        self.assertEqual(notice, "※今月の無料生成回数の上限を超えたため、本回は追加料金150円が発生します")

    def test_standard_plan_uses_own_limit_and_unit_price(self):
        # スタンダードプランは月15回まで・従量120円/回(pricing-plan.md)。
        self.assertEqual(PLAN_MONTHLY_LIMITS["スタンダード"], 15)
        notice = build_usage_notice("スタンダード", 13)
        self.assertEqual(notice, "※今月の生成回数は残り2回です(上限到達後は1回あたり120円の追加料金がかかります)")

    def test_setter_multi_plan_uses_own_limit_and_unit_price(self):
        # セッター複数プランは月30回まで・従量100円/回(pricing-plan.md)。
        self.assertEqual(PLAN_MONTHLY_LIMITS["セッター複数"], 30)
        notice = build_usage_notice("セッター複数", 28)
        self.assertEqual(notice, "※今月の生成回数は残り2回です(上限到達後は1回あたり100円の追加料金がかかります)")


class ProcessMemoEventUsageCounterTest(unittest.TestCase):
    """process_memo_event()への月間カウント統合(status=='generated'のみカウント、
    残り2回到達・上限超過時のみ返信文に通知を追記)の検証。"""

    def test_generated_reply_appends_notice_at_two_remaining(self):
        usage_counter = InMemoryUsageCounter()
        for _ in range(5):
            usage_counter.increment("u-1", "2026-08")

        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, plan="ライト", month="2026-08",
        )

        self.assertTrue(result.reply_sent)
        self.assertIn("残り2回です", result.reply_text)
        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 6)

    def test_generated_reply_has_no_notice_when_far_from_limit(self):
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, plan="ライト", month="2026-08",
        )

        self.assertNotIn("※", result.reply_text)
        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 1)

    def test_generated_reply_appends_overage_notice_beyond_limit(self):
        usage_counter = InMemoryUsageCounter()
        for _ in range(8):
            usage_counter.increment("u-1", "2026-08")

        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, plan="ライト", month="2026-08",
        )

        self.assertIn("追加料金150円が発生します", result.reply_text)

    def test_out_of_scope_reply_does_not_increment_count(self):
        # カウント対象はstatus=="generated"のみ(2節)。
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        process_memo_event(
            _make_event(text="会員になりたい", user_id="u-1"), FixtureLlmClient("OOS1_membership_question"),
            reply_client, usage_counter=usage_counter, plan="ライト", month="2026-08",
        )

        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 0)

    def test_no_counting_when_usage_counter_not_provided(self):
        # usage_counter未指定(実接続前)の呼び出しは従来通りカウント処理をスキップする。
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client)

        self.assertNotIn("※", result.reply_text)

    def test_no_counting_when_user_id_missing_from_event(self):
        # sourceにuserIdが無いイベント(想定外だが安全側にカウントをスキップ)。
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, plan="ライト", month="2026-08",
        )

        self.assertNotIn("※", result.reply_text)


class MergeTextAndPhotoEventsTest(unittest.TestCase):
    def test_text_and_one_photo_from_same_user_are_merged(self):
        events = [_image_event("u1"), _text_event("u1", "エリアA 更新")]
        merged = merge_text_and_photo_events(events)

        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["hasPhoto"])
        self.assertEqual(merged[0]["message"]["text"], "エリアA 更新")

    def test_text_only_is_marked_no_photo(self):
        events = [_text_event("u1", "エリアA 更新")]
        merged = merge_text_and_photo_events(events)

        self.assertEqual(len(merged), 1)
        self.assertFalse(merged[0]["hasPhoto"])

    def test_photo_only_passes_through_unmerged(self):
        events = [_image_event("u1")]
        merged = merge_text_and_photo_events(events)

        self.assertEqual(len(merged), 1)
        self.assertNotIn("hasPhoto", merged[0])
        self.assertEqual(merged[0]["message"]["type"], "image")

    def test_different_users_are_not_confused(self):
        events = [_image_event("u1"), _text_event("u2", "u2のメモ")]
        merged = merge_text_and_photo_events(events)

        self.assertEqual(len(merged), 2)
        text_results = [e for e in merged if e["message"]["type"] == "text"]
        self.assertEqual(len(text_results), 1)
        self.assertFalse(text_results[0]["hasPhoto"])
        image_results = [e for e in merged if e["message"]["type"] == "image"]
        self.assertEqual(len(image_results), 1)
        self.assertNotIn("hasPhoto", image_results[0])

    def test_two_text_events_from_same_user_are_not_merged(self):
        events = [_text_event("u1", "メモ1", "rt-1"), _text_event("u1", "メモ2", "rt-2")]
        merged = merge_text_and_photo_events(events)

        self.assertEqual(len(merged), 2)
        self.assertEqual({e["message"]["text"] for e in merged}, {"メモ1", "メモ2"})

    def test_event_without_user_id_is_passed_through(self):
        events = [{"message": {"type": "text", "text": "userId無し"}, "replyToken": "rt"}]
        merged = merge_text_and_photo_events(events)

        self.assertEqual(len(merged), 1)
        self.assertNotIn("hasPhoto", merged[0])


class ValidateLlmOutputTest(unittest.TestCase):
    def test_all_fixture_cases_pass_validation(self):
        for case_id, instance in TEST_CASES.items():
            with self.subTest(case=case_id):
                self.assertEqual(validate_llm_output(instance), [])

    def test_format_reply_text_raises_for_unknown_status(self):
        with self.assertRaises(ValueError):
            format_reply_text({"status": "unexpected_status"})


class VerifyLineSignatureTest(unittest.TestCase):
    def test_valid_signature_accepted(self):
        secret = "demo-secret"
        body = b'{"events": []}'
        signature = base64.b64encode(hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()).decode("utf-8")
        self.assertTrue(verify_line_signature(body, signature, secret))

    def test_missing_signature_rejected(self):
        self.assertFalse(verify_line_signature(b"body", None, "secret"))

    def test_invalid_signature_rejected(self):
        self.assertFalse(verify_line_signature(b"body", "invalid", "secret"))


if __name__ == "__main__":
    unittest.main()
