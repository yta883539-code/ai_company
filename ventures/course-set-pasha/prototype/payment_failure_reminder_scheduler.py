#!/usr/bin/env python3
"""
payment-failure-reminder-scheduler-design.mdで設計した「Cloud Function E:
send_payment_failure_reminders」を、実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信はオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「いつ・どのユーザーに
  決済失敗リマインドを送るべきか」の判定ロジック(design 4節)と、「実際に送るメッセージの
  整形・送信・冪等性のための書き込み」の配線を実クラウド接続なしで検証可能にしたもの
  (trial_end_scheduler.pyと同じ位置づけ、aircon-pasha/prototype/
  payment_failure_reminder_scheduler.pyの本venture版)。
- LinePushClientはtrial_end_scheduler.pyで既に定義済みのProtocolをそのまま再利用する
  (本モジュールで重複定義しない)。

設計の参照元: payment-failure-reminder-scheduler-design.md, payment-failure-dunning-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol, Sequence

from trial_end_scheduler import LIFF_URL_PLACEHOLDER, LinePushClient

# payment-failure-dunning-design.md 3節と同じ暫定値(他venture共通、実測データなし)。
DEFAULT_GRACE_PERIOD_DAYS = 7
# payment-failure-dunning-design.md 4節「猶予期間終了直前(3日前リマインド)」。
DEFAULT_REMINDER_DAYS_BEFORE_END = 3


@dataclass(frozen=True)
class PaymentFailureUserState:
    """payment-failure-reminder-scheduler-design.md 4節が参照する、ユーザー1件分の
    usage_counter状態。payment_failure_detected_at・payment_failure_reminder_sent_atは
    InMemoryUsageCounter(cloud_function_webhook.py、フェーズ120)に既存のフィールドを
    そのまま反映する。"""

    user_id: str
    payment_failure_detected_at: Optional[datetime]
    payment_failure_reminder_sent_at: Optional[datetime] = None


def select_due_payment_failure_reminders(
    users: Sequence[PaymentFailureUserState],
    now: datetime,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
) -> list[PaymentFailureUserState]:
    """payment-failure-reminder-scheduler-design.md 4節の抽出条件をそのままコード化したもの。

    以下すべてを満たすユーザーのみを対象として返す(順序はusersの入力順を維持する)。
    - payment_failure_detected_atが設定済み
    - payment_failure_reminder_sent_atが未設定(1回のみ送信)
    - now - payment_failure_detected_at >= grace_period_days - reminder_days_before_end
      (デフォルトでは4日。「以上」の範囲条件とすることで日次実行の遅延・欠落に自然に耐える)
    - now - payment_failure_detected_at < grace_period_days
      (design 2節: 既に制限モードへ移行済み相当のユーザーは対象から除外する安全策。
      本ventureは`payment_suspended_at`のような別立てフラグを持たないため、この上限側の
      条件がaircon-pasha版の`payment_suspended_at is None`条件の代わりを果たす)
    """

    lower_bound = timedelta(days=grace_period_days - reminder_days_before_end)
    upper_bound = timedelta(days=grace_period_days)
    due: list[PaymentFailureUserState] = []
    for user in users:
        if user.payment_failure_detected_at is None:
            continue
        if user.payment_failure_reminder_sent_at is not None:
            continue
        elapsed = now - user.payment_failure_detected_at
        if elapsed < lower_bound:
            continue
        if elapsed >= upper_bound:
            continue
        due.append(user)
    return due


# ---------------------------------------------------------------------------
# メッセージ整形(payment-failure-dunning-design.md 4節「猶予期間終了直前」)
# ---------------------------------------------------------------------------

PAYMENT_FAILURE_REMINDER_TEMPLATE = (
    "[コースセットパシャッと] お支払い確認のお願い(再送)\n"
    "\n"
    "お支払い手続きが未完了のままです。\n"
    "このままですと3日後に投稿文の生成を一時停止いたします。\n"
    "\n"
    "▼ お支払い方法を確認する\n"
    "{liff_url}"
)


def format_payment_failure_reminder_message(liff_url: str = LIFF_URL_PLACEHOLDER) -> str:
    """payment-failure-dunning-design.md 4節の「猶予期間終了直前(3日前リマインド)」文言を
    そのまま組み立てる。全ユーザー共通の固定文言(ユーザーごとに変化する値がない)ため、
    trial_end_scheduler.pyの通知文言と異なり引数はliff_urlのみでよい。"""
    return PAYMENT_FAILURE_REMINDER_TEMPLATE.format(liff_url=liff_url)


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function E本体)
# ---------------------------------------------------------------------------


class PaymentFailureReminderSentAtWriter(Protocol):
    """cloud_function_webhook.py UsageCounterProtocolのうち、本モジュールが実際に使う
    1メソッドのみを要求する最小限のProtocol(trial_end_scheduler.pyのTrialEndNotifiedAtWriter・
    stripe_webhook.pyのUpgradedAtWriterProtocolと同じ「呼び出し側は具象クラスに直接
    依存しない」という考え方)。"""

    def set_payment_failure_reminder_sent_at(self, user_id: str, sent_at: datetime) -> None:
        ...


@dataclass
class SendPaymentFailureRemindersResult:
    """1回のCloud Function E起動での送信結果(呼び出し側のログ・監視用、
    trial_end_scheduler.py SendTrialEndNotificationsResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_payment_failure_reminders(
    users: Sequence[PaymentFailureUserState],
    now: datetime,
    usage_counter: PaymentFailureReminderSentAtWriter,
    push_client: LinePushClient,
    liff_url: str = LIFF_URL_PLACEHOLDER,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
) -> SendPaymentFailureRemindersResult:
    """payment-failure-reminder-scheduler-design.md 1節の全体構成図における「Cloud Function E:
    send_payment_failure_reminders」本体。引数のusersは呼び出し元でFirestoreから読み取った
    候補一覧を想定し(4節の抽出条件をクエリ化したものに相当)、実際の絞り込みは
    select_due_payment_failure_reminders()が行う。

    送信成功時のみusage_counter.set_payment_failure_reminder_sent_at()を書き込み、送信失敗時は
    書き込まない(6節の冪等性設計、send_trial_end_notifications()と同じ「書き込み一発+
    次回実行時に自然に再試行対象として残る」方式)。全ユーザー共通の固定文言のため、
    メッセージ整形はループの外で1回だけ行う。
    """
    from trial_end_scheduler import LinePushDeliveryError

    result = SendPaymentFailureRemindersResult()
    text = format_payment_failure_reminder_message(liff_url)

    for user in select_due_payment_failure_reminders(
        users, now, grace_period_days, reminder_days_before_end
    ):
        try:
            push_client.send_message(user.user_id, text)
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        usage_counter.set_payment_failure_reminder_sent_at(user.user_id, now)
        result.sent.append(user.user_id)

    return result


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    now = datetime(2026, 8, 28, 4, 0, 0)
    users = [
        # 検知から5日経過(4日以上7日未満): 対象
        PaymentFailureUserState(
            user_id="u1", payment_failure_detected_at=now - timedelta(days=5)
        ),
        # 検知から2日しか経過していない: 対象外
        PaymentFailureUserState(
            user_id="u2", payment_failure_detected_at=now - timedelta(days=2)
        ),
        # 既にリマインド送信済み: 対象外
        PaymentFailureUserState(
            user_id="u3",
            payment_failure_detected_at=now - timedelta(days=6),
            payment_failure_reminder_sent_at=now - timedelta(days=1),
        ),
        # 検知から8日経過(既に猶予期間超過、制限モード相当): 対象外
        PaymentFailureUserState(
            user_id="u4", payment_failure_detected_at=now - timedelta(days=8)
        ),
        # 決済失敗未検知: 対象外
        PaymentFailureUserState(user_id="u5", payment_failure_detected_at=None),
    ]
    due = select_due_payment_failure_reminders(users, now)
    print([u.user_id for u in due])

    class _InMemoryUsageCounterStub:
        def __init__(self) -> None:
            self.reminder_sent_at: dict[str, datetime] = {}

        def set_payment_failure_reminder_sent_at(self, user_id: str, sent_at: datetime) -> None:
            self.reminder_sent_at[user_id] = sent_at

    usage_counter = _InMemoryUsageCounterStub()
    push = InMemoryLinePushClient()
    result = send_payment_failure_reminders(users, now, usage_counter, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
