#!/usr/bin/env python3
"""cloud_function_webhook.pyの検証用テスト。`python3 test_cloud_function_webhook.py`で実行する。"""

import base64
import hashlib
import hmac

from cloud_function_webhook import (
    API_FAILURE_FALLBACK_MESSAGE,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    TRIAL_END_BUTTON_LABEL,
    TRIAL_END_QUICK_REPLY,
    VALIDATION_FAILURE_FALLBACK_MESSAGE,
    InMemoryPortalLinkProvider,
    InMemoryReplyClient,
    LlmApiError,
    QuickReplyButton,
    format_trial_end_notification_message,
    process_memo_event,
    verify_line_signature,
)
from checkout_session import START_CHECKOUT_POSTBACK_DATA
from validate_test_cases import TEST_CASES

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
        "message": {"type": "text", "text": text},
        "replyToken": reply_token,
        "source": {"userId": user_id},
    }


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
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
