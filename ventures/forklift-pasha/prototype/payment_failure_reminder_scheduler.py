#!/usr/bin/env python3
"""payment-failure-reminder-scheduler-design.md(フェーズ169)で設計した、決済失敗検知後の
顧客向けリマインドメール・運営者向け通知の抽出ロジック・メール整形・送信配線を実行可能な
コードに落とし込んだもの。

実際のCloud Scheduler設定・実メール送信接続はオーナー承認待ち(pending-approval.md
2026-10-10 18:00 UTC記載の範囲)。送信クライアントはtrial_end_email_scheduler.pyの
EmailSenderClient/InMemoryEmailSenderClient/EmailDeliveryErrorをそのまま再利用する
(design前文の方針どおり、送信手段がメール1つのみの本ventureでは新規定義しない)。

設計の参照元: payment-failure-reminder-scheduler-design.md, payment-failure-dunning-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from payment_failure import PAYMENT_FAILURE_GRACE_PERIOD_DAYS, is_payment_suspended
from trial_end_email_scheduler import (
    EmailDeliveryError,
    EmailSenderClient,
    InMemoryEmailSenderClient,
)
from trial_management import FleetOperatorStoreProtocol

# design 1節: 猶予期間7日のうち3日前(=検知から4日後)にリマインドを1回だけ送る。
DEFAULT_REMINDER_DAYS_BEFORE_END = 3


# ---------------------------------------------------------------------------
# 1. 顧客向けリマインド (design 1節)
# ---------------------------------------------------------------------------


def is_payment_failure_reminder_due(
    internal_id: str,
    now: datetime,
    store: FleetOperatorStoreProtocol,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
) -> bool:
    """design 1節の抽出条件をそのままコード化したもの。"""
    if store.get_upgraded_at(internal_id) is None:
        return False
    if store.get_canceled_at(internal_id) is not None:
        return False
    if is_payment_suspended(internal_id, now, store):
        return False
    if store.get_payment_failure_reminder_sent_at(internal_id) is not None:
        return False
    detected_at = store.get_payment_failure_detected_at(internal_id)
    if detected_at is None:
        return False
    threshold = timedelta(days=grace_period_days - reminder_days_before_end)
    return now - detected_at >= threshold


def select_due_payment_failure_reminders(
    internal_ids: Sequence[str],
    now: datetime,
    store: FleetOperatorStoreProtocol,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
) -> list[str]:
    return [
        internal_id
        for internal_id in internal_ids
        if is_payment_failure_reminder_due(
            internal_id, now, store, grace_period_days, reminder_days_before_end
        )
    ]


PAYMENT_FAILURE_REMINDER_EMAIL_SUBJECT = "【フォークリフトパシャっと】お支払い確認のお願い(再送)"

PAYMENT_FAILURE_REMINDER_EMAIL_BODY = (
    "いつもフォークリフトパシャっとをご利用いただきありがとうございます。\n"
    "お支払い手続きが未完了のままです。このままですと3日後に点検記録簿の整形・期限"
    "リマインドの生成を一時停止いたします。\n"
    "\n"
    "お手数ですが、ご登録のアクセスURLからお支払い方法をご確認・更新ください。"
)


@dataclass
class SendPaymentFailureRemindersResult:
    sent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # 次回起動時に再試行
    skipped_no_email: list[str] = field(default_factory=list)


def send_payment_failure_reminders(
    internal_ids: Sequence[str],
    now: datetime,
    store: FleetOperatorStoreProtocol,
    email_client: EmailSenderClient,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
) -> SendPaymentFailureRemindersResult:
    """design 1節本体。送信成功時のみ`payment_failure_reminder_sent_at`を書き込む
    (失敗時は書き込まず次回実行時に自然に再試行対象として残る)。"""
    result = SendPaymentFailureRemindersResult()
    for internal_id in select_due_payment_failure_reminders(
        internal_ids, now, store, grace_period_days, reminder_days_before_end
    ):
        to_email = store.get_email(internal_id)
        if not to_email:
            result.skipped_no_email.append(internal_id)
            continue
        try:
            email_client.send_email(
                to_email,
                PAYMENT_FAILURE_REMINDER_EMAIL_SUBJECT,
                PAYMENT_FAILURE_REMINDER_EMAIL_BODY,
            )
        except EmailDeliveryError:
            result.failed.append(internal_id)
            continue
        store.set_payment_failure_reminder_sent_at(internal_id, now)
        result.sent.append(internal_id)
    return result


# ---------------------------------------------------------------------------
# 2. 運営者向け通知 (design 2節)
# ---------------------------------------------------------------------------

# 実際の宛先は実メール送信接続時のオーナー承認待ちの範囲(design 2節)。
OWNER_NOTIFICATION_EMAIL_PLACEHOLDER = "owner-notification-placeholder@example.com"

OWNER_NOTIFICATION_EMAIL_SUBJECT_TEMPLATE = (
    "【フォークリフトパシャっと運営者通知】決済失敗により制限モードへ移行: {internal_id}"
)

OWNER_NOTIFICATION_EMAIL_BODY_TEMPLATE = (
    "事業者({internal_id})が決済失敗の猶予期間(7日)を超えたため、点検記録簿の整形・"
    "期限リマインドの生成を一時停止しました。"
)


def select_due_payment_suspension_owner_notifications(
    internal_ids: Sequence[str],
    now: datetime,
    store: FleetOperatorStoreProtocol,
) -> list[str]:
    """design 2節の抽出条件(制限モード移行済み・未通知)をそのままコード化したもの。"""
    due: list[str] = []
    for internal_id in internal_ids:
        if not is_payment_suspended(internal_id, now, store):
            continue
        if store.get_payment_suspension_owner_notified_at(internal_id) is not None:
            continue
        due.append(internal_id)
    return due


@dataclass
class SendPaymentSuspensionOwnerNotificationsResult:
    sent: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # 次回起動時に再試行


def send_payment_suspension_owner_notifications(
    internal_ids: Sequence[str],
    now: datetime,
    store: FleetOperatorStoreProtocol,
    email_client: EmailSenderClient,
    owner_email: str = OWNER_NOTIFICATION_EMAIL_PLACEHOLDER,
) -> SendPaymentSuspensionOwnerNotificationsResult:
    """design 2節本体。送信成功時のみ`payment_suspension_owner_notified_at`を書き込む
    (失敗時は書き込まず次回実行時に自然に再試行対象として残る)。"""
    result = SendPaymentSuspensionOwnerNotificationsResult()
    for internal_id in select_due_payment_suspension_owner_notifications(
        internal_ids, now, store
    ):
        try:
            email_client.send_email(
                owner_email,
                OWNER_NOTIFICATION_EMAIL_SUBJECT_TEMPLATE.format(internal_id=internal_id),
                OWNER_NOTIFICATION_EMAIL_BODY_TEMPLATE.format(internal_id=internal_id),
            )
        except EmailDeliveryError:
            result.failed.append(internal_id)
            continue
        store.set_payment_suspension_owner_notified_at(internal_id, now)
        result.sent.append(internal_id)
    return result


def _demo() -> None:
    from trial_management import InMemoryFleetOperatorStore

    store = InMemoryFleetOperatorStore()
    now = datetime(2026, 10, 18, 4, 0, 0)

    store.set_email("fo_1", "owner1@example.com")
    store.set_upgraded_at("fo_1", now - timedelta(days=60))
    store.set_payment_failure_detected_at("fo_1", now - timedelta(days=4))  # リマインド対象

    store.set_email("fo_2", "owner2@example.com")
    store.set_upgraded_at("fo_2", now - timedelta(days=60))
    store.set_payment_failure_detected_at("fo_2", now - timedelta(days=9))  # 制限モード移行済み

    client = InMemoryEmailSenderClient()
    reminder_result = send_payment_failure_reminders(["fo_1", "fo_2"], now, store, client)
    owner_result = send_payment_suspension_owner_notifications(
        ["fo_1", "fo_2"], now, store, client
    )
    print(f"reminder sent={reminder_result.sent}")
    print(f"owner notified={owner_result.sent}")


if __name__ == "__main__":
    _demo()
