#!/usr/bin/env python3
"""cloud_function_webhook.pyの検証用テスト。`python3 test_cloud_function_webhook.py`で実行する。"""

import base64
import hashlib
import hmac
import random

from datetime import datetime, timedelta

from cloud_function_webhook import (
    ALREADY_SUBSCRIBED_NOTICE,
    API_FAILURE_FALLBACK_MESSAGE,
    CONTRACTOR_ONLY_CHECKOUT_NOTICE,
    LINKING_REQUIRED_MESSAGE,
    LINKING_SUCCESS_MESSAGE,
    PAYMENT_SUSPENDED_NOTICE,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    TRIAL_END_BUTTON_LABEL,
    TRIAL_END_QUICK_REPLY,
    TRIAL_PERIOD_OVER_NOTICE,
    VALIDATION_FAILURE_FALLBACK_MESSAGE,
    InMemoryCheckoutSessionClient,
    InMemoryPortalLinkProvider,
    InMemoryReplyClient,
    LlmApiError,
    QuickReplyButton,
    dispatch_webhook_events,
    format_checkout_reply_message,
    format_follow_welcome_message,
    format_trial_end_notification_message,
    process_follow_event,
    process_memo_event,
    process_message_event,
    process_postback_event,
    process_unfollow_event,
    receive_webhook,
    verify_line_signature,
)
from checkout_session import START_CHECKOUT_POSTBACK_DATA, build_start_checkout_postback_data
from usage_counter_workshop import (
    InMemoryUsageCounterStore,
    InMemoryUserProfileStore,
    InMemoryWorkshopStore,
)
from validate_test_cases import TEST_CASES
from workshop_linking import InMemoryLinkingCodeStore, issue_linking_code_on_follow

FEB = datetime(2026, 2, 1, 9, 0, 0)
MAR = datetime(2026, 3, 1, 9, 0, 0)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def _sign(body: bytes, channel_secret: str) -> str:
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def test_verify_line_signature_accepts_correct_signature():
    body = b'{"events": []}'
    secret = "test_channel_secret"
    check("正しい署名はTrue", verify_line_signature(body, _sign(body, secret), secret) is True)


def test_verify_line_signature_rejects_wrong_signature():
    body = b'{"events": []}'
    secret = "test_channel_secret"
    wrong_signature = _sign(body, "different_secret")
    check("誤った署名はFalse", verify_line_signature(body, wrong_signature, secret) is False)


def test_verify_line_signature_rejects_tampered_body():
    secret = "test_channel_secret"
    signature = _sign(b'{"events": []}', secret)
    check(
        "署名生成後にbodyが改ざんされた場合はFalse",
        verify_line_signature(b'{"events": [1]}', signature, secret) is False,
    )


def test_verify_line_signature_rejects_missing_header():
    body = b'{"events": []}'
    secret = "test_channel_secret"
    check("署名ヘッダNoneはFalse", verify_line_signature(body, None, secret) is False)
    check("署名ヘッダ空文字列はFalse", verify_line_signature(body, "", secret) is False)


def test_in_memory_reply_client_records_sent_message_without_quick_reply():
    client = InMemoryReplyClient()
    client.reply("token1", "本文1")
    check("sentに1件記録", client.sent == [("token1", "本文1")])
    check("quick_replies_sentにNoneが1件記録", client.quick_replies_sent == [None])


def test_in_memory_reply_client_records_quick_reply():
    client = InMemoryReplyClient()
    button = QuickReplyButton(label="有料プランへ進む", postback_data=START_CHECKOUT_POSTBACK_DATA)
    client.reply("token2", "本文2", quick_reply=button)
    check("sentとquick_replies_sentのindexが対応", client.sent[0] == ("token2", "本文2"))
    check("quick_replies_sentにボタンが記録", client.quick_replies_sent[0] is button)


def test_trial_end_quick_reply_matches_default_checkout_postback_data():
    check("TRIAL_END_QUICK_REPLY.labelが定数と一致", TRIAL_END_QUICK_REPLY.label == TRIAL_END_BUTTON_LABEL)
    check(
        "TRIAL_END_QUICK_REPLY.postback_dataがcheckout_session.START_CHECKOUT_POSTBACK_DATAと一致"
        "(parse_start_checkout_postback_data()がDEFAULT_CHECKOUT_PLANとして解釈できる形式)",
        TRIAL_END_QUICK_REPLY.postback_data == START_CHECKOUT_POSTBACK_DATA,
    )


def test_format_trial_end_notification_message_includes_time_estimate_when_generation_count_positive():
    message = format_trial_end_notification_message(1)
    check("生成実績の回数が本文に含まれる", "受注内容整理メモ・納品案内・お手入れ案内の生成: 1回" in message)
    check("浮いた時間の行が含まれる(1回×20分=20分)", "浮いた事務作業時間の目安: 約20分" in message)
    check("ボタン誘導の文言が含まれる", "下のボタンから" in message)


def test_format_trial_end_notification_message_scales_minutes_with_count():
    message = format_trial_end_notification_message(3)
    check("複数回の場合は分数が回数分スケールする(3回×20分=60分)", "浮いた事務作業時間の目安: 約60分" in message)


def test_format_trial_end_notification_message_omits_time_estimate_when_generation_count_zero():
    message = format_trial_end_notification_message(0)
    check("生成実績0回が本文に含まれる", "受注内容整理メモ・納品案内・お手入れ案内の生成: 0回" in message)
    check("浮いた時間の行は省略される(訴求にならないため)", "浮いた事務作業時間の目安" not in message)


def test_format_trial_end_notification_message_does_not_embed_postback_data_or_url():
    message = format_trial_end_notification_message(1)
    check(
        "本文中にpostback_dataそのものは埋め込まれない(quickReplyとして別途添付する想定)",
        START_CHECKOUT_POSTBACK_DATA not in message,
    )
    check("本文中にURL(https)は含まれない", "https" not in message)


def test_format_trial_end_notification_message_rejects_negative_count():
    try:
        format_trial_end_notification_message(-1)
        check("負のgeneration_countでValueError", False)
    except ValueError:
        check("負のgeneration_countでValueError", True)


# ---------------------------------------------------------------------------
# process_memo_event()(フェーズ63)
# ---------------------------------------------------------------------------

def _make_event(text: str, *, reply_token: str = "reply-token-1", user_id: str = "U123") -> dict:
    return {
        "type": "message",
        "message": {"type": "text", "text": text},
        "replyToken": reply_token,
        "source": {"userId": user_id},
    }


def _make_follow_event(*, reply_token: str = "reply-token-follow", user_id: str = "U123") -> dict:
    return {
        "type": "follow",
        "replyToken": reply_token,
        "source": {"userId": user_id},
    }


