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
"""

from __future__ import annotations

from dataclasses import dataclass

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
