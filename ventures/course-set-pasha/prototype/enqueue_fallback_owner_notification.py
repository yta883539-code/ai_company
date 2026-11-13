#!/usr/bin/env python3
"""
enqueue-fallback-owner-notification-design.md(フェーズ374)で設計した、
`dispatch_webhook_events()`の`result.enqueue_fallback_webhook_event_ids`
(フェーズ373、Cloud Tasksへの`create_task()`が`TaskAlreadyExistsError`以外の例外で失敗し、
同期処理へフォールバックした`webhookEventId`の一覧)が非空だった場合に、オーナーへLINE Push
でdigest通知を送るモジュール。

位置づけ:
- blocked_but_billing_owner_notification.py・payment_suspension_owner_notification.pyとは
  異なり、通知対象は顧客のuser_idではなくwebhookEventId(運用上のインシデント信号)であり、
  各webhookEventIdは既存の重複排除(line-webhook-event-id-idempotency-design.md)により
  再出現しない前提のため、永続的な「通知済みフラグ」のストアは持たない(design 2節)。
- 実際のオーナーLINEユーザーIDの取得・設定、実LINE Push Message APIでの送信はオーナー承認待ち
  (README.md「実LLM呼び出し・実LINE API接続」の記載範囲に含まれる、新規の承認待ち事項では
  ない)。本モジュールはそれとは別に、文言整形・送信の配線を実クラウド接続なしで検証可能に
  したもの。
- LinePushClient・LinePushDeliveryErrorはtrial_end_scheduler.pyで既に定義済みのものを
  そのまま再利用する(本モジュールで重複定義しない)。

設計の参照元: enqueue-fallback-owner-notification-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# design 1節: 既存2設計と同じ考え方のプレースホルダ。実値は実LINE API接続後に設定値として
# 差し込む。
OWNER_LINE_USER_ID_PLACEHOLDER = "{オーナーLINEユーザーID}"

# design 4節: 列挙する先頭件数。これを超える分は「...他N件」と要約する。
_LISTED_WEBHOOK_EVENT_ID_LIMIT = 5

ENQUEUE_FALLBACK_OWNER_NOTIFICATION_TEMPLATE = (
    "[コースセットパシャッと運営] Cloud Tasksへのenqueue失敗のお知らせ\n"
    "\n"
    "以下のWebhookイベントで、Cloud Tasksへのenqueueに失敗したため同期処理へ\n"
    "自動フォールバックしました(顧客への応答自体は正常に行われています)。\n"
    "\n"
    "件数: {count}件\n"
    "webhookEventId: {webhook_event_id_list}\n"
    "\n"
    "Cloud Tasksのクォータ超過や一時的なネットワーク障害が疑われます。頻発する場合は\n"
    "Cloud Tasksの設定(クォータ・リトライポリシー)をご確認ください。"
)


def _format_webhook_event_id_list(webhook_event_ids: Sequence[str]) -> str:
    """design 4節「先頭5件までを列挙し、残りは要約する」をそのままコード化したもの。"""
    listed = list(webhook_event_ids[:_LISTED_WEBHOOK_EVENT_ID_LIMIT])
    remaining = len(webhook_event_ids) - len(listed)
    text = ", ".join(listed)
    if remaining > 0:
        text += f", ...他{remaining}件"
    return text


def format_enqueue_fallback_owner_notification_message(
    webhook_event_ids: Sequence[str],
) -> str:
    """design 4節の文言を、件数・webhookEventId一覧を埋め込んで組み立てる。"""
    return ENQUEUE_FALLBACK_OWNER_NOTIFICATION_TEMPLATE.format(
        count=len(webhook_event_ids),
        webhook_event_id_list=_format_webhook_event_id_list(webhook_event_ids),
    )


@dataclass
class SendEnqueueFallbackOwnerNotificationResult:
    """1回の送信試行の結果(design 3節、永続フラグを持たないため呼び出し元のログ用途のみ)。"""

    sent: bool


def send_enqueue_fallback_owner_notification(
    webhook_event_ids: Sequence[str],
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> SendEnqueueFallbackOwnerNotificationResult:
    """enqueue-fallback-owner-notification-design.md 2〜3節の本体。

    webhook_event_idsが空の場合は何も送信しない(呼び出し側で非空チェックを重複させなくて
    良いよう、本関数側でも安全側のガードを持つ)。送信失敗(LinePushDeliveryError)は
    design 3節の方針通り握りつぶし、再送・リトライは行わない。
    """
    if not webhook_event_ids:
        return SendEnqueueFallbackOwnerNotificationResult(sent=False)

    text = format_enqueue_fallback_owner_notification_message(webhook_event_ids)
    try:
        push_client.send_message(owner_line_user_id, text)
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