def test_format_follow_welcome_message_embeds_linking_code():
    message = format_follow_welcome_message("ABC234")
    check("連携コードが本文に含まれる", "連携コード: ABC234" in message)
    check("トークに送信するよう案内している", "このトークに送信してください" in message)


def test_process_follow_event_ignores_non_follow_event():
    result = process_follow_event(_make_event("メモです"), InMemoryLinkingCodeStore(), InMemoryReplyClient())
    check("follow以外はhandled=False", result.handled is False)
    check("follow以外は返信もしない", result.reply_sent is False)


def test_process_follow_event_issues_code_and_sends_welcome_message():
    linking_store = InMemoryLinkingCodeStore()
    reply_client = InMemoryReplyClient()
    now = datetime(2026, 9, 9, 12, 0, 0)
    result = process_follow_event(
        _make_follow_event(user_id="U_FOLLOW"), linking_store, reply_client, rng=random.Random(1), now=now,
    )
    check("handled=True", result.handled is True)
    check("返信が送られている", result.reply_sent is True)
    check("linking_codeが6文字返る", result.linking_code is not None and len(result.linking_code) == 6)
    check("pending_linksへ保存されている", linking_store.get(result.linking_code) == ("U_FOLLOW", now))
    check("返信本文にコードが埋め込まれている", f"連携コード: {result.linking_code}" in reply_client.sent[0][1])


def test_process_follow_event_without_user_id_does_not_reply():
    event = {"type": "follow", "replyToken": "r1", "source": {}}
    reply_client = InMemoryReplyClient()
    result = process_follow_event(event, InMemoryLinkingCodeStore(), reply_client)
    check("user_id欠落時はhandled=True", result.handled is True)
    check("user_id欠落時は返信しない", result.reply_sent is False)
    check("user_id欠落時はlinking_codeもNone", result.linking_code is None)
    check("実際に返信は送られていない", reply_client.sent == [])


def test_process_unfollow_event_ignores_non_unfollow_event():
    result = process_unfollow_event(_make_event("メモです"))
    check("unfollow以外はhandled=False", result.handled is False)


def test_process_unfollow_event_returns_handled_without_user_id():
    event = {"type": "unfollow", "source": {}}
    result = process_unfollow_event(event)
    check("user_id欠落でもhandled=True", result.handled is True)


def test_process_unfollow_event_returns_handled_for_known_user():
    event = {"type": "unfollow", "source": {"userId": "U_UNFOLLOW"}}
    result = process_unfollow_event(event)
    check("unfollowはhandled=True", result.handled is True)


class _StubLlmCall:
    """呼び出しのたびにinstancesを順に返すスタブ。空になったら最後の値を返し続ける。"""

    def __init__(self, instances):
        self._instances = list(instances)
        self.calls = []

    def generate(self, memo_text, retry_context=None):
        self.calls.append((memo_text, retry_context))
        if len(self._instances) > 1:
            return self._instances.pop(0)
        return self._instances[0]


class _AlwaysFailingLlmCall:
    def __init__(self):
        self.calls = 0

    def generate(self, memo_text, retry_context=None):
        self.calls += 1
        raise LlmApiError("stub failure")


def test_process_memo_event_ignores_non_text_message():
    reply_client = InMemoryReplyClient()
    result = process_memo_event(
        {"message": {"type": "image"}, "replyToken": "t", "source": {"userId": "U1"}},
        _StubLlmCall([TEST_CASES["G1_new_basic"]]),
        reply_client,
    )
    check("非テキストメッセージはhandled=False", result.handled is False)
    check("非テキストメッセージは返信しない", reply_client.sent == [])


def test_process_memo_event_generated_includes_three_outputs():
    reply_client = InMemoryReplyClient()
    result = process_memo_event(_make_event("新規、ブリティッシュ、牛革"), _StubLlmCall([TEST_CASES["G1_new_basic"]]), reply_client)
    check("generatedはhandled=True", result.handled is True)
    check("generatedは返信送信済み", result.reply_sent is True)
    check("受注内容整理メモの見出しを含む", "【受注内容整理メモ】" in result.reply_text)
    check("納品案内の下書きの見出しを含む", "【納品案内の下書き】" in result.reply_text)
    check("お手入れ案内の下書きの見出しを含む", "【お手入れ案内の下書き】" in result.reply_text)
    check("order_summary.bodyが含まれる", TEST_CASES["G1_new_basic"]["order_summary"]["body"] in result.reply_text)


def test_process_memo_event_out_of_scope_returns_message_as_is():
    reply_client = InMemoryReplyClient()
    result = process_memo_event(_make_event("会員は何人まで?"), _StubLlmCall([TEST_CASES["OOS1_membership_question"]]), reply_client)
    check("out_of_scopeはout_of_scope_messageをそのまま返す", result.reply_text == TEST_CASES["OOS1_membership_question"]["out_of_scope_message"])


def test_process_memo_event_insufficient_input_returns_missing_fields_request():
    reply_client = InMemoryReplyClient()
    result = process_memo_event(_make_event("鞍作って"), _StubLlmCall([TEST_CASES["II1_no_category"]]), reply_client)
    check("insufficient_inputはmissing_fields_requestをそのまま返す", result.reply_text == TEST_CASES["II1_no_category"]["missing_fields_request"])


def _cancellation_intent_case_with_portal_placeholder():
    """TEST_CASES["C1_cancellation_intent"]のbodyにはプレースホルダ文字列
    "{Stripeカスタマーポータル URL}" 自体が literal には含まれていない(文面例のみで、
    実際の置換対象マーカーはsubscription-cancellation-flow-design.md 「1. 解約意図検知時の
    案内メッセージ」記載の別の箇所)ため、置換ロジック(render_subscription_procedure_notice)
    自体の検証にはプレースホルダを明示的に含む合成フィクスチャを使う。"""
    from cloud_function_webhook import PORTAL_LINK_PLACEHOLDER

    case = {k: v for k, v in TEST_CASES["C1_cancellation_intent"].items()}
    notice = dict(case["subscription_procedure_notice"])
    notice["body"] = f"下記リンクから解約手続きをお願いいたします。\n{PORTAL_LINK_PLACEHOLDER}"
    case["subscription_procedure_notice"] = notice
    return case


def test_process_memo_event_cancellation_intent_replaces_portal_placeholder():
    reply_client = InMemoryReplyClient()
    provider = InMemoryPortalLinkProvider(url="https://billing.stripe.com/p/session/abc123")
    case = _cancellation_intent_case_with_portal_placeholder()
    result = process_memo_event(
        _make_event("解約したい"), _StubLlmCall([case]), reply_client,
        portal_link_provider=provider,
    )
    check("cancellation_intentはプレースホルダを実URLへ置換する", "https://billing.stripe.com/p/session/abc123" in result.reply_text)
    check("cancellation_intentはプレースホルダ文字列を残さない", "{Stripeカスタマーポータル URL}" not in result.reply_text)


