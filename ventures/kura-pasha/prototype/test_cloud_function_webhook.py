#!/usr/bin/env python3
"""cloud_function_webhook.pyの検証用テスト。`python3 test_cloud_function_webhook.py`で実行する。"""

import base64
import hashlib
import hmac

from cloud_function_webhook import (
    TRIAL_END_BUTTON_LABEL,
    TRIAL_END_QUICK_REPLY,
    InMemoryReplyClient,
    QuickReplyButton,
    format_trial_end_notification_message,
    verify_line_signature,
)
from checkout_session import START_CHECKOUT_POSTBACK_DATA

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
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
