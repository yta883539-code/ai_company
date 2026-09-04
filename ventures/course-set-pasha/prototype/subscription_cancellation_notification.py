#!/usr/bin/env python3
"""
subscription-cancelled-notification-design.md(フェーズ155)の実送信配線。

subscription-cancellation-flow-design.md(フェーズ55)2節で草案のみ存在し、
`stripe_webhook.dispatch_stripe_event()`の`customer.subscription.deleted`分岐に
一切配線されていなかった「解約確定時の顧客向けLINE通知」を実装する。

line-reservation-aiフェーズ続き177(`prototype/cloud_function_subscription_cancelled_
webhook.py` `render_cancellation_completed_message()`)と同じ位置づけの、契約終了
イベント(`customer.subscription.deleted`)受信時に送る単発の完了案内。design 1節の
とおり「解約予約受理時点(cancel_at_period_end)」の案内は本モジュールの対象外で、
次回以降の課題として残る。

`payment_recovery_notification.py`と同じ「文言定数+`render_*()`+`handle_*()`実送信
配線」の3点セット構成を踏襲する。本ventureの決済・契約系システム通知は一貫して
トーン分岐(formal/standard/casual)を行わないプレーンテキストであり(design 2節)、
本モジュールもそれに倣う。

subscription-cancellation-scheduled-notification-design.md(フェーズ156)追加分:
`customer.subscription.updated`受信時の「解約予約受理時点(`cancel_at_period_end`の
`false→true`変化)」「解約取り消し時点(`true→false`変化)」の2つの案内を、
`classify_cancel_at_period_end_change()`・`render_subscription_cancellation_scheduled_
message()`・`render_subscription_cancellation_rescheduled_message()`・
`handle_subscription_cancellation_update()`として同モジュールに追加する
(フェーズ155で草案のみ残っていた「次回以降の課題」対応)。line-reservation-aiフェーズ
続き185(`cloud_function_subscription_cancelled_webhook.py`
`classify_subscription_update()`・`handle_subscription_updated()`)を翻案したもの。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from cloud_function_webhook import (
    PORTAL_LINK_PLACEHOLDER,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    PortalLinkProvider,
)
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# design 2節: 「契約終了」「本日以降、投稿文の生成は利用不可」「再開時は新規契約と
# 同じ手続き」の3点を含む。line-reservation-ai版の「新規予約受付を停止」を、本venture
# 固有の「投稿文の生成が利用不可になる」に翻案した(日付プレースホルダは含めない、
# design 1節の理由により`customer.subscription.deleted`受信時点では既に契約終了後の
# ため)。
SUBSCRIPTION_CANCELLED_MESSAGE = (
    "【コースセットパシャッと】ご契約が終了しました\n"
    "\n"
    "ご契約が終了しました。ご利用ありがとうございました。\n"
    "本日以降、投稿文の生成はご利用いただけません。\n"
    "\n"
    "またのご利用をお待ちしております。再開をご希望の際は、いつでも新規契約と\n"
    "同じお手続きでお申し込みいただけます。"
)


def render_subscription_cancelled_message() -> str:
    """design 2節の文言をそのまま返す(日付・URL等の差し込みが無いため引数なし)。
    将来トーン分岐や終了日差し込みが必要になった場合に備え、文言組み立てを
    `dispatch_stripe_event()`側から独立させておく(他の`render_*()`関数と同じ理由)。"""
    return SUBSCRIPTION_CANCELLED_MESSAGE


@dataclass
class SubscriptionCancelledNotificationResult:
    """1回の`customer.subscription.deleted`通知送信の結果。

    design 3節のとおり、本モジュールは送信成否のみを報告する。`deletion_candidate_at`
    等の状態変更は呼び出し側(`dispatch_stripe_event()`)が送信成否と独立して行う
    (`payment_recovery_notification.py`と異なり、本モジュール自身は状態を一切
    保持・変更しない)。"""

    notified: bool


def handle_subscription_cancelled(
    user_id: str,
    push_client: LinePushClient,
) -> SubscriptionCancelledNotificationResult:
    """`customer.subscription.deleted`受信時(`stripe_customer_id → user_id`逆引き後)に
    呼ぶ処理本体。design 3節のとおり、送信失敗時も呼び出し側での状態変更(削除候補化等)を
    ブロックしない設計のため、本関数自体は例外を外へ漏らさず`notified=False`を返すのみで
    完結する(呼び出し側はWebhookリトライに委ねる必要が無い)。"""
    text = render_subscription_cancelled_message()
    try:
        push_client.send_message(user_id, text)
    except LinePushDeliveryError:
        return SubscriptionCancelledNotificationResult(notified=False)
    return SubscriptionCancelledNotificationResult(notified=True)


# ---------------------------------------------------------------------------
# subscription-cancellation-scheduled-notification-design.md(フェーズ156)追加分:
# customer.subscription.updated受信時(cancel_at_period_end変化)の案内。
# ---------------------------------------------------------------------------

# classify_cancel_at_period_end_change()が返す分類。line-reservation-aiの
# OUTCOME_CANCELLATION_SCHEDULED/OUTCOME_CANCELLATION_RESCHEDULED/OUTCOME_NO_CHANGEと
# 対称の命名(design 3節)。
OUTCOME_CANCELLATION_SCHEDULED = "cancellation_scheduled"
OUTCOME_CANCELLATION_RESCHEDULED = "cancellation_rescheduled"
OUTCOME_NO_CHANGE = "no_change"

_JST = timezone(timedelta(hours=9))

# design 4節: 「解約のお取り消しを承りました」「引き続きご利用いただけます」の2点のみを
# 含む固定文言(plan_name・period_end_dateは差し込まない、design 4節の理由)。
SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE = (
    "【コースセットパシャッと】解約のお取り消しを承りました\n"
    "\n"
    "解約のお取り消しを承りました。引き続きご利用いただけます。\n"
    "\n"
    "ご不明な点がございましたら、このトークルームへご返信ください。"
)


def classify_cancel_at_period_end_change(before: bool, after: bool) -> str:
    """design 3節。`customer.subscription.updated`受信時、`cancel_at_period_end`の
    前後比較から分類する。本ventureは`suspension_reason`相当の別立て状態を持たないため、
    line-reservation-aiの`classify_subscription_update()`と異なりガード条件を持たない
    (design 3節・7節)。"""
    if not before and after:
        return OUTCOME_CANCELLATION_SCHEDULED
    if before and not after:
        return OUTCOME_CANCELLATION_RESCHEDULED
    return OUTCOME_NO_CHANGE


def _format_period_end_date_jst(current_period_end: object) -> Optional[str]:
    """design 2節。`current_period_end`(Unixタイムスタンプ)をJSTの`YYYY-MM-DD`形式へ
    変換する。存在しない・数値でない・bool(int のサブクラスで誤って真偽値が渡された場合を
    弾く、他モジュールの`created`検証と同じ理由)の場合は`None`を返す(安全側フォールバック、
    4節参照)。"""
    if not isinstance(current_period_end, (int, float)) or isinstance(current_period_end, bool):
        return None
    return datetime.fromtimestamp(current_period_end, tz=_JST).strftime("%Y-%m-%d")


def render_subscription_cancellation_scheduled_message(
    period_end_date: Optional[str],
    portal_link_provider: Optional[PortalLinkProvider],
    user_id: Optional[str],
) -> str:
    """design 4節「解約予約受理時の案内メッセージ」を組み立てる。`period_end_date`が
    `None`の場合(2節のフォールバック)は日付なしの表現に差し替える。URL差し込みは
    `payment_recovery_notification.render_payment_failure_detected_message()`と同じ
    `PORTAL_LINK_PLACEHOLDER`+`.replace()`方式。未接続・user_id不明・URL取得失敗時は
    `PORTAL_LINK_UNAVAILABLE_FALLBACK`へ全文差し替える(壊れたURLを顧客に見せない)。"""
    until_phrase = (
        f"今回の請求期間の終了日({period_end_date})まで"
        if period_end_date is not None
        else "今回の請求期間の終了日まで"
    )
    text = (
        "【コースセットパシャッと】解約のお手続きを承りました\n"
        "\n"
        "解約のお手続きを承りました。以下の点をご確認ください。\n"
        "\n"
        f"・ご利用は{until_phrase}通常通り継続します(投稿文の生成に制限はありません)\n"
        "・終了日以降は投稿文の生成がご利用いただけなくなります\n"
        "・日割りでの返金は行っておりません\n"
        "\n"
        "解約を取り消したい場合は、終了日より前であれば下記からお手続きが可能です。\n"
        "\n"
        "▼ お手続きはこちら\n"
        f"{PORTAL_LINK_PLACEHOLDER}\n"
        "\n"
        "またのご利用をお待ちしております。"
    )

    url = None
    if portal_link_provider is not None and user_id:
        url = portal_link_provider.get_portal_url(user_id)
    if not url:
        return PORTAL_LINK_UNAVAILABLE_FALLBACK
    return text.replace(PORTAL_LINK_PLACEHOLDER, url)


def render_subscription_cancellation_rescheduled_message() -> str:
    """design 4節の文言をそのまま返す(差し込み情報なし)。"""
    return SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE


@dataclass
class SubscriptionCancellationUpdateResult:
    """1回の`customer.subscription.updated`(cancel_at_period_end変化)処理の結果。
    `outcome`が`OUTCOME_NO_CHANGE`の場合、送信は行われず`notified`は常に`False`。"""

    outcome: str
    notified: bool = False


def handle_subscription_cancellation_update(
    user_id: str,
    cancel_at_period_end_before: bool,
    cancel_at_period_end_after: bool,
    current_period_end: object,
    push_client: LinePushClient,
    portal_link_provider: Optional[PortalLinkProvider] = None,
) -> SubscriptionCancellationUpdateResult:
    """design 5節。`dispatch_stripe_event()`の`customer.subscription.updated`分岐から
    呼ばれる処理本体。design 5節のとおり本イベントは契約継続中(scheduled)または契約
    継続が確定した(rescheduled)場合のみ発火するため、`store`(削除候補管理)側の状態は
    一切変更しない(呼び出し側でも変更しない、design 5節)。"""
    outcome = classify_cancel_at_period_end_change(
        cancel_at_period_end_before, cancel_at_period_end_after
    )
    if outcome == OUTCOME_NO_CHANGE:
        return SubscriptionCancellationUpdateResult(outcome=outcome)

    if outcome == OUTCOME_CANCELLATION_SCHEDULED:
        text = render_subscription_cancellation_scheduled_message(
            _format_period_end_date_jst(current_period_end), portal_link_provider, user_id
        )
    else:
        text = render_subscription_cancellation_rescheduled_message()

    try:
        push_client.send_message(user_id, text)
    except LinePushDeliveryError:
        return SubscriptionCancellationUpdateResult(outcome=outcome, notified=False)

    return SubscriptionCancellationUpdateResult(outcome=outcome, notified=True)


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    push = InMemoryLinePushClient()
    result = handle_subscription_cancelled("u1", push)
    print("result:", result)
    print("送信済みログ件数:", len(push.sent))
    for user_id, text in push.sent:
        print("---", user_id)
        print(text)


if __name__ == "__main__":
    _demo()