def test_process_memo_event_cancellation_intent_falls_back_when_provider_missing():
    reply_client = InMemoryReplyClient()
    case = _cancellation_intent_case_with_portal_placeholder()
    result = process_memo_event(_make_event("解約したい"), _StubLlmCall([case]), reply_client)
    check("provider未接続時は安全側フォールバック文言を返す", result.reply_text == PORTAL_LINK_UNAVAILABLE_FALLBACK)


def test_process_memo_event_cancellation_unclear_does_not_need_provider():
    reply_client = InMemoryReplyClient()
    result = process_memo_event(_make_event("やめようかな"), _StubLlmCall([TEST_CASES["C3_cancellation_unclear"]]), reply_client)
    check("cancellation_unclearはincludes_portal_link=Falseのためbodyをそのまま返す", result.reply_text == TEST_CASES["C3_cancellation_unclear"]["subscription_procedure_notice"]["body"])


def test_process_memo_event_checkout_intent_returns_notice_body():
    reply_client = InMemoryReplyClient()
    result = process_memo_event(_make_event("有料プラン始めたい"), _StubLlmCall([TEST_CASES["CO1_checkout_intent"]]), reply_client)
    check("checkout_intentはcheckout_notice.bodyを返す", result.reply_text == TEST_CASES["CO1_checkout_intent"]["checkout_notice"]["body"])


def test_process_memo_event_contractor_transfer_expired_notice_returns_body():
    reply_client = InMemoryReplyClient()
    result = process_memo_event(_make_event("(自動注入文脈)"), _StubLlmCall([TEST_CASES["CTE1_contractor_transfer_expired_notice"]]), reply_client)
    check(
        "contractor_transfer_expired_noticeはcontractor_transfer_expired_notice.bodyを返す",
        result.reply_text == TEST_CASES["CTE1_contractor_transfer_expired_notice"]["contractor_transfer_expired_notice"]["body"],
    )


def test_process_memo_event_retries_once_on_validation_error_then_succeeds():
    broken = dict(TEST_CASES["G1_new_basic"])
    broken["delivery_notice"] = dict(broken["delivery_notice"])
    broken["delivery_notice"]["category"] = "repair"  # 厳守事項4違反(category不一致)
    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([broken, TEST_CASES["G1_new_basic"]])
    result = process_memo_event(_make_event("新規、ブリティッシュ、牛革"), llm_call, reply_client)
    check("1回目の検証エラー後、再生成して成功する", result.reply_sent is True)
    check("retried=Trueが記録される", result.retried is True)
    check("再生成は都度1回だけ(合計2回呼ばれる)", len(llm_call.calls) == 2)
    check("2回目の呼び出しにretry_contextが渡される", llm_call.calls[1][1] is not None)


def test_process_memo_event_falls_back_after_second_validation_error():
    broken = dict(TEST_CASES["G1_new_basic"])
    broken["delivery_notice"] = dict(broken["delivery_notice"])
    broken["delivery_notice"]["category"] = "repair"
    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([broken, broken])
    result = process_memo_event(_make_event("新規、ブリティッシュ、牛革"), llm_call, reply_client)
    check("2回とも検証エラーならフォールバック文言を返す", result.reply_text == VALIDATION_FAILURE_FALLBACK_MESSAGE)
    check("validation_errorsが記録される", len(result.validation_errors) > 0)
    check("再生成は1回のみ(合計2回呼ばれる、3回目は呼ばれない)", len(llm_call.calls) == 2)


def test_process_memo_event_falls_back_after_llm_api_error_retried_once():
    reply_client = InMemoryReplyClient()
    llm_call = _AlwaysFailingLlmCall()
    result = process_memo_event(_make_event("新規、ブリティッシュ、牛革"), llm_call, reply_client)
    check("LLM API呼び出し失敗時はAPI_FAILURE_FALLBACK_MESSAGEを返す", result.reply_text == API_FAILURE_FALLBACK_MESSAGE)
    check("api_failure=Trueが記録される", result.api_failure is True)
    check("即時リトライは1回のみ(合計2回呼ばれる)", llm_call.calls == 2)


# ---------------------------------------------------------------------------
# process_memo_event()のusage_counter_workshop.py連携(フェーズ64)
# ---------------------------------------------------------------------------

def _make_stores():
    return InMemoryUserProfileStore(), InMemoryWorkshopStore(), InMemoryUsageCounterStore()


def test_process_memo_event_blocks_with_trial_period_over_notice():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_TRIAL_OVER", "W_TRIAL_OVER")
    workshops.set_plan("W_TRIAL_OVER", "standard")
    workshops.set_members("W_TRIAL_OVER", "U_TRIAL_OVER", ["U_TRIAL_OVER"])
    workshops.set_trial_start_at("W_TRIAL_OVER", FEB)
    workshops.set_trial_generation_used("W_TRIAL_OVER", True)

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_TRIAL_OVER"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=MAR,
    )
    check("トライアル終了時はTRIAL_PERIOD_OVER_NOTICEを返す", result.reply_text == TRIAL_PERIOD_OVER_NOTICE)
    check("トライアル終了時はgeneration_paused=True", result.generation_paused is True)
    check("トライアル終了時はLLMを呼び出さない", llm_call.calls == [])
    check(
        "トライアル終了時はTRIAL_END_QUICK_REPLYを添付する",
        reply_client.quick_replies_sent[0] is TRIAL_END_QUICK_REPLY,
    )


def test_process_memo_event_allows_generation_when_subscription_active_despite_trial_over():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_ACTIVE", "W_ACTIVE")
    workshops.set_plan("W_ACTIVE", "standard")
    workshops.set_members("W_ACTIVE", "U_ACTIVE", ["U_ACTIVE"])
    workshops.set_trial_start_at("W_ACTIVE", FEB)
    workshops.set_trial_generation_used("W_ACTIVE", True)
    workshops.set_subscription_status("W_ACTIVE", "active")

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_ACTIVE"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=MAR,
    )
    check("有償契約中(active)はトライアル終了後も通常どおり生成できる", result.reply_sent is True)
    check("有償契約中は通常の生成本文を返す", "【受注内容整理メモ】" in result.reply_text)
    check("有償契約中は生成一時停止フラグが立たない", result.generation_paused is False)


