#!/usr/bin/env python3
"""cloud_function_webhook.pyの自動テスト。

schema/validate_test_cases.pyのTEST_CASES(G1〜G3・OOS1・II1)を返すスタブLLMクライアントを
使い、status別の返信文組み立て・検証失敗時のフォールバックを確認する。
course-set-pasha/prototype/test_cloud_function_webhook.pyの構成を踏襲しつつ、本venture固有の
差異(写真束ねロジックが存在しないためそのテストは対象外。署名検証・HTTPエントリポイントは
フェーズ115(webhook-http-entry-point-design.md)でcourse-set-pashaと同じ設計を追加した)を
反映した。

実行方法: python3 -m unittest test_cloud_function_webhook -v
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))
from validate_test_cases import TEST_CASES  # noqa: E402

from cloud_function_webhook import (  # noqa: E402
    API_FAILURE_FALLBACK_MESSAGE,
    APPLICATION_FORM_URL_PLACEHOLDER,
    LENGTH_LIMIT_FALLBACK_MESSAGE,
    LINKING_REQUIRED_MESSAGE,
    LINKING_SUCCESS_MESSAGE,
    PLAN_MONTHLY_LIMITS,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    SELF_CHECK_NOTICE_TEXT,
    TRIAL_GENERATION_LIMIT,
    VALIDATION_FAILURE_FALLBACK_MESSAGE,
    InMemoryApplicationFormLinkProvider,
    InMemoryCheckoutSessionClient,
    InMemoryPortalLinkProvider,
    InMemoryReplyClient,
    InMemoryUsageCounter,
    LlmApiError,
    QuickReplyButton,
    ReplyApiError,
    build_usage_notice,
    dispatch_webhook_events,
    format_checkout_reply_message,
    format_reply_text,
    format_trial_end_condition_a_notice,
    format_welcome_message,
    get_runtime_dependencies,
    main,
    process_follow_event,
    process_memo_event,
    process_message_event,
    process_postback_event,
    process_unfollow_event,
    receive_webhook,
    render_subscription_procedure_notice,
    validate_llm_output,
    verify_line_signature,
)
from checkout_session import START_CHECKOUT_POSTBACK_DATA  # noqa: E402
from post_generation_checks import LINE_TEXT_MESSAGE_CHAR_LIMIT  # noqa: E402
from trial_end_scheduler import TRIAL_END_BUTTON_LABEL  # noqa: E402
from user_id_linking import (  # noqa: E402
    InMemoryLinkingCodeStore,
    InMemoryUserProfileStore,
    PendingLink,
    UserProfile,
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


class FlakyOnceLlmClient:
    """1回目のgenerate()呼び出しでLlmApiErrorを送出し、2回目(即時リトライ)は
    正常な出力を返すスタブ(api-call-failure-handling.md方針1のリトライ成功パターン)。"""

    def __init__(self, case_id):
        self.case_id = case_id
        self.calls = 0

    def generate(self, memo_text, retry_context=None):
        self.calls += 1
        if self.calls == 1:
            raise LlmApiError("simulated timeout")
        return dict(TEST_CASES[self.case_id])


class AlwaysFailingLlmClient:
    """常にLlmApiErrorを送出するスタブ(即時リトライしても解消しないパターンの検証用)。"""

    def __init__(self):
        self.calls = 0

    def generate(self, memo_text, retry_context=None):
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


def _make_event(reply_token="rt-1", text="壁掛け型2.2kW、フィルター・熱交換器・送風ファンまで分解洗浄", user_id=None):
    event = {
        "replyToken": reply_token,
        "message": {"type": "text", "text": text},
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
        self.assertIn("【作業完了報告メッセージの下書き】", result.reply_text)
        self.assertIn("【お手入れ案内の下書き】", result.reply_text)
        self.assertIn("【作業履歴記録(スプレッドシート転記用)】", result.reply_text)
        self.assertEqual(len(reply_client.sent), 1)
        self.assertEqual(reply_client.sent[0], ("rt-1", result.reply_text))

    def test_generated_case_history_row_includes_model_and_dirt_condition(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(), FixtureLlmClient("G1_basic"), reply_client)

        row = TEST_CASES["G1_basic"]["history_rows"][0]
        self.assertIn(row["model_type_and_capacity"], result.reply_text)
        self.assertIn(row["dirt_condition"], result.reply_text)

    def test_generated_case_with_multiple_units_lists_each_with_index_label(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="リビングと寝室の2台を分解洗浄"), FixtureLlmClient("G4_multiple_units_same_visit"), reply_client
        )

        self.assertTrue(result.reply_sent)
        self.assertIn("[1台目]", result.reply_text)
        self.assertIn("[2台目]", result.reply_text)
        for row in TEST_CASES["G4_multiple_units_same_visit"]["history_rows"]:
            self.assertIn(row["model_type_and_capacity"], result.reply_text)

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

    def test_over_length_body_falls_back_to_length_limit_message(self):
        # character-limit-fallback-design.md準拠: 依頼者へ転送される文面が5,000文字
        # (UTF-16コード単位)を超えた場合は、汎用のVALIDATION_FAILURE_FALLBACK_MESSAGEでは
        # なく、専用のLENGTH_LIMIT_FALLBACK_MESSAGE(業者向け・入力メモの短縮を促す文言)
        # を返す。切り詰めて送信しない(依頼者への誤送信事故を避ける)ことも合わせて確認する。
        def make_body_too_long(instance):
            instance = dict(instance)
            instance["completion_report"] = dict(instance["completion_report"])
            instance["completion_report"]["body"] = "あ" * (LINE_TEXT_MESSAGE_CHAR_LIMIT + 1)
            return instance

        reply_client = InMemoryReplyClient()
        llm_client = AlwaysBrokenLlmClient("G1_basic", mutate=make_body_too_long)
        result = process_memo_event(_make_event(), llm_client, reply_client)

        self.assertTrue(result.reply_sent)
        self.assertEqual(result.reply_text, LENGTH_LIMIT_FALLBACK_MESSAGE)
        self.assertTrue(result.validation_errors)
        # リトライは1回のみ、それでも上限超過が続く場合に専用フォールバックへ落ちる
        self.assertEqual(len(llm_client.calls), 2)

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

    def test_llm_api_failure_recovers_after_one_retry(self):
        reply_client = InMemoryReplyClient()
        llm_client = FlakyOnceLlmClient("G1_basic")
        result = process_memo_event(_make_event(), llm_client, reply_client)

        self.assertTrue(result.reply_sent)
        self.assertFalse(result.api_failure)
        self.assertIn("【作業完了報告メッセージの下書き】", result.reply_text)
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


class BuildUsageNoticeTest(unittest.TestCase):
    """limit-approaching-notification-design.md 2・4節の境界値(残り5回到達・上限超過)の検証。"""

    def test_no_notice_when_far_from_limit(self):
        self.assertIsNone(build_usage_notice("スモール", 1))

    def test_notice_at_five_remaining(self):
        # スモールプランは月40回まで(pricing-plan.md)。残り5回 = 35回目消費時点。
        notice = build_usage_notice("スモール", 35)
        self.assertEqual(notice, "※今月の生成回数は残り5回です(上限到達後は1回あたり60円の追加料金がかかります)")

    def test_no_notice_at_four_remaining(self):
        # 残り5回の1回のみ通知する方針(4節)のため、残り4回時点では追加通知しない。
        self.assertIsNone(build_usage_notice("スモール", 36))

    def test_no_notice_exactly_at_limit(self):
        self.assertIsNone(build_usage_notice("スモール", 40))

    def test_notice_when_over_limit(self):
        notice = build_usage_notice("スモール", 41)
        self.assertEqual(notice, "※今月の無料生成回数の上限を超えたため、本回は追加料金60円が発生します")

    def test_standard_plan_uses_own_limit_and_unit_price(self):
        # スタンダードプランは月90回まで・従量50円/回(pricing-plan.md)。
        self.assertEqual(PLAN_MONTHLY_LIMITS["スタンダード"], 90)
        notice = build_usage_notice("スタンダード", 85)
        self.assertEqual(notice, "※今月の生成回数は残り5回です(上限到達後は1回あたり50円の追加料金がかかります)")

    def test_busy_season_plan_uses_own_limit_and_unit_price(self):
        # 繁忙期対応プランは月150回まで・従量40円/回(pricing-plan.md)。
        self.assertEqual(PLAN_MONTHLY_LIMITS["繁忙期対応"], 150)
        notice = build_usage_notice("繁忙期対応", 145)
        self.assertEqual(notice, "※今月の生成回数は残り5回です(上限到達後は1回あたり40円の追加料金がかかります)")


class ProcessMemoEventUsageCounterTest(unittest.TestCase):
    """process_memo_event()への月間カウント統合(status=='generated'のみカウント、
    残り5回到達・上限超過時のみ返信文に通知を追記)の検証。"""

    def test_generated_reply_appends_notice_at_five_remaining(self):
        usage_counter = InMemoryUsageCounter()
        for _ in range(34):
            usage_counter.increment("u-1", "2026-08")

        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, plan="スモール", month="2026-08",
        )

        self.assertTrue(result.reply_sent)
        self.assertIn("残り5回です", result.reply_text)
        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 35)

    def test_generated_reply_has_no_notice_when_far_from_limit(self):
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, plan="スモール", month="2026-08",
        )

        self.assertNotIn("※", result.reply_text)
        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 1)

    def test_generated_reply_appends_overage_notice_beyond_limit(self):
        usage_counter = InMemoryUsageCounter()
        for _ in range(40):
            usage_counter.increment("u-1", "2026-08")

        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            usage_counter=usage_counter, plan="スモール", month="2026-08",
        )

        self.assertIn("追加料金60円が発生します", result.reply_text)

    def test_out_of_scope_reply_does_not_increment_count(self):
        # カウント対象はstatus=="generated"のみ(設計3節)。
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        process_memo_event(
            _make_event(text="予約を受け付けてほしい", user_id="u-1"), FixtureLlmClient("OOS1_reservation_question"),
            reply_client, usage_counter=usage_counter, plan="スモール", month="2026-08",
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
            usage_counter=usage_counter, plan="スモール", month="2026-08",
        )

        self.assertNotIn("※", result.reply_text)


class ProcessMemoEventFirstGenerationSelfCheckTest(unittest.TestCase):
    """process_memo_event()への初回生成時セルフチェック案内(first-generation-self-check-
    design.md)・trial_start_at書き込み(trial-start-anchor-decision.md)統合の検証。"""

    def _linked_profile_store(self, trial_start_at=None):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        profile_store.save(
            "u-1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                trial_start_at=trial_start_at,
            ),
        )
        return profile_store

    def test_first_generation_appends_notice_and_sets_trial_start_at(self):
        from datetime import datetime, timezone

        profile_store = self._linked_profile_store()
        now = datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            profile_store=profile_store, now=now,
        )

        self.assertIn(SELF_CHECK_NOTICE_TEXT, result.reply_text)
        self.assertEqual(profile_store.get("u-1").trial_start_at, now)

    def test_second_generation_does_not_repeat_notice_or_overwrite_trial_start_at(self):
        from datetime import datetime, timezone

        original_trial_start_at = datetime(2026, 8, 20, 1, 0, tzinfo=timezone.utc)
        profile_store = self._linked_profile_store(trial_start_at=original_trial_start_at)
        later_now = datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            profile_store=profile_store, now=later_now,
        )

        self.assertNotIn(SELF_CHECK_NOTICE_TEXT, result.reply_text)
        self.assertEqual(profile_store.get("u-1").trial_start_at, original_trial_start_at)

    def test_out_of_scope_reply_does_not_trigger_notice_or_write(self):
        # status=="generated"以外はセルフチェック案内・trial_start_at書き込みの対象外
        # (design 5節、usage_counterのカウント対象条件と同じ方針)。
        profile_store = self._linked_profile_store()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(text="予約を受け付けてほしい", user_id="u-1"),
            FixtureLlmClient("OOS1_reservation_question"), reply_client,
            profile_store=profile_store,
        )

        self.assertNotIn(SELF_CHECK_NOTICE_TEXT, result.reply_text)
        self.assertIsNone(profile_store.get("u-1").trial_start_at)

    def test_no_notice_or_write_when_profile_store_not_provided(self):
        # profile_store未指定(実接続前)の呼び出しは従来通りスキップする。
        reply_client = InMemoryReplyClient()
        result = process_memo_event(_make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client)

        self.assertNotIn(SELF_CHECK_NOTICE_TEXT, result.reply_text)

    def test_no_write_when_user_profile_not_found(self):
        # profile_storeは渡されたがuser_idに対応するuser_profileが存在しない(想定外だが
        # 安全側にスキップする)場合。
        profile_store = InMemoryUserProfileStore()
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-unknown"), FixtureLlmClient("G1_basic"), reply_client,
            profile_store=profile_store,
        )

        self.assertNotIn(SELF_CHECK_NOTICE_TEXT, result.reply_text)


class ProcessMemoEventTrialEndConditionATest(unittest.TestCase):
    """process_memo_event()への条件A(生成回数10回到達)トライアル終了通知
    (trial-end-condition-a-cta-design.md)統合の検証。"""

    def _profile_store(self, **profile_kwargs):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        profile_store.save(
            "u-1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                trial_start_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
                **profile_kwargs,
            ),
        )
        return profile_store

    def test_tenth_generation_appends_notice_and_attaches_quick_reply(self):
        from datetime import datetime, timezone

        profile_store = self._profile_store(trial_generation_count=TRIAL_GENERATION_LIMIT - 1)
        now = datetime(2026, 8, 28, 3, 0, tzinfo=timezone.utc)
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            profile_store=profile_store, now=now,
        )

        self.assertIn(
            format_trial_end_condition_a_notice(TRIAL_GENERATION_LIMIT), result.reply_text
        )
        self.assertEqual(
            reply_client.quick_replies_sent[-1],
            QuickReplyButton(
                label=TRIAL_END_BUTTON_LABEL, postback_data=START_CHECKOUT_POSTBACK_DATA,
            ),
        )
        self.assertEqual(profile_store.get("u-1").trial_end_notified_at, now)

    def test_ninth_generation_does_not_trigger_notice(self):
        profile_store = self._profile_store(trial_generation_count=TRIAL_GENERATION_LIMIT - 2)
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            profile_store=profile_store,
        )

        self.assertNotIn("無料トライアル", result.reply_text)
        self.assertEqual(reply_client.quick_replies_sent[-1], None)
        self.assertIsNone(profile_store.get("u-1").trial_end_notified_at)
        self.assertEqual(profile_store.get("u-1").trial_generation_count, TRIAL_GENERATION_LIMIT - 1)

    def test_no_double_send_when_already_notified_by_condition_b(self):
        from datetime import datetime, timezone

        already_notified_at = datetime(2026, 8, 20, tzinfo=timezone.utc)
        profile_store = self._profile_store(
            trial_generation_count=TRIAL_GENERATION_LIMIT - 1,
            trial_end_notified_at=already_notified_at,
        )
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            profile_store=profile_store,
        )

        self.assertNotIn("無料トライアル", result.reply_text)
        self.assertEqual(reply_client.quick_replies_sent[-1], None)
        self.assertEqual(profile_store.get("u-1").trial_end_notified_at, already_notified_at)

    def test_no_counting_or_notice_after_upgrade(self):
        from datetime import datetime, timezone

        profile_store = self._profile_store(
            trial_generation_count=TRIAL_GENERATION_LIMIT - 1,
            upgraded_at=datetime(2026, 8, 25, tzinfo=timezone.utc),
        )
        reply_client = InMemoryReplyClient()

        result = process_memo_event(
            _make_event(user_id="u-1"), FixtureLlmClient("G1_basic"), reply_client,
            profile_store=profile_store,
        )

        self.assertNotIn("無料トライアル", result.reply_text)
        self.assertEqual(reply_client.quick_replies_sent[-1], None)
        self.assertEqual(
            profile_store.get("u-1").trial_generation_count, TRIAL_GENERATION_LIMIT - 1
        )


class RenderSubscriptionProcedureNoticeTest(unittest.TestCase):
    """schema/output.schema.jsonのsubscription_procedure_notice(status=cancellation_intent/
    downgrade_intent/cancellation_unclear)の返信組み立て(厳守事項6a対応)を検証する。"""

    def test_unclear_case_returns_body_as_is_without_provider(self):
        notice = TEST_CASES["CI3_cancellation_unclear"]["subscription_procedure_notice"]
        text = render_subscription_procedure_notice(notice, None, "u-1")
        self.assertEqual(text, notice["body"])

    def test_cancellation_intent_replaces_placeholder_with_portal_url(self):
        notice = TEST_CASES["CI1_cancellation_intent_clear"]["subscription_procedure_notice"]
        provider = InMemoryPortalLinkProvider(url="https://billing.stripe.com/p/session/abc123")
        text = render_subscription_procedure_notice(notice, provider, "u-1")
        self.assertIn("https://billing.stripe.com/p/session/abc123", text)
        self.assertNotIn("{Stripeカスタマーポータル URL}", text)

    def test_downgrade_intent_replaces_placeholder_with_portal_url(self):
        notice = TEST_CASES["CI2_downgrade_intent"]["subscription_procedure_notice"]
        provider = InMemoryPortalLinkProvider(url="https://billing.stripe.com/p/session/xyz789")
        text = render_subscription_procedure_notice(notice, provider, "u-1")
        self.assertIn("https://billing.stripe.com/p/session/xyz789", text)

    def test_falls_back_when_provider_not_given(self):
        notice = TEST_CASES["CI1_cancellation_intent_clear"]["subscription_procedure_notice"]
        text = render_subscription_procedure_notice(notice, None, "u-1")
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_falls_back_when_user_id_missing(self):
        notice = TEST_CASES["CI1_cancellation_intent_clear"]["subscription_procedure_notice"]
        provider = InMemoryPortalLinkProvider()
        text = render_subscription_procedure_notice(notice, provider, None)
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)

    def test_falls_back_when_provider_returns_none(self):
        notice = TEST_CASES["CI1_cancellation_intent_clear"]["subscription_procedure_notice"]
        provider = InMemoryPortalLinkProvider(url=None)
        text = render_subscription_procedure_notice(notice, provider, "u-1")
        self.assertEqual(text, PORTAL_LINK_UNAVAILABLE_FALLBACK)


class ProcessMemoEventCancellationFlowTest(unittest.TestCase):
    """process_memo_event()にsubscription_procedure_notice対応のstatusが渡された場合の
    統合的な挙動(ポータルリンク解決・カウント対象外)を検証する。"""

    def test_cancellation_intent_reply_includes_resolved_portal_url(self):
        reply_client = InMemoryReplyClient()
        provider = InMemoryPortalLinkProvider(url="https://billing.stripe.com/p/session/abc123")
        result = process_memo_event(
            _make_event(text="解約したいです", user_id="u-1"),
            FixtureLlmClient("CI1_cancellation_intent_clear"),
            reply_client,
            portal_link_provider=provider,
        )

        self.assertTrue(result.reply_sent)
        self.assertIn("https://billing.stripe.com/p/session/abc123", result.reply_text)

    def test_cancellation_unclear_reply_has_no_portal_link(self):
        reply_client = InMemoryReplyClient()
        result = process_memo_event(
            _make_event(text="そろそろ辞めようかな", user_id="u-1"),
            FixtureLlmClient("CI3_cancellation_unclear"),
            reply_client,
        )

        self.assertNotIn("{Stripeカスタマーポータル URL}", result.reply_text)
        self.assertNotIn("https://", result.reply_text)

    def test_cancellation_intent_does_not_increment_usage_counter(self):
        # カウント対象はstatus=="generated"のみ(limit-approaching-notification-design.md 3節)。
        usage_counter = InMemoryUsageCounter()
        reply_client = InMemoryReplyClient()
        process_memo_event(
            _make_event(text="解約したいです", user_id="u-1"),
            FixtureLlmClient("CI1_cancellation_intent_clear"),
            reply_client,
            usage_counter=usage_counter, plan="スモール", month="2026-08",
        )

        self.assertEqual(usage_counter.get_count("u-1", "2026-08"), 0)


class ProcessFollowEventTest(unittest.TestCase):
    """follow-unfollow-event-handling-design.md 1節、残課題の想定テストケース(1)(2)。"""

    def test_follow_event_sends_fixed_welcome_message_without_linking_code(self):
        reply_client = InMemoryReplyClient()
        event = {
            "type": "follow",
            "replyToken": "reply-token-1",
            "source": {"userId": "u-1"},
        }
        result = process_follow_event(event, reply_client)

        self.assertTrue(result.handled)
        self.assertTrue(result.reply_sent)
        self.assertFalse(hasattr(result, "linking_code"))
        sent_text = reply_client.sent[0][1]
        self.assertIn("友だち追加ありがとうございます", sent_text)
        self.assertIn("連携コード(6文字)をお持ちの方", sent_text)
        self.assertIn(APPLICATION_FORM_URL_PLACEHOLDER, sent_text)

    def test_follow_event_uses_form_link_provider_url_when_connected(self):
        reply_client = InMemoryReplyClient()
        provider = InMemoryApplicationFormLinkProvider(url="https://forms.gle/real-form")
        event = {"type": "follow", "replyToken": "reply-token-2", "source": {"userId": "u-1"}}

        process_follow_event(event, reply_client, form_link_provider=provider)

        sent_text = reply_client.sent[0][1]
        self.assertIn("https://forms.gle/real-form", sent_text)
        self.assertNotIn(APPLICATION_FORM_URL_PLACEHOLDER, sent_text)

    def test_follow_event_falls_back_to_placeholder_when_provider_returns_none(self):
        reply_client = InMemoryReplyClient()
        provider = InMemoryApplicationFormLinkProvider(url=None)
        event = {"type": "follow", "replyToken": "reply-token-3", "source": {"userId": "u-1"}}

        process_follow_event(event, reply_client, form_link_provider=provider)

        self.assertIn(APPLICATION_FORM_URL_PLACEHOLDER, reply_client.sent[0][1])

    def test_non_follow_event_is_not_handled(self):
        reply_client = InMemoryReplyClient()
        result = process_follow_event({"type": "message"}, reply_client)

        self.assertFalse(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertEqual(reply_client.sent, [])

    def test_follow_event_without_user_id_sends_no_reply(self):
        reply_client = InMemoryReplyClient()
        event = {"type": "follow", "replyToken": "reply-token-4", "source": {}}

        result = process_follow_event(event, reply_client)

        self.assertTrue(result.handled)
        self.assertFalse(result.reply_sent)
        self.assertEqual(reply_client.sent, [])

    def test_format_welcome_message_without_provider_uses_placeholder(self):
        message = format_welcome_message(None)
        self.assertIn(APPLICATION_FORM_URL_PLACEHOLDER, message)


class ProcessUnfollowEventTest(unittest.TestCase):
    """follow-unfollow-event-handling-design.md 2節、残課題の想定テストケース(3)。
    pending_links・user_profileのいずれにも書き込み・削除が発生しないことは、本venture版が
    そもそもそれらのストアへアクセスする引数を持たない実装(design 2節)であることによって
    構造的に保証される。"""

    def test_unfollow_event_is_handled_with_no_side_effects(self):
        result = process_unfollow_event({"type": "unfollow", "source": {"userId": "u-1"}})
        self.assertTrue(result.handled)

    def test_unfollow_event_handled_even_without_user_id(self):
        result = process_unfollow_event({"type": "unfollow", "source": {}})
        self.assertTrue(result.handled)

    def test_non_unfollow_event_is_not_handled(self):
        result = process_unfollow_event({"type": "message"})
        self.assertFalse(result.handled)


class ProcessPostbackEventTest(unittest.TestCase):
    """checkout-initiation-flow-design.md 2〜3節、フェーズ131「残課題」1点目の実装テスト。"""

    def _linked_profile_store(self, stripe_customer_id=None):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        profile_store.save(
            "u-1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                stripe_customer_id=stripe_customer_id,
            ),
        )
        return profile_store

    def test_linked_user_receives_checkout_url_and_client_receives_built_params(self):
        reply_client = InMemoryReplyClient()
        checkout_session_client = InMemoryCheckoutSessionClient(url="https://checkout.stripe.com/x")
        event = {
            "type": "postback",
            "replyToken": "rt-1",
            "source": {"userId": "u-1"},
            "postback": {"data": START_CHECKOUT_POSTBACK_DATA},
        }

        result = process_postback_event(
            event, checkout_session_client, reply_client, self._linked_profile_store(),
        )

        self.assertTrue(result.handled)
        self.assertTrue(result.reply_sent)
        self.assertEqual(result.checkout_url, "https://checkout.stripe.com/x")
        self.assertEqual(reply_client.sent, [("rt-1", format_checkout_reply_message("https://checkout.stripe.com/x"))])
        self.assertEqual(len(checkout_session_client.calls), 1)
        self.assertEqual(checkout_session_client.calls[0]["mode"], "subscription")
        self.assertEqual(checkout_session_client.calls[0]["client_reference_id"], "u-1")
        self.assertNotIn("customer", checkout_session_client.calls[0])

    def test_existing_stripe_customer_id_is_forwarded_to_params(self):
        checkout_session_client = InMemoryCheckoutSessionClient()
        event = {
            "type": "postback",
            "replyToken": "rt-2",
            "source": {"userId": "u-1"},
            "postback": {"data": START_CHECKOUT_POSTBACK_DATA},
        }

        process_postback_event(
            event, checkout_session_client, InMemoryReplyClient(),
            self._linked_profile_store(stripe_customer_id="cus_existing"),
        )

        self.assertEqual(checkout_session_client.calls[0]["customer"], "cus_existing")

    def test_unlinked_user_gets_linking_required_message_without_calling_checkout_client(self):
        reply_client = InMemoryReplyClient()
        checkout_session_client = InMemoryCheckoutSessionClient()
        event = {
            "type": "postback",
            "replyToken": "rt-3",
            "source": {"userId": "u-unknown"},
            "postback": {"data": START_CHECKOUT_POSTBACK_DATA},
        }

        result = process_postback_event(
            event, checkout_session_client, reply_client, InMemoryUserProfileStore(),
        )

        self.assertTrue(result.handled)
        self.assertIsNone(result.checkout_url)
        self.assertEqual(reply_client.sent, [("rt-3", LINKING_REQUIRED_MESSAGE)])
        self.assertEqual(checkout_session_client.calls, [])

    def test_missing_user_id_gets_linking_required_message(self):
        reply_client = InMemoryReplyClient()
        checkout_session_client = InMemoryCheckoutSessionClient()
        event = {
            "type": "postback", "replyToken": "rt-4", "source": {},
            "postback": {"data": START_CHECKOUT_POSTBACK_DATA},
        }

        result = process_postback_event(
            event, checkout_session_client, reply_client, InMemoryUserProfileStore(),
        )

        self.assertTrue(result.handled)
        self.assertEqual(reply_client.sent, [("rt-4", LINKING_REQUIRED_MESSAGE)])
        self.assertEqual(checkout_session_client.calls, [])

    def test_non_start_checkout_postback_is_not_handled(self):
        checkout_session_client = InMemoryCheckoutSessionClient()
        event = {
            "type": "postback", "replyToken": "rt-5", "source": {"userId": "u-1"},
            "postback": {"data": "action=something_else"},
        }

        result = process_postback_event(
            event, checkout_session_client, InMemoryReplyClient(), self._linked_profile_store(),
        )

        self.assertFalse(result.handled)
        self.assertEqual(checkout_session_client.calls, [])

    def test_missing_postback_data_is_not_handled(self):
        result = process_postback_event(
            {"type": "postback", "source": {"userId": "u-1"}},
            InMemoryCheckoutSessionClient(), InMemoryReplyClient(), self._linked_profile_store(),
        )
        self.assertFalse(result.handled)


class ProcessMessageEventLinkingTest(unittest.TestCase):
    """user-account-linking-design.md 3節の実装(process_message_event)。"""

    def _issue_pending_link(self, store, code="AB12CD", now=None):
        from datetime import datetime, timezone

        issued_at = now or datetime(2026, 8, 23, 0, 0, tzinfo=timezone.utc)
        store.save(
            code,
            PendingLink(
                form_submission_id="form-1",
                business_name="テストクリーニング",
                business_type="独立系",
                email="owner@example.com",
                issued_at=issued_at,
            ),
        )
        return issued_at

    def test_linked_user_is_routed_to_memo_flow(self):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        profile_store.save(
            "u-1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            ),
        )
        linking_store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        event = {
            "replyToken": "reply-token-1",
            "source": {"userId": "u-1"},
            "message": {"type": "text", "text": "壁掛け型2.2kW分解洗浄実施"},
        }

        result = process_message_event(
            event, FixtureLlmClient("G1_basic"), reply_client,
            profile_store, linking_store, datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        self.assertTrue(result.handled)
        self.assertFalse(result.linked_now)
        self.assertIn("作業完了報告メッセージの下書き", result.reply_text)

    def test_unlinked_user_with_matching_code_links_successfully(self):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        linking_store = InMemoryLinkingCodeStore()
        self._issue_pending_link(linking_store, code="AB12CD")
        reply_client = InMemoryReplyClient()
        event = {
            "replyToken": "reply-token-2",
            "source": {"userId": "u-2"},
            "message": {"type": "text", "text": "ab12cd"},
        }

        result = process_message_event(
            event, FixtureLlmClient("G1_basic"), reply_client,
            profile_store, linking_store, datetime(2026, 8, 23, 1, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(result.handled)
        self.assertTrue(result.linked_now)
        self.assertEqual(result.reply_text, LINKING_SUCCESS_MESSAGE)
        self.assertTrue(profile_store.exists("u-2"))
        self.assertIsNone(linking_store.get("AB12CD"))

    def test_unlinked_user_with_expired_code_gets_linking_required_message(self):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        linking_store = InMemoryLinkingCodeStore()
        self._issue_pending_link(
            linking_store, code="AB12CD",
            now=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        reply_client = InMemoryReplyClient()
        event = {
            "replyToken": "reply-token-3",
            "source": {"userId": "u-3"},
            "message": {"type": "text", "text": "AB12CD"},
        }

        result = process_message_event(
            event, FixtureLlmClient("G1_basic"), reply_client,
            profile_store, linking_store, datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        self.assertTrue(result.handled)
        self.assertFalse(result.linked_now)
        self.assertEqual(result.reply_text, LINKING_REQUIRED_MESSAGE)
        self.assertFalse(profile_store.exists("u-3"))

    def test_unlinked_user_sending_ordinary_memo_is_not_routed_to_memo_flow(self):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        linking_store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        event = {
            "replyToken": "reply-token-4",
            "source": {"userId": "u-4"},
            "message": {"type": "text", "text": "壁掛け型2.2kW分解洗浄実施"},
        }

        result = process_message_event(
            event, FixtureLlmClient("G1_basic"), reply_client,
            profile_store, linking_store, datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        self.assertTrue(result.handled)
        self.assertEqual(result.reply_text, LINKING_REQUIRED_MESSAGE)
        self.assertFalse(profile_store.exists("u-4"))

    def test_image_only_event_is_not_handled(self):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        linking_store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        event = {"replyToken": "reply-token-5", "source": {"userId": "u-5"}, "message": {"type": "image"}}

        result = process_message_event(
            event, FixtureLlmClient("G1_basic"), reply_client,
            profile_store, linking_store, datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        self.assertFalse(result.handled)

    def test_missing_user_id_gets_linking_required_message(self):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        linking_store = InMemoryLinkingCodeStore()
        reply_client = InMemoryReplyClient()
        event = {
            "replyToken": "reply-token-6", "source": {},
            "message": {"type": "text", "text": "AB12CD"},
        }

        result = process_message_event(
            event, FixtureLlmClient("G1_basic"), reply_client,
            profile_store, linking_store, datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        self.assertTrue(result.handled)
        self.assertEqual(result.reply_text, LINKING_REQUIRED_MESSAGE)


class DispatchWebhookEventsTest(unittest.TestCase):
    """dispatch_webhook_events()のテスト(フェーズ111・112・113で実装した3つのイベント処理
    関数を実際のevents配列から呼び分ける入口)。"""

    def _linked_profile_store(self):
        from datetime import datetime, timezone

        profile_store = InMemoryUserProfileStore()
        profile_store.save(
            "u-1",
            UserProfile(
                business_name="テストクリーニング", business_type="独立系",
                email="owner@example.com", linked_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            ),
        )
        return profile_store

    def test_follow_event_is_routed_to_process_follow_event(self):
        reply_client = InMemoryReplyClient()
        events = [{"type": "follow", "replyToken": "rt-1", "source": {"userId": "u-1"}}]

        result = dispatch_webhook_events(events, reply_client=reply_client)

        self.assertEqual(len(result.follow_results), 1)
        self.assertTrue(result.follow_results[0].handled)
        self.assertEqual(len(reply_client.sent), 1)

    def test_follow_event_not_processed_without_reply_client(self):
        events = [{"type": "follow", "replyToken": "rt-1", "source": {"userId": "u-1"}}]

        result = dispatch_webhook_events(events)

        self.assertEqual(result.follow_results, [])

    def test_unfollow_event_is_routed_to_process_unfollow_event(self):
        events = [{"type": "unfollow", "source": {"userId": "u-1"}}]

        result = dispatch_webhook_events(events)

        self.assertEqual(len(result.unfollow_results), 1)
        self.assertTrue(result.unfollow_results[0].handled)

    def test_message_event_for_linked_user_is_routed_to_memo_flow(self):
        from datetime import datetime, timezone

        reply_client = InMemoryReplyClient()
        events = [{
            "replyToken": "rt-2",
            "type": "message",
            "source": {"userId": "u-1"},
            "message": {"type": "text", "text": "壁掛け型2.2kW分解洗浄実施"},
        }]

        result = dispatch_webhook_events(
            events,
            reply_client=reply_client,
            llm_call=FixtureLlmClient("G1_basic"),
            profile_store=self._linked_profile_store(),
            linking_store=InMemoryLinkingCodeStore(),
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        self.assertEqual(len(result.message_results), 1)
        self.assertIn("作業完了報告メッセージの下書き", result.message_results[0].reply_text)

    def test_message_event_not_processed_without_linking_store(self):
        from datetime import datetime, timezone

        events = [{
            "replyToken": "rt-3",
            "type": "message",
            "source": {"userId": "u-1"},
            "message": {"type": "text", "text": "壁掛け型2.2kW分解洗浄実施"},
        }]

        result = dispatch_webhook_events(
            events,
            reply_client=InMemoryReplyClient(),
            llm_call=FixtureLlmClient("G1_basic"),
            profile_store=self._linked_profile_store(),
            now=datetime(2026, 8, 23, tzinfo=timezone.utc),
        )

        self.assertEqual(result.message_results, [])

    def test_message_event_not_processed_without_now(self):
        events = [{
            "replyToken": "rt-4",
            "type": "message",
            "source": {"userId": "u-1"},
            "message": {"type": "text", "text": "壁掛け型2.2kW分解洗浄実施"},
        }]

        result = dispatch_webhook_events(
            events,
            reply_client=InMemoryReplyClient(),
            llm_call=FixtureLlmClient("G1_basic"),
            profile_store=self._linked_profile_store(),
            linking_store=InMemoryLinkingCodeStore(),
        )

        self.assertEqual(result.message_results, [])

    def test_unknown_event_type_is_recorded_in_ignored_types(self):
        events = [{"type": "join"}, {"type": "beacon"}]

        result = dispatch_webhook_events(events)

        self.assertEqual(result.ignored_types, ["join", "beacon"])

    def test_mixed_events_are_routed_independently(self):
        reply_client = InMemoryReplyClient()
        events = [
            {"type": "follow", "replyToken": "rt-5", "source": {"userId": "u-2"}},
            {"type": "unfollow", "source": {"userId": "u-3"}},
            {"type": "join"},
        ]

        result = dispatch_webhook_events(events, reply_client=reply_client)

        self.assertEqual(len(result.follow_results), 1)
        self.assertEqual(len(result.unfollow_results), 1)
        self.assertEqual(result.ignored_types, ["join"])
        self.assertEqual(result.message_results, [])
        self.assertEqual(result.postback_results, [])

    def test_postback_event_is_routed_to_process_postback_event(self):
        reply_client = InMemoryReplyClient()
        checkout_session_client = InMemoryCheckoutSessionClient()
        events = [{
            "type": "postback",
            "replyToken": "rt-6",
            "source": {"userId": "u-1"},
            "postback": {"data": START_CHECKOUT_POSTBACK_DATA},
        }]

        result = dispatch_webhook_events(
            events,
            reply_client=reply_client,
            profile_store=self._linked_profile_store(),
            checkout_session_client=checkout_session_client,
        )

        self.assertEqual(len(result.postback_results), 1)
        self.assertTrue(result.postback_results[0].handled)
        self.assertEqual(len(checkout_session_client.calls), 1)

    def test_postback_event_not_processed_without_checkout_session_client(self):
        events = [{
            "type": "postback",
            "replyToken": "rt-7",
            "source": {"userId": "u-1"},
            "postback": {"data": START_CHECKOUT_POSTBACK_DATA},
        }]

        result = dispatch_webhook_events(
            events, reply_client=InMemoryReplyClient(), profile_store=self._linked_profile_store(),
        )

        self.assertEqual(result.postback_results, [])
        self.assertEqual(result.ignored_types, [])


class ValidateLlmOutputTest(unittest.TestCase):
    def test_all_fixture_cases_pass_validation(self):
        for case_id, instance in TEST_CASES.items():
            with self.subTest(case=case_id):
                self.assertEqual(validate_llm_output(instance), [])

    def test_format_reply_text_raises_for_unknown_status(self):
        with self.assertRaises(ValueError):
            format_reply_text({"status": "unexpected_status"})


class VerifyLineSignatureTest(unittest.TestCase):
    """verify_line_signature()のテスト(webhook-http-entry-point-design.md 1節、フェーズ115)。"""

    CHANNEL_SECRET = "test-channel-secret"

    def _signature_for(self, body: bytes) -> str:
        import base64
        import hashlib
        import hmac

        digest = hmac.new(self.CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    def test_correct_signature_is_accepted(self):
        body = b'{"events": []}'
        self.assertTrue(verify_line_signature(body, self._signature_for(body), self.CHANNEL_SECRET))

    def test_incorrect_signature_is_rejected(self):
        body = b'{"events": []}'
        self.assertFalse(verify_line_signature(body, "invalid-signature==", self.CHANNEL_SECRET))

    def test_missing_signature_header_is_rejected(self):
        body = b'{"events": []}'
        self.assertFalse(verify_line_signature(body, None, self.CHANNEL_SECRET))


class ReceiveWebhookTest(unittest.TestCase):
    """receive_webhook()のテスト(webhook-http-entry-point-design.md 2節、フェーズ115)。"""

    CHANNEL_SECRET = "test-channel-secret"

    def _signature_for(self, body: bytes) -> str:
        import base64
        import hashlib
        import hmac

        digest = hmac.new(self.CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    def test_invalid_signature_returns_401_without_dispatching(self):
        reply_client = InMemoryReplyClient()
        body = b'{"events": [{"type": "follow", "replyToken": "rt-1", "source": {"userId": "u-1"}}]}'

        result = receive_webhook(body, "wrong-signature==", self.CHANNEL_SECRET, reply_client=reply_client)

        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.error, "invalid_signature")
        self.assertIsNone(result.dispatch_result)
        self.assertEqual(reply_client.sent, [])

    def test_invalid_json_body_returns_400(self):
        body = b"{not valid json"

        result = receive_webhook(body, self._signature_for(body), self.CHANNEL_SECRET)

        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "invalid_json")

    def test_missing_events_key_returns_400(self):
        body = b'{"foo": "bar"}'

        result = receive_webhook(body, self._signature_for(body), self.CHANNEL_SECRET)

        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.error, "missing_events")

    def test_valid_follow_event_request_returns_200_with_dispatch_result(self):
        reply_client = InMemoryReplyClient()
        body = b'{"events": [{"type": "follow", "replyToken": "rt-1", "source": {"userId": "u-1"}}]}'

        result = receive_webhook(
            body, self._signature_for(body), self.CHANNEL_SECRET, reply_client=reply_client,
        )

        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.error)
        self.assertEqual(len(result.dispatch_result.follow_results), 1)
        self.assertEqual(len(reply_client.sent), 1)


class _StubFlaskRequest:
    """functions_frameworkが渡すFlask Requestインターフェースの必要最小限のスタブ。
    本物のflask.Request/functions_frameworkはインストールせず、`get_data()`・
    `headers.get(...)`という同じインターフェースだけを再現する
    (course-set-pashaのtest_cloud_function_webhook.pyと同じ構成)。"""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    def get_data(self) -> bytes:
        return self._body


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント)のテスト(フェーズ116)。

    webhook-http-entry-point-design.md「残課題」だった、実リクエストオブジェクトからの
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
