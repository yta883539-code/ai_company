#!/usr/bin/env python3
"""cloud_function_webhook.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(G1〜G4・OOS1・II1)を返すスタブLLMクライアントを
使い、status別の返信文組み立て・検証失敗時のフォールバックを確認する。

実行方法: python3 -m unittest test_cloud_function_webhook -v
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from cloud_function_webhook import (  # noqa: E402
    API_FAILURE_FALLBACK_MESSAGE,
    APPLICATION_FORM_URL_PLACEHOLDER,
    PLAN_MONTHLY_LIMITS,
    PORTAL_LINK_PLACEHOLDER,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    VALIDATION_FAILURE_FALLBACK_MESSAGE,
    FIRST_GENERATION_NOTICE_AREA_UNCONFIGURED_SUFFIX,
    FIRST_GENERATION_NOTICE_BODY,
    InMemoryApplicationFormLinkProvider,
    InMemoryFirstGenerationNoticeStore,
    InMemoryGymAreaConfigStore,
    InMemoryPortalLinkProvider,
    InMemoryReplyClient,
    InMemoryUsageCounter,
    LlmApiError,
    ReplyApiError,
    append_first_generation_notice,
    build_usage_notice,
    dispatch_webhook_events,
    format_reply_text,
    format_welcome_message,
    get_runtime_dependencies,
    main,
    merge_text_and_photo_events,
    process_follow_event,
    process_memo_event,
    process_unfollow_event,
    receive_webhook,
    validate_llm_output,
    verify_line_signature,
)
from user_id_linking import (  # noqa: E402
    InMemoryLinkingCodeStore,
    LinkingCodePurgeThrottle,
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


class ProcessMemoEventPurgeThrottleTest(unittest.TestCase):
    """linking-code-purge-trigger-design.mdで採用した、process_memo_event便乗での
    purge_expired_links()呼び出し配線の検証。"""

    def test_purges_expired_links_when_both_store_and_throttle_are_provided(self):
        linking_store = InMemoryLinkingCodeStore()
        now = datetime(2026, 8, 20, 12, 0, 0)
        linking_store.save("OLD001", "U-old", now - timedelta(hours=25))
        throttle = LinkingCodePurgeThrottle()
        reply_client = InMemoryReplyClient()

        process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic"), reply_client,
            linking_store=linking_store, purge_throttle=throttle, now=now,
        )

        self.assertIsNone(linking_store.get("OLD001"))

    def test_second_call_within_min_interval_does_not_purge_again(self):
        linking_store = InMemoryLinkingCodeStore()
        now = datetime(2026, 8, 20, 12, 0, 0)
        throttle = LinkingCodePurgeThrottle()
        reply_client = InMemoryReplyClient()
        process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic"), reply_client,
            linking_store=linking_store, purge_throttle=throttle, now=now,
        )

        linking_store.save("OLD001", "U-old", now - timedelta(hours=25))
        process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic"), reply_client,
            linking_store=linking_store, purge_throttle=throttle,
            now=now + timedelta(minutes=30),
        )

        self.assertIsNotNone(linking_store.get("OLD001"))  # 1時間未満なので間引かれる

    def test_no_purge_call_when_linking_store_not_provided(self):
        # purge_throttleのみ渡されlinking_storeが無い場合は既存の他オプション引数と同様、
        # 何も呼ばれず通常通り返信のみ行われる(未接続時の安全側デフォルト)。
        throttle = LinkingCodePurgeThrottle()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic"), reply_client, purge_throttle=throttle,
        )

        self.assertTrue(result.reply_sent)
        self.assertIsNone(throttle._last_purge_at)

    def test_no_purge_call_when_purge_throttle_not_provided(self):
        linking_store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(), FixtureLlmClient("G1_basic"), reply_client, linking_store=linking_store,
        )

        self.assertTrue(result.reply_sent)


class AppendFirstGenerationNoticeTest(unittest.TestCase):
    def test_appends_body_only_when_area_configured(self):
        result = append_first_generation_notice("本文", gym_area_configured=True)

        self.assertEqual(result, f"本文\n\n{FIRST_GENERATION_NOTICE_BODY}")

    def test_appends_area_unconfigured_suffix_when_not_configured(self):
        result = append_first_generation_notice("本文", gym_area_configured=False)

        self.assertIn(FIRST_GENERATION_NOTICE_BODY, result)
        self.assertIn(FIRST_GENERATION_NOTICE_AREA_UNCONFIGURED_SUFFIX, result)


class InMemoryGymAreaConfigStoreTest(unittest.TestCase):
    """gym_area_configuredの実データ参照経路スタブ
    (first-generation-notice-implementation-design.md 5節)の検証。"""

    def test_unregistered_user_is_not_configured(self):
        store = InMemoryGymAreaConfigStore()

        self.assertFalse(store.is_configured("u-1"))

    def test_user_passed_at_construction_is_configured(self):
        store = InMemoryGymAreaConfigStore(configured_user_ids={"u-1"})

        self.assertTrue(store.is_configured("u-1"))
        self.assertFalse(store.is_configured("u-2"))

    def test_set_configured_toggles_state(self):
        store = InMemoryGymAreaConfigStore()

        store.set_configured("u-1")
        self.assertTrue(store.is_configured("u-1"))

        store.set_configured("u-1", configured=False)
        self.assertFalse(store.is_configured("u-1"))


class ProcessMemoEventFirstGenerationNoticeTest(unittest.TestCase):
    """process_memo_event()への初回生成確認案内の統合
    (first-generation-notice-implementation-design.md 2節)の検証。"""

    def test_first_generation_appends_notice(self):
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
        )

        self.assertIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertTrue(notice_store.has_sent("u-1"))

    def test_second_generation_does_not_repeat_notice(self):
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()

        process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
        )
        second_result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
        )

        self.assertNotIn(FIRST_GENERATION_NOTICE_BODY, second_result.reply_text)

    def test_out_of_scope_reply_does_not_trigger_notice(self):
        # 確認案内は生成成功時(status=="generated")のみが対象(6節)。
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(text="会員になりたい", user_id="u-1"), FixtureLlmClient("OOS1_membership_question"),
            reply_client, usage_counter=usage_counter, first_generation_notice_store=notice_store,
        )

        self.assertNotIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertFalse(notice_store.has_sent("u-1"))

    def test_area_unconfigured_appends_extra_sentence(self):
        # gym_area_config_storeにu-1が未登録(=申込フォームでジム名・地域名が未入力)のケース。
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        gym_area_store = InMemoryGymAreaConfigStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
            gym_area_config_store=gym_area_store,
        )

        self.assertIn(FIRST_GENERATION_NOTICE_AREA_UNCONFIGURED_SUFFIX, result.reply_text)

    def test_area_configured_does_not_append_extra_sentence(self):
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        gym_area_store = InMemoryGymAreaConfigStore(configured_user_ids={"u-1"})
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
            gym_area_config_store=gym_area_store,
        )

        self.assertIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertNotIn(FIRST_GENERATION_NOTICE_AREA_UNCONFIGURED_SUFFIX, result.reply_text)

    def test_gym_area_config_store_not_provided_defaults_to_configured(self):
        # gym_area_config_store未指定(実接続前)は「設定済み」を既定値とし、未接続を理由に
        # 誤って未設定の注意喚起を出さない(安全側のデフォルト)。
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
        )

        self.assertIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertNotIn(FIRST_GENERATION_NOTICE_AREA_UNCONFIGURED_SUFFIX, result.reply_text)

    def test_no_notice_when_store_not_provided(self):
        # first_generation_notice_store未指定(実接続前)の呼び出しは従来通りスキップする。
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter,
        )

        self.assertNotIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)

    def test_combines_with_usage_counter_notice_in_single_reply(self):
        # first_generation_notice_storeとplan(月間カウント)の両方を渡した場合、
        # 確認案内(1回目)と上限接近通知が同じ返信に共存しうる。
        usage_counter = InMemoryUsageCounter()
        for _ in range(5):
            usage_counter.increment("u-1", "2026-08")
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
            plan="ライト", month="2026-08",
        )

        # increment前のcount(5)が0でないため、確認案内は付記されない(初回生成の定義通り)。
        self.assertNotIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertIn("残り2回です", result.reply_text)


class InMemoryUsageCounterAtomicNoticeTest(unittest.TestCase):
    """InMemoryUsageCounter.increment_and_mark_notice()単体の検証
    (first-generation-notice-implementation-design.md 3節「書き込みの原子性」)。"""

    def test_increment_and_mark_notice_true_updates_both(self):
        counter = InMemoryUsageCounter()

        count = counter.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=True)

        self.assertEqual(count, 1)
        self.assertTrue(counter.has_sent("u-1"))

    def test_increment_and_mark_notice_false_only_updates_count(self):
        counter = InMemoryUsageCounter()

        count = counter.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=False)

        self.assertEqual(count, 1)
        self.assertFalse(counter.has_sent("u-1"))

    def test_second_call_continues_incrementing_without_reset(self):
        counter = InMemoryUsageCounter()
        counter.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=True)

        count = counter.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=True)

        self.assertEqual(count, 2)
        self.assertTrue(counter.has_sent("u-1"))


class InMemoryUsageCounterTrialStartAtTest(unittest.TestCase):
    """InMemoryUsageCounter.set_trial_start_at_if_unset()・get_trial_start_at()、および
    increment_and_mark_notice()へのtrial_start_at相乗り(trial-start-anchor-decision.md 3節)。"""

    def test_get_trial_start_at_defaults_to_none(self):
        counter = InMemoryUsageCounter()

        self.assertIsNone(counter.get_trial_start_at("u-1"))

    def test_set_trial_start_at_if_unset_records_value(self):
        counter = InMemoryUsageCounter()
        moment = datetime(2026, 8, 23, 12, 0, tzinfo=timezone(timedelta(hours=9)))

        counter.set_trial_start_at_if_unset("u-1", moment)

        self.assertEqual(counter.get_trial_start_at("u-1"), moment)

    def test_set_trial_start_at_if_unset_does_not_overwrite_existing_value(self):
        counter = InMemoryUsageCounter()
        first_moment = datetime(2026, 8, 23, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        later_moment = datetime(2026, 8, 24, 9, 0, tzinfo=timezone(timedelta(hours=9)))
        counter.set_trial_start_at_if_unset("u-1", first_moment)

        counter.set_trial_start_at_if_unset("u-1", later_moment)

        self.assertEqual(counter.get_trial_start_at("u-1"), first_moment)

    def test_increment_and_mark_notice_sets_trial_start_at_when_provided(self):
        counter = InMemoryUsageCounter()
        moment = datetime(2026, 8, 23, 12, 0, tzinfo=timezone(timedelta(hours=9)))

        counter.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=True, trial_start_at=moment)

        self.assertEqual(counter.get_trial_start_at("u-1"), moment)

    def test_increment_and_mark_notice_without_trial_start_at_leaves_it_unset(self):
        counter = InMemoryUsageCounter()

        counter.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=True)

        self.assertIsNone(counter.get_trial_start_at("u-1"))

    def test_increment_and_mark_notice_does_not_overwrite_trial_start_at_on_later_calls(self):
        counter = InMemoryUsageCounter()
        first_moment = datetime(2026, 8, 23, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        later_moment = datetime(2026, 9, 1, 9, 0, tzinfo=timezone(timedelta(hours=9)))
        counter.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=True, trial_start_at=first_moment)

        counter.increment_and_mark_notice("u-1", "2026-09", mark_notice_sent=False, trial_start_at=later_moment)

        self.assertEqual(counter.get_trial_start_at("u-1"), first_moment)


class _AtomicOnlyUsageCounter(InMemoryUsageCounter):
    """increment()・mark_sent()が単体(increment_and_mark_notice()を介さず)で呼ばれた回数を
    記録するスパイ。process_memo_event()が本当にincrement_and_mark_notice()経由の単一書き込み
    経路を使っていること(2ステップの書き込みに分解されていないこと)を検証するために使う
    (increment_and_mark_notice()自体の内部実装がincrement()を再利用することは許容する)。"""

    def __init__(self) -> None:
        super().__init__()
        self.direct_increment_calls = 0
        self.direct_mark_sent_calls = 0
        self.atomic_calls = 0
        self._in_atomic_call = False

    def increment(self, user_id, month):
        if not self._in_atomic_call:
            self.direct_increment_calls += 1
        return super().increment(user_id, month)

    def mark_sent(self, user_id):
        if not self._in_atomic_call:
            self.direct_mark_sent_calls += 1
        return super().mark_sent(user_id)

    def increment_and_mark_notice(self, user_id, month, mark_notice_sent, trial_start_at=None):
        self.atomic_calls += 1
        self._in_atomic_call = True
        try:
            return super().increment_and_mark_notice(user_id, month, mark_notice_sent, trial_start_at)
        finally:
            self._in_atomic_call = False


class ProcessMemoEventAtomicNoticeWriteTest(unittest.TestCase):
    """usage_counterとfirst_generation_notice_storeに同一インスタンスを渡した場合、
    process_memo_event()がcount増分とnotice_sent更新を単一の書き込み呼び出し
    (increment_and_mark_notice)にまとめること(first-generation-notice-implementation-design.md
    3節)の検証。"""

    def test_first_generation_write_uses_atomic_path_when_same_store(self):
        store = _AtomicOnlyUsageCounter()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=store, first_generation_notice_store=store,
            plan="ライト", month="2026-08",
        )

        self.assertIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertTrue(store.has_sent("u-1"))
        self.assertEqual(store.get_count("u-1", "2026-08"), 1)
        self.assertEqual(store.atomic_calls, 1)
        self.assertEqual(store.direct_increment_calls, 0)
        self.assertEqual(store.direct_mark_sent_calls, 0)

    def test_non_first_generation_still_uses_atomic_increment_when_same_store(self):
        # 初回生成ではない(既にnotice送信済み)場合はmark_notice_sent=Falseで
        # increment_and_mark_notice()を呼ぶ(増分自体は単一メソッド経由のまま)。
        store = _AtomicOnlyUsageCounter()
        store.increment_and_mark_notice("u-1", "2026-08", mark_notice_sent=True)
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=store, first_generation_notice_store=store,
            plan="ライト", month="2026-08",
        )

        self.assertNotIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertEqual(store.get_count("u-1", "2026-08"), 2)
        self.assertEqual(store.direct_increment_calls, 0)
        self.assertEqual(store.direct_mark_sent_calls, 0)

    def test_different_store_instances_fall_back_to_two_step_write(self):
        # 従来通り、usage_counterとfirst_generation_notice_storeが別インスタンスの場合は
        # 2ステップの書き込みのまま(既存のProcessMemoEventFirstGenerationNoticeTestと同種の
        # 確認。ここでは原子的経路を使っていないことの反証として残す)。
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
            plan="ライト", month="2026-08",
        )

        self.assertIn(FIRST_GENERATION_NOTICE_BODY, result.reply_text)
        self.assertTrue(notice_store.has_sent("u-1"))
        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 1)


class ProcessMemoEventTrialStartAtTest(unittest.TestCase):
    """process_memo_event()がtrial_start_atを初回生成成功時にのみ、指定された`now`で
    記録すること(trial-start-anchor-decision.md 3節「初回生成成功時に1回だけ設定」)の検証。
    2ステップの書き込み経路(usage_counterとfirst_generation_notice_storeが別インスタンス)、
    原子的書き込み経路(同一インスタンス)の両方をカバーする。"""

    def test_first_generation_sets_trial_start_at_via_two_step_path(self):
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()
        moment = datetime(2026, 8, 23, 12, 0, tzinfo=timezone(timedelta(hours=9)))

        process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
            plan="ライト", month="2026-08", now=moment,
        )

        self.assertEqual(usage_counter.get_trial_start_at("u-1"), moment)

    def test_first_generation_sets_trial_start_at_via_atomic_path(self):
        store = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        moment = datetime(2026, 8, 23, 12, 0, tzinfo=timezone(timedelta(hours=9)))

        process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=store, first_generation_notice_store=store,
            plan="ライト", month="2026-08", now=moment,
        )

        self.assertEqual(store.get_trial_start_at("u-1"), moment)

    def test_second_generation_does_not_overwrite_trial_start_at(self):
        usage_counter = InMemoryUsageCounter()
        notice_store = InMemoryFirstGenerationNoticeStore()
        reply_client = InMemoryReplyClient()
        first_moment = datetime(2026, 8, 23, 12, 0, tzinfo=timezone(timedelta(hours=9)))
        later_moment = datetime(2026, 8, 24, 9, 0, tzinfo=timezone(timedelta(hours=9)))
        process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
            plan="ライト", month="2026-08", now=first_moment,
        )

        process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, first_generation_notice_store=notice_store,
            plan="ライト", month="2026-08", now=later_moment,
        )

        self.assertEqual(usage_counter.get_trial_start_at("u-1"), first_moment)

    def test_no_usage_counter_means_no_trial_start_at_error(self):
        # usage_counter未接続時(None)は、trial_start_atの記録もカウント処理自体と同様に
        # 単純にスキップされる(例外にならないことのみ確認)。
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
        )

        self.assertTrue(result.reply_sent)


class SubscriptionProcedureNoticeTest(unittest.TestCase):
    """status=cancellation_intent/downgrade_intent/cancellation_unclearの
    subscription_procedure_notice.body組み立て(PORTAL_LINK_PLACEHOLDERの置換・
    未接続時のフォールバック)の検証。CI1〜CI3はschema/validate_test_cases.pyのフィクスチャ。"""

    def test_cancellation_intent_replaces_placeholder_with_portal_url(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="解約したいです", user_id="u-1"),
            FixtureLlmClient("CI1_cancellation_intent_clear"), reply_client,
            portal_link_provider=InMemoryPortalLinkProvider("https://billing.stripe.com/p/session/abc"),
        )

        self.assertTrue(result.reply_sent)
        self.assertNotIn(PORTAL_LINK_PLACEHOLDER, result.reply_text)
        self.assertIn("https://billing.stripe.com/p/session/abc", result.reply_text)

    def test_downgrade_intent_replaces_placeholder_with_portal_url(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="プランを下げたい", user_id="u-1"),
            FixtureLlmClient("CI2_downgrade_intent"), reply_client,
            portal_link_provider=InMemoryPortalLinkProvider("https://billing.stripe.com/p/session/xyz"),
        )

        self.assertNotIn(PORTAL_LINK_PLACEHOLDER, result.reply_text)
        self.assertIn("https://billing.stripe.com/p/session/xyz", result.reply_text)

    def test_cancellation_unclear_has_no_portal_link_even_when_provider_available(self):
        # includes_portal_link=Falseのケース(厳守事項7a(iv))はプレースホルダ自体を
        # 含まないため、providerの有無にかかわらず本文をそのまま返す。
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="もう辞めようかな", user_id="u-1"),
            FixtureLlmClient("CI3_cancellation_unclear"), reply_client,
            portal_link_provider=InMemoryPortalLinkProvider(),
        )

        self.assertEqual(
            result.reply_text,
            TEST_CASES["CI3_cancellation_unclear"]["subscription_procedure_notice"]["body"],
        )

    def test_cancellation_intent_falls_back_when_provider_not_connected(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="解約したいです", user_id="u-1"),
            FixtureLlmClient("CI1_cancellation_intent_clear"), reply_client,
            portal_link_provider=None,
        )

        self.assertEqual(result.reply_text, PORTAL_LINK_UNAVAILABLE_FALLBACK)
        self.assertNotIn(PORTAL_LINK_PLACEHOLDER, result.reply_text)

    def test_cancellation_intent_falls_back_when_provider_returns_none(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="解約したいです", user_id="u-1"),
            FixtureLlmClient("CI1_cancellation_intent_clear"), reply_client,
            portal_link_provider=InMemoryPortalLinkProvider(None),
        )

        self.assertEqual(result.reply_text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_cancellation_intent_falls_back_when_user_id_missing(self):
        # userIdが取得できないイベント(想定外)は、providerが接続済みでも安全側で
        # フォールバックする(URLをどの顧客宛に発行してよいか特定できないため)。
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="解約したいです"),
            FixtureLlmClient("CI1_cancellation_intent_clear"), reply_client,
            portal_link_provider=InMemoryPortalLinkProvider("https://billing.stripe.com/p/session/abc"),
        )

        self.assertEqual(result.reply_text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_cancellation_status_does_not_increment_usage_counter(self):
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        process_memo_event(
            _make_event(text="解約したいです", user_id="u-1"),
            FixtureLlmClient("CI1_cancellation_intent_clear"), reply_client,
            usage_counter=usage_counter, plan="ライト", month="2026-08",
            portal_link_provider=InMemoryPortalLinkProvider(),
        )

        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 0)


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


class ProcessFollowEventTest(unittest.TestCase):
    """process_follow_event()・format_welcome_message()のテスト(follow-event-welcome-message-design.md参照)。"""

    def _rng(self, seed=1):
        import random

        return random.Random(seed)

    def test_generated_code_is_embedded_in_reply_and_result(self):
        store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        event = {
            "type": "follow",
            "replyToken": "rt-follow-1",
            "source": {"userId": "U1234"},
        }

        result = process_follow_event(event, store, reply_client, rng=self._rng())

        self.assertTrue(result.handled)
        self.assertTrue(result.reply_sent)
        self.assertIsNotNone(result.linking_code)
        self.assertEqual(len(reply_client.sent), 1)
        sent_reply_token, sent_text = reply_client.sent[0]
        self.assertEqual(sent_reply_token, "rt-follow-1")
        self.assertIn(result.linking_code, sent_text)
        self.assertIn("コースセットパシャッと", sent_text)

    def test_without_form_link_provider_placeholder_is_used(self):
        text = format_welcome_message("ABC123", form_link_provider=None)
        self.assertIn(APPLICATION_FORM_URL_PLACEHOLDER, text)

    def test_with_form_link_provider_real_url_is_used(self):
        provider = InMemoryApplicationFormLinkProvider(url="https://forms.gle/real-form")
        text = format_welcome_message("ABC123", form_link_provider=provider)
        self.assertIn("https://forms.gle/real-form", text)
        self.assertNotIn(APPLICATION_FORM_URL_PLACEHOLDER, text)

    def test_non_follow_event_is_ignored(self):
        store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        event = {
            "type": "message",
            "replyToken": "rt",
            "source": {"userId": "U1234"},
        }

        result = process_follow_event(event, store, reply_client, rng=self._rng())

        self.assertFalse(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertEqual(reply_client.sent, [])

    def test_missing_user_id_does_not_reply(self):
        store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        event = {"type": "follow", "replyToken": "rt", "source": {}}

        result = process_follow_event(event, store, reply_client, rng=self._rng())

        self.assertTrue(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertIsNone(result.linking_code)
        self.assertEqual(reply_client.sent, [])

    def test_reply_failure_still_keeps_issued_code(self):
        class FailingReplyClient:
            def reply(self, reply_token, message_text):
                raise ReplyApiError("boom")

        store = InMemoryLinkingCodeStore()
        event = {
            "type": "follow",
            "replyToken": "rt",
            "source": {"userId": "U9999"},
        }

        result = process_follow_event(event, store, FailingReplyClient(), rng=self._rng())

        self.assertTrue(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertIsNotNone(result.linking_code)
        self.assertIsNotNone(store.get(result.linking_code))

    def test_purge_throttle_runs_before_issuing_code(self):
        store = InMemoryLinkingCodeStore()
        store.save("OLDCOD", "Uold", datetime(2026, 1, 1))
        reply_client = InMemoryReplyClient()
        throttle = LinkingCodePurgeThrottle()
        event = {
            "type": "follow",
            "replyToken": "rt",
            "source": {"userId": "U1234"},
        }

        process_follow_event(
            event,
            store,
            reply_client,
            rng=self._rng(),
            purge_throttle=throttle,
            now=datetime(2026, 1, 3),
        )

        self.assertIsNone(store.get("OLDCOD"))


class ProcessUnfollowEventTest(unittest.TestCase):
    """process_unfollow_event()のテスト(unfollow-event-handling-design.md参照)。"""

    def test_deletes_pending_links_for_the_unfollowed_user(self):
        store = InMemoryLinkingCodeStore()
        issued_at = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
        store.save("CODE01", "U-bye", issued_at)
        store.save("CODE02", "U-bye", issued_at)
        store.save("CODE03", "U-stay", issued_at)
        event = {"type": "unfollow", "source": {"userId": "U-bye"}}

        result = process_unfollow_event(event, store)

        self.assertTrue(result.handled)
        self.assertEqual(result.deleted_link_count, 2)
        self.assertIsNone(store.get("CODE01"))
        self.assertIsNone(store.get("CODE02"))
        self.assertIsNotNone(store.get("CODE03"))

    def test_no_pending_links_returns_zero(self):
        store = InMemoryLinkingCodeStore()
        event = {"type": "unfollow", "source": {"userId": "U-clean"}}

        result = process_unfollow_event(event, store)

        self.assertTrue(result.handled)
        self.assertEqual(result.deleted_link_count, 0)

    def test_non_unfollow_event_is_ignored(self):
        store = InMemoryLinkingCodeStore()
        event = {"type": "follow", "source": {"userId": "U1"}}

        result = process_unfollow_event(event, store)

        self.assertFalse(result.handled)

    def test_missing_user_id_is_handled_without_deleting(self):
        store = InMemoryLinkingCodeStore()
        event = {"type": "unfollow", "source": {}}

        result = process_unfollow_event(event, store)

        self.assertTrue(result.handled)
        self.assertEqual(result.deleted_link_count, 0)

    def test_missing_linking_store_is_handled_without_error(self):
        event = {"type": "unfollow", "source": {"userId": "U-bye"}}

        result = process_unfollow_event(event, None)

        self.assertTrue(result.handled)
        self.assertEqual(result.deleted_link_count, 0)


class DispatchWebhookEventsTest(unittest.TestCase):
    """dispatch_webhook_events()のテスト(webhook-event-dispatch-design.md参照)。"""

    def _rng(self, seed=1):
        import random

        return random.Random(seed)

    def test_follow_and_message_events_are_routed_separately(self):
        linking_store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        events = [
            {
                "type": "follow",
                "replyToken": "rt-follow",
                "source": {"userId": "U-follow"},
            },
            {
                "type": "message",
                "replyToken": "rt-message",
                "message": {"type": "text", "text": "エリアA 黄テープ 8本新規"},
                "source": {"userId": "U-message"},
            },
        ]

        result = dispatch_webhook_events(
            events,
            linking_store=linking_store,
            reply_client=reply_client,
            llm_call=FixtureLlmClient("G1_basic"),
            rng=self._rng(),
        )

        self.assertEqual(len(result.follow_results), 1)
        self.assertTrue(result.follow_results[0].handled)
        self.assertEqual(len(result.memo_results), 1)
        self.assertTrue(result.memo_results[0].handled)
        self.assertEqual(result.ignored_types, [])
        self.assertEqual(len(reply_client.sent), 2)

    def test_message_events_are_bundled_by_user_before_processing(self):
        reply_client = InMemoryReplyClient()
        events = [
            {
                "type": "message",
                "replyToken": "rt-text",
                "message": {"type": "text", "text": "エリアA 黄テープ 8本新規"},
                "source": {"userId": "U-bundle"},
            },
            {
                "type": "message",
                "replyToken": "rt-photo",
                "message": {"type": "image"},
                "source": {"userId": "U-bundle"},
            },
        ]

        result = dispatch_webhook_events(
            events,
            reply_client=reply_client,
            llm_call=FixtureLlmClient("G1_basic"),
        )

        # text+imageの2イベントがmerge_text_and_photo_events()で1件に束ねられるため、
        # process_memo_event()の呼び出しも1回だけになる(followイベントが混入して
        # 束ね処理を乱すこともない)。
        self.assertEqual(len(result.memo_results), 1)
        self.assertTrue(result.memo_results[0].handled)

    def test_unsupported_event_type_is_recorded_and_ignored(self):
        reply_client = InMemoryReplyClient()
        events = [{"type": "postback", "source": {"userId": "U-bye"}}]

        result = dispatch_webhook_events(events, reply_client=reply_client)

        self.assertEqual(result.follow_results, [])
        self.assertEqual(result.memo_results, [])
        self.assertEqual(result.unfollow_results, [])
        self.assertEqual(result.ignored_types, ["postback"])
        self.assertEqual(reply_client.sent, [])

    def test_unfollow_events_are_routed_and_delete_pending_links(self):
        linking_store = InMemoryLinkingCodeStore()
        linking_store.save("ABCDEF", "U-bye", datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc))
        events = [{"type": "unfollow", "source": {"userId": "U-bye"}}]

        result = dispatch_webhook_events(events, linking_store=linking_store)

        self.assertEqual(result.ignored_types, [])
        self.assertEqual(len(result.unfollow_results), 1)
        self.assertTrue(result.unfollow_results[0].handled)
        self.assertEqual(result.unfollow_results[0].deleted_link_count, 1)
        self.assertIsNone(linking_store.get("ABCDEF"))

    def test_follow_events_are_skipped_when_linking_store_not_connected(self):
        reply_client = InMemoryReplyClient()
        events = [
            {"type": "follow", "replyToken": "rt", "source": {"userId": "U1"}},
        ]

        result = dispatch_webhook_events(events, reply_client=reply_client, linking_store=None)

        self.assertEqual(result.follow_results, [])
        self.assertEqual(reply_client.sent, [])

    def test_message_events_are_skipped_when_llm_call_not_connected(self):
        reply_client = InMemoryReplyClient()
        events = [
            {
                "type": "message",
                "replyToken": "rt",
                "message": {"type": "text", "text": "テスト"},
                "source": {"userId": "U1"},
            },
        ]

        result = dispatch_webhook_events(events, reply_client=reply_client, llm_call=None)

        self.assertEqual(result.memo_results, [])
        self.assertEqual(reply_client.sent, [])


class ReceiveWebhookTest(unittest.TestCase):
    """receive_webhook()のテスト(receive-webhook-http-entry-point-design.md参照)。"""

    SECRET = "demo-secret"

    def _signed(self, body: bytes) -> str:
        return base64.b64encode(hmac.new(self.SECRET.encode("utf-8"), body, hashlib.sha256).digest()).decode(
            "utf-8"
        )

    def test_invalid_signature_returns_401_without_dispatch(self):
        body = json.dumps({"events": [{"type": "unfollow"}]}).encode("utf-8")
        reply_client = InMemoryReplyClient()

        result = receive_webhook(body, "invalid-signature", self.SECRET, reply_client=reply_client)

        self.assertEqual(result.status_code, 401)
        self.assertIsNone(result.dispatch_result)
        self.assertEqual(reply_client.sent, [])

    def test_invalid_json_body_returns_400(self):
        body = b"not-json{"

        result = receive_webhook(body, self._signed(body), self.SECRET)

        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_json")

    def test_missing_events_key_returns_400(self):
        body = json.dumps({"foo": "bar"}).encode("utf-8")

        result = receive_webhook(body, self._signed(body), self.SECRET)

        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "missing_events")

    def test_valid_request_dispatches_and_returns_200(self):
        body = json.dumps(
            {
                "events": [
                    {
                        "type": "message",
                        "replyToken": "rt-message",
                        "message": {"type": "text", "text": "エリアA 黄テープ 8本新規"},
                        "source": {"userId": "U-message"},
                    }
                ]
            }
        ).encode("utf-8")
        reply_client = InMemoryReplyClient()

        result = receive_webhook(
            body,
            self._signed(body),
            self.SECRET,
            reply_client=reply_client,
            llm_call=FixtureLlmClient("G1_basic"),
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNotNone(result.dispatch_result)
        self.assertEqual(len(result.dispatch_result.memo_results), 1)
        self.assertTrue(result.dispatch_result.memo_results[0].handled)
        self.assertEqual(len(reply_client.sent), 1)


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ。
    本物のflask.Request/functions_frameworkはインストールせず、`get_data()`・
    `headers.get(...)`という同じインターフェースだけを再現する。"""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    def get_data(self) -> bytes:
        return self._body


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント)のテスト。
    receive-webhook-http-entry-point-design.md「残課題」だった、実リクエストオブジェクトからの
    body・署名ヘッダ取り出し配線を検証する(receive_webhook()自体の分岐は
    ReceiveWebhookTestで既にカバー済みのため、ここではmain()固有の配線部分に絞る)。"""

    SECRET = "demo-secret"

    def _signed(self, body: bytes) -> str:
        return base64.b64encode(hmac.new(self.SECRET.encode("utf-8"), body, hashlib.sha256).digest()).decode(
            "utf-8"
        )

    def setUp(self):
        self._original_secret = os.environ.get("LINE_CHANNEL_SECRET")
        os.environ["LINE_CHANNEL_SECRET"] = self.SECRET

    def tearDown(self):
        if self._original_secret is None:
            os.environ.pop("LINE_CHANNEL_SECRET", None)
        else:
            os.environ["LINE_CHANNEL_SECRET"] = self._original_secret

    def test_valid_request_extracts_body_and_signature_and_returns_200(self):
        body = json.dumps({"events": [{"type": "unfollow"}]}).encode("utf-8")
        request = _StubFlaskRequest(body, {"X-Line-Signature": self._signed(body)})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 200)
        self.assertEqual(response_body, "OK")

    def test_invalid_signature_returns_401_with_error_body(self):
        body = json.dumps({"events": []}).encode("utf-8")
        request = _StubFlaskRequest(body, {"X-Line-Signature": "invalid-signature"})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)
        self.assertEqual(response_body, "invalid_signature")

    def test_missing_signature_header_returns_401(self):
        body = json.dumps({"events": []}).encode("utf-8")
        request = _StubFlaskRequest(body, {})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)

    def test_missing_channel_secret_env_returns_401(self):
        os.environ.pop("LINE_CHANNEL_SECRET", None)
        body = json.dumps({"events": []}).encode("utf-8")
        request = _StubFlaskRequest(body, {"X-Line-Signature": self._signed(body)})

        response_body, status_code = main(request)

        self.assertEqual(status_code, 401)

    def test_get_runtime_dependencies_output_is_accepted_by_receive_webhook(self):
        # 現時点(オーナー承認待ち)では空辞書(=全依存関係が未接続)を返す。
        # receive_webhook()にそのまま**kwargsとして渡せる(dispatch_webhook_events()側の
        # None未接続時フォールバックにより例外を起こさない)ことを確認する。
        deps = get_runtime_dependencies()
        self.assertEqual(deps, {})
        body = json.dumps({"events": [{"type": "unfollow"}]}).encode("utf-8")

        result = receive_webhook(body, self._signed(body), self.SECRET, **deps)

        self.assertEqual(result.status_code, 200)


if __name__ == "__main__":
    unittest.main()