def test_process_memo_event_blocks_with_payment_suspended_notice_after_grace_period():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_PAY_SUSPENDED", "W_PAY_SUSPENDED")
    workshops.set_plan("W_PAY_SUSPENDED", "standard")
    workshops.set_members("W_PAY_SUSPENDED", "U_PAY_SUSPENDED", ["U_PAY_SUSPENDED"])
    workshops.set_trial_start_at("W_PAY_SUSPENDED", FEB)
    workshops.set_trial_generation_used("W_PAY_SUSPENDED", True)
    workshops.set_subscription_status("W_PAY_SUSPENDED", "past_due")
    workshops.set_payment_failure_detected_at("W_PAY_SUSPENDED", MAR)

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_PAY_SUSPENDED"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=MAR + timedelta(days=8),
    )
    check("猶予期間超過時はPAYMENT_SUSPENDED_NOTICEを返す", result.reply_text == PAYMENT_SUSPENDED_NOTICE)
    check("猶予期間超過時はpayment_suspended=True", result.payment_suspended is True)
    check("猶予期間超過時はLLMを呼び出さない", llm_call.calls == [])


def test_process_memo_event_allows_generation_within_payment_failure_grace_period():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_PAY_GRACE", "W_PAY_GRACE")
    workshops.set_plan("W_PAY_GRACE", "standard")
    workshops.set_members("W_PAY_GRACE", "U_PAY_GRACE", ["U_PAY_GRACE"])
    workshops.set_trial_start_at("W_PAY_GRACE", FEB)
    workshops.set_trial_generation_used("W_PAY_GRACE", True)
    workshops.set_subscription_status("W_PAY_GRACE", "past_due")
    workshops.set_payment_failure_detected_at("W_PAY_GRACE", MAR)

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_PAY_GRACE"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=MAR + timedelta(days=3),
    )
    check("猶予期間内は通常どおり生成できる", result.reply_sent is True)
    check("猶予期間内は生成一時停止フラグが立たない", result.payment_suspended is False)


def test_process_memo_event_appends_trial_end_notification_on_first_success():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_FIRST", "W_FIRST")
    workshops.set_plan("W_FIRST", "standard")
    workshops.set_members("W_FIRST", "U_FIRST", ["U_FIRST"])

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_FIRST"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=FEB,
    )
    check("生涯最初の生成成功でtrial_end_notification_sent=True", result.trial_end_notification_sent is True)
    check(
        "返信本文末尾にトライアル終了通知が便乗する",
        format_trial_end_notification_message(1) in result.reply_text,
    )
    check(
        "トライアル終了通知にはTRIAL_END_QUICK_REPLYを添付する",
        reply_client.quick_replies_sent[0] is TRIAL_END_QUICK_REPLY,
    )
    check("trial_generation_usedがTrueへ更新される", workshops.get_trial_generation_used("W_FIRST") is True)
    check("trial_end_notified_atがnowで書き込まれる", workshops.get_trial_end_notified_at("W_FIRST") == FEB)
    check("usage_counter_storeにも加算される", counters.get("W_FIRST") is not None)


def test_process_memo_event_does_not_append_trial_end_notification_on_second_success():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_SECOND", "W_SECOND")
    workshops.set_plan("W_SECOND", "standard")
    workshops.set_members("W_SECOND", "U_SECOND", ["U_SECOND"])

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_SECOND"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=FEB,
    )
    second_result = process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_SECOND"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=MAR,
    )
    check("2回目の生成成功ではtrial_end_notification_sent=False", second_result.trial_end_notification_sent is False)
    check(
        "2回目の返信本文にはトライアル終了通知が含まれない",
        format_trial_end_notification_message(1) not in second_result.reply_text,
    )
    check("2回目もquick_replyは付与しない", reply_client.quick_replies_sent[1] is None)


def test_process_memo_event_skips_store_integration_when_stores_not_provided():
    """従来通りuser_profile_store等を渡さない場合は、ストア連携をスキップし
    LLM呼び出し前のブロック判定・トライアル終了通知の便乗のいずれも発生しないことを
    確認する(後方互換性、フェーズ63以前の呼び出し方が引き続き動作する)。"""
    reply_client = InMemoryReplyClient()
    result = process_memo_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_NO_STORES"),
        _StubLlmCall([TEST_CASES["G1_new_basic"]]), reply_client,
    )
    check("ストア未接続時は通常どおり生成できる", result.reply_sent is True)
    check("ストア未接続時はtrial_end_notification_sent=False", result.trial_end_notification_sent is False)
    check("ストア未接続時はgeneration_paused=False", result.generation_paused is False)
    check("ストア未接続時はpayment_suspended=False", result.payment_suspended is False)


# ---------------------------------------------------------------------------
# process_message_event()(フェーズ69)
# ---------------------------------------------------------------------------

def test_process_message_event_delegates_when_stores_not_provided():
    """3ストアが1つでも欠けている場合は連携判定を行わず、従来通りprocess_memo_event()へ
    直接委譲する(後方互換、フェーズ68以前の呼び出し方が引き続き動作する)。"""
    reply_client = InMemoryReplyClient()
    result = process_message_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_NO_LINKING"),
        _StubLlmCall([TEST_CASES["G1_new_basic"]]), reply_client,
    )
    check("ストア未接続時は通常どおり生成できる", result.reply_sent is True)
    check("ストア未接続時は生成本文がそのまま返る", "【受注内容整理メモ】" in result.reply_text)


def test_process_message_event_delegates_when_user_already_linked():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_LINKED", "W_LINKED")
    workshops.set_plan("W_LINKED", "standard")
    workshops.set_members("W_LINKED", "U_LINKED", ["U_LINKED"])
    linking_store = InMemoryLinkingCodeStore()

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_message_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_LINKED"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        linking_store=linking_store,
    )
    check("連携済みuser_idは通常どおり生成できる", result.reply_sent is True)
    check("連携済みuser_idは生成本文がそのまま返る", "【受注内容整理メモ】" in result.reply_text)
    check("連携済みuser_idはLLMが呼ばれる", len(llm_call.calls) == 1)


