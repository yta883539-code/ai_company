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
    API_FAILURE_FALLBACK_MESSAGE,
    LENGTH_LIMIT_FALLBACK_MESSAGE,
    PLAN_MONTHLY_LIMITS,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    VALIDATION_FAILURE_FALLBACK_MESSAGE,
    InMemoryPortalLinkProvider,
    InMemoryReplyClient,
    InMemoryUsageCounter,
    LlmApiError,
    ReplyApiError,
    build_usage_notice,
    format_reply_text,
    process_memo_event,
    render_subscription_procedure_notice,
    validate_llm_output,
)
from post_generation_checks import LINE_TEXT_MESSAGE_CHAR_LIMIT  # noqa: E402


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
