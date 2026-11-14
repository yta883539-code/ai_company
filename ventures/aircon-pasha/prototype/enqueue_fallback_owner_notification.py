#!/usr/bin/env python3
"""
enqueue-fallback-owner-notification-design.md(aircon-pasha版)で設計した、
`dispatch_webhook_events()`の`result.enqueue_fallback_webhook_event_ids`
(Cloud Tasksへの`create_task()`が`TaskAlreadyExistsError`以外の例外で失敗し、同期処理へ
フォールバックした`webhookEventId`の一覧)が非空だった場合に、オーナーへLINE Pushで
digest通知を送るモジュール。course-set-pasha/prototype/enqueue_fallback_owner_
notification.pyの横展開版。

位置づけ:
- blocked_but_billing_owner_notification.py・payment_suspension_owner_notification.pyとは
  異なり、通知対象は顧客のuser_idではなくwebhookEventId(運用上のインシデント信号)であり、
  各webhookEventIdは既存の重複排除(line-webhook-event-id-idempotency-design.md)により
  再出現しない前提のため、永続的な「通知済みフラグ」のストアは持たない(design 2節)。
- course-set-pasha版はプレーンテキストの`send_message()`を使うが、本venture一貫の
  `LinePushClient`(trial_end_scheduler.py)はFlex Message(`send_flex_message(user_id,
  alt_text, contents)`)のみを提供するため、payment_suspension_owner_notification.py等と
  同様にボタンを持たないbubble形式のFlex Messageを組み立てる(design 2〜3節)。
- 実際のオーナーLINEユーザーIDの取得・設定、実LINE Push Message APIでの送信はオーナー承認待ち
  (README.md「実LLM呼び出し・実LINE API接続」の記載範囲に含まれる、新規の承認待ち事項では
  ない)。本モジュールはそれとは別に、文言整形・送信の配線を実クラウド接続なしで検証可能に
  したもの。
- LinePushClient・LinePushDeliveryErrorはtrial_end_scheduler.pyで既に定義済みのものを
  そのまま再利用する(本モジュールで重複定義しない)。OWNER_LINE_USER_ID_PLACEHOLDERは
  blocked_but_billing_owner_notification.pyで定義済みのものを再利用する。

設計の参照元: enqueue-fallback-owner-notification-design.md(aircon-pasha版)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from blocked_but_billing_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

ENQUEUE_FALLBACK_OWNER_NOTIFICATION_ALT_TEXT = (
    "[エアコンパシャッと運営] Cloud Tasksへのenqueue失敗のお知らせ"
)

# design 3節: 列挙する先頭件数。これを超える分は「...他N件」と要約する。
_LISTED_WEBHOOK_EVENT_ID_LIMIT = 5


def _format_webhook_event_id_list(webhook_event_ids: Sequence[str]) -> str:
    """design 3節「先頭5件までを列挙し、残りは要約する」をそのままコード化したもの。"""
    listed = list(webhook_event_ids[:_LISTED_WEBHOOK_EVENT_ID_LIMIT])
    remaining = len(webhook_event_ids) - len(listed)
    text = ", ".join(listed)
    if remaining > 0:
        text += f", ...他{remaining}件"
    return text


def build_enqueue_fallback_owner_notification_flex_message(
    webhook_event_ids: Sequence[str],
) -> dict:
    """design 3節: ボタンを持たない、テキストのみのbubble形式のFlex Messageを組み立てる
    (payment_suspension_owner_notification.build_payment_suspension_owner_notification_
    flex_message()と同じ構成)。"""
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": ENQUEUE_FALLBACK_OWNER_NOTIFICATION_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": (
                        "以下のWebhookイベントで、Cloud Tasksへのenqueueに失敗したため\n"
                        "同期処理へ自動フォールバックしました(顧客への応答自体は正常に\n"
                        "行われています)。\n"
                        f"件数: {len(webhook_event_ids)}件\n"
                        f"webhookEventId: {_format_webhook_event_id_list(webhook_event_ids)}"
                    ),
                    "wrap": True,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": (
                        "Cloud Tasksのクォータ超過や一時的なネットワーク障害が疑われます。"
                        "頻発する場合はCloud Tasksの設定(クォータ・リトライポリシー)を"
                        "ご確認ください。"
                    ),
                    "wrap": True,
                    "margin": "md",
                },
            ],
        },
    }


@dataclass
class SendEnqueueFallbackOwnerNotificationResult:
    """1回の送信試行の結果(design 2節、永続フラグを持たないため呼び出し元のログ用途のみ)。"""

    sent: bool


def send_enqueue_fallback_owner_notification(
    webhook_event_ids: Sequence[str],
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> SendEnqueueFallbackOwnerNotificationResult:
    """enqueue-fallback-owner-notification-design.md(aircon-pasha版)2〜3節の本体。

    webhook_event_idsが空の場合は何も送信しない(呼び出し側で非空チェックを重複させなくて
    良いよう、本関数側でも安全側のガードを持つ)。送信失敗(LinePushDeliveryError)は
    design方針通り握りつぶし、再送・リトライは行わない。
    """
    if not webhook_event_ids:
        return SendEnqueueFallbackOwnerNotificationResult(sent=False)

    contents = build_enqueue_fallback_owner_notification_flex_message(webhook_event_ids)
    try:
        push_client.send_flex_message(
            owner_line_user_id,
            ENQUEUE_FALLBACK_OWNER_NOTIFICATION_ALT_TEXT,
            contents,
        )
    except LinePushDeliveryError:
        return SendEnqueueFallbackOwnerNotificationResult(sent=False)
    return SendEnqueueFallbackOwnerNotificationResult(sent=True)


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    push = InMemoryLinePushClient()
    result = send_enqueue_fallback_owner_notification(["ev1", "ev2", "ev3"], push)
    print(f"sent={result.sent}")
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