def test_process_message_event_creates_workshop_on_valid_linking_code():
    profiles, workshops, counters = _make_stores()
    linking_store = InMemoryLinkingCodeStore()
    now = datetime(2026, 9, 9, 12, 0, 0)
    code = issue_linking_code_on_follow("U_NEW", linking_store, now, random.Random(1))

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_message_event(
        _make_event(code, user_id="U_NEW"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        linking_store=linking_store, now=now,
    )
    check("有効な連携コード送信時はhandled=True", result.handled is True)
    check("有効な連携コード送信時は返信送信済み", result.reply_sent is True)
    check("有効な連携コード送信時はLINKING_SUCCESS_MESSAGEを返す", result.reply_text == LINKING_SUCCESS_MESSAGE)
    check("有効な連携コード送信時はLLMを呼び出さない(依頼メモとして処理しない)", llm_call.calls == [])
    check("user_profileにworkshop_idが紐付く", profiles.get_workshop_id("U_NEW") is not None)
    check("連携コードは使い切りで消費される", linking_store.get(code) is None)


def test_process_message_event_replies_linking_required_on_invalid_text():
    profiles, workshops, counters = _make_stores()
    linking_store = InMemoryLinkingCodeStore()

    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = process_message_event(
        _make_event("新規、ブリティッシュ、牛革", user_id="U_UNLINKED"),
        llm_call, reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        linking_store=linking_store,
    )
    check("未連携かつコード不一致時はLINKING_REQUIRED_MESSAGEを返す", result.reply_text == LINKING_REQUIRED_MESSAGE)
    check("未連携かつコード不一致時はLLMを呼び出さない", llm_call.calls == [])
    check("未連携かつコード不一致時はworkshopが作られない", profiles.get_workshop_id("U_UNLINKED") is None)


def test_process_message_event_replies_linking_required_when_user_id_missing():
    profiles, workshops, counters = _make_stores()
    linking_store = InMemoryLinkingCodeStore()
    event = {
        "type": "message",
        "message": {"type": "text", "text": "ABC234"},
        "replyToken": "r1",
        "source": {},
    }
    reply_client = InMemoryReplyClient()
    result = process_message_event(
        event, _StubLlmCall([TEST_CASES["G1_new_basic"]]), reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        linking_store=linking_store,
    )
    check("user_id欠落時はLINKING_REQUIRED_MESSAGEを返す", result.reply_text == LINKING_REQUIRED_MESSAGE)


# ---------------------------------------------------------------------------
# process_postback_event()(フェーズ71)
# ---------------------------------------------------------------------------

def _make_postback_event(
    data: str, *, reply_token: str = "reply-token-postback", user_id: str = "U_CONTRACTOR"
) -> dict:
    return {
        "type": "postback",
        "postback": {"data": data},
        "replyToken": reply_token,
        "source": {"userId": user_id},
    }


def _link_contractor_workshop(profiles, workshops, user_id: str, workshop_id: str) -> None:
    """process_postback_event()のテスト共通セットアップ: user_idを契約者とするworkshopを
    連携する(profiles.link()・workshops.set_members()の組み合わせ)。"""
    profiles.link(user_id, workshop_id)
    workshops.set_plan(workshop_id, "standard")
    workshops.set_members(workshop_id, user_id, [user_id])


def test_process_postback_event_ignores_unknown_postback_data():
    profiles, workshops, _ = _make_stores()
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()
    result = process_postback_event(
        _make_postback_event("action=unknown"), checkout_client, reply_client, profiles, workshops,
    )
    check("未知のpostback dataはhandled=False", result.handled is False)
    check("未知のpostback dataは返信しない", result.reply_sent is False)
    check("未知のpostback dataはCheckout Sessionを作らない", checkout_client.calls == [])


def test_process_postback_event_creates_checkout_session_for_linked_contractor():
    profiles, workshops, _ = _make_stores()
    _link_contractor_workshop(profiles, workshops, "U_CONTRACTOR", "W_CHECKOUT")
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()

    result = process_postback_event(
        _make_postback_event(START_CHECKOUT_POSTBACK_DATA, user_id="U_CONTRACTOR"),
        checkout_client, reply_client, profiles, workshops,
    )
    check("契約者本人・未契約workshopではhandled=True", result.handled is True)
    check("Checkout SessionのURLが返信される", result.reply_sent is True)
    check("checkout_urlがInMemoryCheckoutSessionClientの固定URL", result.checkout_url == "https://checkout.stripe.com/stub-session")
    check(
        "返信本文はformat_checkout_reply_message()と一致する",
        reply_client.sent[0][1] == format_checkout_reply_message(result.checkout_url),
    )
    check("プラン未指定時はDEFAULT_CHECKOUT_PLAN(standard)でparamsが組み立てられる", checkout_client.calls[0]["line_items"][0]["price"].endswith("standard_PLACEHOLDER"))
    check("client_reference_idはworkshop_id", checkout_client.calls[0]["client_reference_id"] == "W_CHECKOUT")
    check("既存stripe_customer_idが無い場合はcustomerキーを含まない", "customer" not in checkout_client.calls[0])


def test_process_postback_event_uses_plan_id_from_postback_data():
    profiles, workshops, _ = _make_stores()
    _link_contractor_workshop(profiles, workshops, "U_CONTRACTOR", "W_LIGHT")
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()

    process_postback_event(
        _make_postback_event(build_start_checkout_postback_data("light"), user_id="U_CONTRACTOR"),
        checkout_client, reply_client, profiles, workshops,
    )
    check(
        "plan=light指定時はlightプランのStripe Price IDが使われる",
        checkout_client.calls[0]["line_items"][0]["price"].endswith("light_PLACEHOLDER"),
    )


def test_process_postback_event_reuses_existing_stripe_customer_id():
    profiles, workshops, _ = _make_stores()
    _link_contractor_workshop(profiles, workshops, "U_CONTRACTOR", "W_REPEAT")
    workshops.set_stripe_customer_id("W_REPEAT", "cus_existing123")
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()

    process_postback_event(
        _make_postback_event(START_CHECKOUT_POSTBACK_DATA, user_id="U_CONTRACTOR"),
        checkout_client, reply_client, profiles, workshops,
    )
    check("既存stripe_customer_idがある場合はcustomerキーに設定される", checkout_client.calls[0]["customer"] == "cus_existing123")


def test_process_postback_event_replies_linking_required_when_unlinked():
    profiles, workshops, _ = _make_stores()
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()

    result = process_postback_event(
        _make_postback_event(START_CHECKOUT_POSTBACK_DATA, user_id="U_UNLINKED"),
        checkout_client, reply_client, profiles, workshops,
    )
    check("未連携user_idはhandled=True", result.handled is True)
    check("未連携user_idはLINKING_REQUIRED_MESSAGEを返す", reply_client.sent[0][1] == LINKING_REQUIRED_MESSAGE)
    check("未連携user_idはCheckout Sessionを作らない", checkout_client.calls == [])


def test_process_postback_event_replies_linking_required_when_user_id_missing():
    profiles, workshops, _ = _make_stores()
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()
    event = {"type": "postback", "postback": {"data": START_CHECKOUT_POSTBACK_DATA}, "replyToken": "r1", "source": {}}

    result = process_postback_event(event, checkout_client, reply_client, profiles, workshops)
    check("user_id欠落時もhandled=True", result.handled is True)
    check("user_id欠落時はLINKING_REQUIRED_MESSAGEを返す", reply_client.sent[0][1] == LINKING_REQUIRED_MESSAGE)


def test_process_postback_event_rejects_non_contractor_member():
    profiles, workshops, _ = _make_stores()
    profiles.link("U_CONTRACTOR", "W_MULTI")
    workshops.set_plan("W_MULTI", "multi_craftsman")
    workshops.set_members("W_MULTI", "U_CONTRACTOR", ["U_CONTRACTOR", "U_MEMBER"])
    profiles.link("U_MEMBER", "W_MULTI")
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()

    result = process_postback_event(
        _make_postback_event(START_CHECKOUT_POSTBACK_DATA, user_id="U_MEMBER"),
        checkout_client, reply_client, profiles, workshops,
    )
    check("契約者以外はhandled=True", result.handled is True)
    check("契約者以外はCONTRACTOR_ONLY_CHECKOUT_NOTICEを返す", reply_client.sent[0][1] == CONTRACTOR_ONLY_CHECKOUT_NOTICE)
    check("契約者以外はCheckout Sessionを作らない", checkout_client.calls == [])


def test_process_postback_event_rejects_when_already_subscribed():
    profiles, workshops, _ = _make_stores()
    _link_contractor_workshop(profiles, workshops, "U_CONTRACTOR", "W_ACTIVE_CHECKOUT")
    workshops.set_subscription_status("W_ACTIVE_CHECKOUT", "active")
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()

    result = process_postback_event(
        _make_postback_event(START_CHECKOUT_POSTBACK_DATA, user_id="U_CONTRACTOR"),
        checkout_client, reply_client, profiles, workshops,
    )
    check("契約中(active)はhandled=True", result.handled is True)
    check("契約中(active)はALREADY_SUBSCRIBED_NOTICEを返す", reply_client.sent[0][1] == ALREADY_SUBSCRIBED_NOTICE)
    check("契約中(active)はCheckout Sessionを作らない", checkout_client.calls == [])


# ---------------------------------------------------------------------------
# dispatch_webhook_events() / receive_webhook()(フェーズ65、フェーズ71でpostbackを追加)
# ---------------------------------------------------------------------------

def test_dispatch_webhook_events_routes_message_event_to_process_memo_event():
    reply_client = InMemoryReplyClient()
    llm_call = _StubLlmCall([TEST_CASES["G1_new_basic"]])
    result = dispatch_webhook_events(
        [_make_event("新規、ブリティッシュ、牛革")],
        llm_call=llm_call,
        reply_client=reply_client,
    )
    check("message1件がmessage_resultsに1件記録される", len(result.message_results) == 1)
    check("message_resultsの中身はhandled=True", result.message_results[0].handled is True)
    check("ignored_typesは空", result.ignored_types == [])
    check("実際に返信が送られている", len(reply_client.sent) == 1)


def test_dispatch_webhook_events_routes_valid_linking_code_to_workshop_creation():
    """フェーズ69: dispatch_webhook_events()がlinking_store等を渡された場合、messageの
    委譲先がprocess_message_event()になり、連携コード送信をworkshop作成として処理できる
    ことをdispatch経由で確認する。"""
    profiles, workshops, counters = _make_stores()
    linking_store = InMemoryLinkingCodeStore()
    now = datetime(2026, 9, 9, 12, 0, 0)
    code = issue_linking_code_on_follow("U_DISPATCH_NEW", linking_store, now, random.Random(2))

    reply_client = InMemoryReplyClient()
    result = dispatch_webhook_events(
        [_make_event(code, user_id="U_DISPATCH_NEW")],
        llm_call=_StubLlmCall([TEST_CASES["G1_new_basic"]]),
        reply_client=reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        linking_store=linking_store, now=now,
    )
    check("連携コード送信はmessage_resultsに1件記録される", len(result.message_results) == 1)
    check("連携コード送信はLINKING_SUCCESS_MESSAGEを返す", result.message_results[0].reply_text == LINKING_SUCCESS_MESSAGE)
    check("連携コード送信でworkshopが作られる", profiles.get_workshop_id("U_DISPATCH_NEW") is not None)


def test_dispatch_webhook_events_records_ignored_types_for_non_message_events():
    events = [
        {"type": "follow", "source": {"userId": "U1"}},
        {"type": "unfollow", "source": {"userId": "U2"}},
        {"type": "postback", "postback": {"data": "action=start_checkout"}},
    ]
    result = dispatch_webhook_events(
        events, llm_call=_StubLlmCall([TEST_CASES["G1_new_basic"]]), reply_client=InMemoryReplyClient(),
    )
    check("follow/unfollow/postbackはmessage_resultsに含まれない", result.message_results == [])
    check("unfollowはフェーズ70からunfollow_resultsに1件記録される", len(result.unfollow_results) == 1)
    check(
        "ignored_typesにはfollow・postbackのみ記録される(unfollowは常に処理されるため対象外)",
        result.ignored_types == ["follow", "postback"],
    )


def test_dispatch_webhook_events_routes_unfollow_event_to_process_unfollow_event():
    result = dispatch_webhook_events(
        [{"type": "unfollow", "source": {"userId": "U_UNFOLLOW_DISPATCH"}}],
    )
    check("unfollow1件がunfollow_resultsに1件記録される", len(result.unfollow_results) == 1)
    check("unfollow_resultsの中身はhandled=True", result.unfollow_results[0].handled is True)
    check("ignored_typesは空", result.ignored_types == [])


def test_dispatch_webhook_events_skips_message_when_llm_call_missing():
    result = dispatch_webhook_events(
        [_make_event("新規、ブリティッシュ、牛革")], llm_call=None, reply_client=InMemoryReplyClient(),
    )
    check("llm_call未接続時はmessage_resultsが空", result.message_results == [])


def test_dispatch_webhook_events_skips_message_when_reply_client_missing():
    result = dispatch_webhook_events(
        [_make_event("新規、ブリティッシュ、牛革")],
        llm_call=_StubLlmCall([TEST_CASES["G1_new_basic"]]),
        reply_client=None,
    )
    check("reply_client未接続時はmessage_resultsが空", result.message_results == [])


def test_dispatch_webhook_events_passes_store_kwargs_through_to_process_memo_event():
    profiles, workshops, counters = _make_stores()
    profiles.link("U_WS", "W_WS")
    workshops.set_plan("W_WS", "standard")
    workshops.set_members("W_WS", "U_WS", ["U_WS"])

    reply_client = InMemoryReplyClient()
    result = dispatch_webhook_events(
        [_make_event("新規、ブリティッシュ、牛革", user_id="U_WS")],
        llm_call=_StubLlmCall([TEST_CASES["G1_new_basic"]]),
        reply_client=reply_client,
        user_profile_store=profiles, workshop_store=workshops, usage_counter_store=counters,
        now=FEB,
    )
    check(
        "workshop連携済みuser_idではストア連携が実際に働く(trial_end_notification_sent=True)",
        result.message_results[0].trial_end_notification_sent is True,
    )


def test_dispatch_webhook_events_routes_follow_event_to_process_follow_event():
    linking_store = InMemoryLinkingCodeStore()
    reply_client = InMemoryReplyClient()
    result = dispatch_webhook_events(
        [_make_follow_event(user_id="U_FOLLOW_DISPATCH")],
        reply_client=reply_client,
        linking_store=linking_store,
        rng=random.Random(3),
    )
    check("follow1件がfollow_resultsに1件記録される", len(result.follow_results) == 1)
    check("follow_resultsの中身はhandled=True", result.follow_results[0].handled is True)
    check("ignored_typesは空", result.ignored_types == [])
    check("実際に返信が送られている", len(reply_client.sent) == 1)


def test_dispatch_webhook_events_skips_follow_when_linking_store_missing():
    result = dispatch_webhook_events(
        [_make_follow_event()], reply_client=InMemoryReplyClient(), linking_store=None,
    )
    check("linking_store未接続時はfollow_resultsが空", result.follow_results == [])
    check("linking_store未接続時はignored_typesに記録される", result.ignored_types == ["follow"])


def test_dispatch_webhook_events_skips_follow_when_reply_client_missing():
    result = dispatch_webhook_events(
        [_make_follow_event()], reply_client=None, linking_store=InMemoryLinkingCodeStore(),
    )
    check("reply_client未接続時はfollow_resultsが空", result.follow_results == [])
    check("reply_client未接続時はignored_typesに記録される", result.ignored_types == ["follow"])


def test_dispatch_webhook_events_routes_postback_event_to_process_postback_event():
    profiles, workshops, _ = _make_stores()
    _link_contractor_workshop(profiles, workshops, "U_CONTRACTOR", "W_DISPATCH_CHECKOUT")
    reply_client = InMemoryReplyClient()
    checkout_client = InMemoryCheckoutSessionClient()

    result = dispatch_webhook_events(
        [_make_postback_event(START_CHECKOUT_POSTBACK_DATA, user_id="U_CONTRACTOR")],
        reply_client=reply_client,
        user_profile_store=profiles, workshop_store=workshops,
        checkout_session_client=checkout_client,
    )
    check("postback1件がpostback_resultsに1件記録される", len(result.postback_results) == 1)
    check("postback_resultsの中身はhandled=True", result.postback_results[0].handled is True)
    check("ignored_typesは空", result.ignored_types == [])
    check("実際に返信が送られている", len(reply_client.sent) == 1)


def test_dispatch_webhook_events_skips_postback_when_checkout_session_client_missing():
    profiles, workshops, _ = _make_stores()
    result = dispatch_webhook_events(
        [_make_postback_event(START_CHECKOUT_POSTBACK_DATA)],
        reply_client=InMemoryReplyClient(),
        user_profile_store=profiles, workshop_store=workshops,
        checkout_session_client=None,
    )
    check("checkout_session_client未接続時はpostback_resultsが空", result.postback_results == [])
    check("checkout_session_client未接続時はignored_typesに記録される", result.ignored_types == ["postback"])


def test_dispatch_webhook_events_skips_postback_when_user_profile_store_missing():
    _, workshops, _ = _make_stores()
    result = dispatch_webhook_events(
        [_make_postback_event(START_CHECKOUT_POSTBACK_DATA)],
        reply_client=InMemoryReplyClient(),
        user_profile_store=None, workshop_store=workshops,
        checkout_session_client=InMemoryCheckoutSessionClient(),
    )
    check("user_profile_store未接続時はpostback_resultsが空", result.postback_results == [])
    check("user_profile_store未接続時はignored_typesに記録される", result.ignored_types == ["postback"])


def test_dispatch_webhook_events_skips_postback_when_workshop_store_missing():
    profiles, _, _ = _make_stores()
    result = dispatch_webhook_events(
        [_make_postback_event(START_CHECKOUT_POSTBACK_DATA)],
        reply_client=InMemoryReplyClient(),
        user_profile_store=profiles, workshop_store=None,
        checkout_session_client=InMemoryCheckoutSessionClient(),
    )
    check("workshop_store未接続時はpostback_resultsが空", result.postback_results == [])
    check("workshop_store未接続時はignored_typesに記録される", result.ignored_types == ["postback"])


def test_dispatch_webhook_events_skips_postback_when_reply_client_missing():
    profiles, workshops, _ = _make_stores()
    result = dispatch_webhook_events(
        [_make_postback_event(START_CHECKOUT_POSTBACK_DATA)],
        reply_client=None,
        user_profile_store=profiles, workshop_store=workshops,
        checkout_session_client=InMemoryCheckoutSessionClient(),
    )
    check("reply_client未接続時はpostback_resultsが空", result.postback_results == [])
    check("reply_client未接続時はignored_typesに記録される", result.ignored_types == ["postback"])


_TEST_CHANNEL_SECRET = "test-channel-secret"


def _webhook_body(events: list) -> bytes:
    import json

    return json.dumps({"events": events}).encode("utf-8")


def test_receive_webhook_rejects_invalid_signature():
    body = _webhook_body([_make_event("新規、ブリティッシュ、牛革")])
    result = receive_webhook(body, "invalid-signature", _TEST_CHANNEL_SECRET)
    check("署名不正時は401", result.status_code == 401)
    check("errorはinvalid_signature", result.error == "invalid_signature")
    check("dispatch_resultはNoneのまま", result.dispatch_result is None)


def test_receive_webhook_rejects_missing_signature_header():
    body = _webhook_body([_make_event("新規、ブリティッシュ、牛革")])
    result = receive_webhook(body, None, _TEST_CHANNEL_SECRET)
    check("署名ヘッダ欠落時も401", result.status_code == 401)


def test_receive_webhook_rejects_invalid_json():
    body = b"not-a-json-body"
    signature = _sign(body, _TEST_CHANNEL_SECRET)
    result = receive_webhook(body, signature, _TEST_CHANNEL_SECRET)
    check("不正JSON時は400", result.status_code == 400)
    check("errorはinvalid_json", result.error == "invalid_json")


def test_receive_webhook_rejects_missing_events_key():
    import json

    body = json.dumps({"not_events": []}).encode("utf-8")
    signature = _sign(body, _TEST_CHANNEL_SECRET)
    result = receive_webhook(body, signature, _TEST_CHANNEL_SECRET)
    check("eventsキー欠落時は400", result.status_code == 400)
    check("errorはmissing_events", result.error == "missing_events")


def test_receive_webhook_dispatches_message_event_on_success():
    body = _webhook_body([_make_event("新規、ブリティッシュ、牛革")])
    signature = _sign(body, _TEST_CHANNEL_SECRET)
    reply_client = InMemoryReplyClient()
    result = receive_webhook(
        body, signature, _TEST_CHANNEL_SECRET,
        llm_call=_StubLlmCall([TEST_CASES["G1_new_basic"]]),
        reply_client=reply_client,
    )
    check("署名・JSON・events全て正常時は200", result.status_code == 200)
    check("dispatch_resultにmessage_resultsが1件ある", len(result.dispatch_result.message_results) == 1)
    check("実際に返信が送られている", len(reply_client.sent) == 1)


def test_receive_webhook_dispatches_postback_event_on_success():
    profiles, workshops, _ = _make_stores()
    _link_contractor_workshop(profiles, workshops, "U_CONTRACTOR", "W_RECEIVE_CHECKOUT")
    body = _webhook_body([_make_postback_event(START_CHECKOUT_POSTBACK_DATA, user_id="U_CONTRACTOR")])
    signature = _sign(body, _TEST_CHANNEL_SECRET)
    reply_client = InMemoryReplyClient()
    result = receive_webhook(
        body, signature, _TEST_CHANNEL_SECRET,
        reply_client=reply_client,
        user_profile_store=profiles, workshop_store=workshops,
        checkout_session_client=InMemoryCheckoutSessionClient(),
    )
    check("postbackイベントも200で処理される", result.status_code == 200)
    check("dispatch_resultにpostback_resultsが1件ある", len(result.dispatch_result.postback_results) == 1)
    check("実際に返信が送られている", len(reply_client.sent) == 1)


def test_receive_webhook_with_all_dependencies_none_does_not_raise():
    body = _webhook_body([_make_event("新規、ブリティッシュ、牛革")])
    signature = _sign(body, _TEST_CHANNEL_SECRET)
    result = receive_webhook(body, signature, _TEST_CHANNEL_SECRET)
    check("依存関係が全て未接続でも200かつignored扱いにならず例外なし", result.status_code == 200)
    check("llm_call未接続のためmessage_resultsは空", result.dispatch_result.message_results == [])


if __name__ == "__main__":
    test_verify_line_signature_accepts_correct_signature()
    test_verify_line_signature_rejects_wrong_signature()
    test_verify_line_signature_rejects_tampered_body()
    test_verify_line_signature_rejects_missing_header()
    test_in_memory_reply_client_records_sent_message_without_quick_reply()
    test_in_memory_reply_client_records_quick_reply()
    test_trial_end_quick_reply_matches_default_checkout_postback_data()
    test_format_trial_end_notification_message_includes_time_estimate_when_generation_count_positive()
    test_format_trial_end_notification_message_scales_minutes_with_count()
    test_format_trial_end_notification_message_omits_time_estimate_when_generation_count_zero()
    test_format_trial_end_notification_message_does_not_embed_postback_data_or_url()
    test_format_trial_end_notification_message_rejects_negative_count()
    test_format_follow_welcome_message_embeds_linking_code()
    test_process_follow_event_ignores_non_follow_event()
    test_process_follow_event_issues_code_and_sends_welcome_message()
    test_process_follow_event_without_user_id_does_not_reply()
    test_process_unfollow_event_ignores_non_unfollow_event()
    test_process_unfollow_event_returns_handled_without_user_id()
    test_process_unfollow_event_returns_handled_for_known_user()
    test_process_memo_event_ignores_non_text_message()
    test_process_memo_event_generated_includes_three_outputs()
    test_process_memo_event_out_of_scope_returns_message_as_is()
    test_process_memo_event_insufficient_input_returns_missing_fields_request()
    test_process_memo_event_cancellation_intent_replaces_portal_placeholder()
    test_process_memo_event_cancellation_intent_falls_back_when_provider_missing()
    test_process_memo_event_cancellation_unclear_does_not_need_provider()
    test_process_memo_event_checkout_intent_returns_notice_body()
    test_process_memo_event_contractor_transfer_expired_notice_returns_body()
    test_process_memo_event_retries_once_on_validation_error_then_succeeds()
    test_process_memo_event_falls_back_after_second_validation_error()
    test_process_memo_event_falls_back_after_llm_api_error_retried_once()
    test_process_memo_event_blocks_with_trial_period_over_notice()
    test_process_memo_event_allows_generation_when_subscription_active_despite_trial_over()
    test_process_memo_event_blocks_with_payment_suspended_notice_after_grace_period()
    test_process_memo_event_allows_generation_within_payment_failure_grace_period()
    test_process_memo_event_appends_trial_end_notification_on_first_success()
    test_process_memo_event_does_not_append_trial_end_notification_on_second_success()
    test_process_memo_event_skips_store_integration_when_stores_not_provided()
    test_process_message_event_delegates_when_stores_not_provided()
    test_process_message_event_delegates_when_user_already_linked()
    test_process_message_event_creates_workshop_on_valid_linking_code()
    test_process_message_event_replies_linking_required_on_invalid_text()
    test_process_message_event_replies_linking_required_when_user_id_missing()
    test_process_postback_event_ignores_unknown_postback_data()
    test_process_postback_event_creates_checkout_session_for_linked_contractor()
    test_process_postback_event_uses_plan_id_from_postback_data()
    test_process_postback_event_reuses_existing_stripe_customer_id()
    test_process_postback_event_replies_linking_required_when_unlinked()
    test_process_postback_event_replies_linking_required_when_user_id_missing()
    test_process_postback_event_rejects_non_contractor_member()
    test_process_postback_event_rejects_when_already_subscribed()
    test_dispatch_webhook_events_routes_message_event_to_process_memo_event()
    test_dispatch_webhook_events_routes_valid_linking_code_to_workshop_creation()
    test_dispatch_webhook_events_records_ignored_types_for_non_message_events()
    test_dispatch_webhook_events_routes_unfollow_event_to_process_unfollow_event()
    test_dispatch_webhook_events_skips_message_when_llm_call_missing()
    test_dispatch_webhook_events_skips_message_when_reply_client_missing()
    test_dispatch_webhook_events_passes_store_kwargs_through_to_process_memo_event()
    test_dispatch_webhook_events_routes_follow_event_to_process_follow_event()
    test_dispatch_webhook_events_skips_follow_when_linking_store_missing()
    test_dispatch_webhook_events_skips_follow_when_reply_client_missing()
    test_dispatch_webhook_events_routes_postback_event_to_process_postback_event()
    test_dispatch_webhook_events_skips_postback_when_checkout_session_client_missing()
    test_dispatch_webhook_events_skips_postback_when_user_profile_store_missing()
    test_dispatch_webhook_events_skips_postback_when_workshop_store_missing()
    test_dispatch_webhook_events_skips_postback_when_reply_client_missing()
    test_receive_webhook_rejects_invalid_signature()
    test_receive_webhook_rejects_missing_signature_header()
    test_receive_webhook_rejects_invalid_json()
    test_receive_webhook_rejects_missing_events_key()
    test_receive_webhook_dispatches_message_event_on_success()
    test_receive_webhook_dispatches_postback_event_on_success()
    test_receive_webhook_with_all_dependencies_none_does_not_raise()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
