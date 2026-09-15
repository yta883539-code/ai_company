#!/usr/bin/env python3
"""
daily-scheduler-design.md(フェーズ112)で設計した「Cloud Function G:
run_daily_workshop_checks」のうち、選定ロジック(どのworkshopに何を送るべきかの判定)を
実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・実LINE公式アカウント接続はオーナー承認待ち(pending-
  approval.md参照)。本モジュールはそれとは別に、「いつ・どのworkshopに(B)トライアル
  30日到達報告・決済失敗3日前リマインドを送るべきか」の判定ロジック(design 3節)、
  および実クラウド接続なしで検証可能な送信配線(design 2節Cloud Function G本体、
  payment_suspension_owner_notification.pyと同じ位置づけ・同じ構成)を実装したもの。
- フェーズ122追記: 本ファイルはフェーズ112作成時点で「(B)トライアル30日到達報告の
  通知文言の組み立てはusage_counter_workshop.pyのformat_trial_end_notification_
  message()相当を本venture側でまだ実装していないため対象外」としていたが、実際には
  cloud_function_webhook.py(フェーズ62、2026-09-09)で既に同名の関数
  (`format_trial_end_notification_message(generation_count)`、経路(A)(B)共通の
  想定でdocstringに明記済み)が実装済みであり、この記載自体が誤りだったことが判明した。
  本フェーズで送信配線(`send_trial_end_reports()`・`send_payment_failure_reminders()`)を
  実装し、この関数を実際に呼び出す。

設計の参照元: daily-scheduler-design.md, trial-end-notification-design.md,
payment-failure-dunning-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Protocol, Sequence

from cloud_function_webhook import format_trial_end_notification_message
from payment_suspension_owner_notification import (
    OWNER_LINE_USER_ID_PLACEHOLDER,
    SendPaymentSuspensionOwnerNotificationsResult,
    send_payment_suspension_owner_notifications,
)
from subscription_cancellation_notification import LinePushClient, LinePushDeliveryError
from usage_counter_workshop import PAYMENT_FAILURE_GRACE_PERIOD_DAYS, TRIAL_PERIOD_DAYS

# payment-failure-dunning-design.md 3節: 猶予期間は7日、そのうち3日前(=検知から4日後)に
# リマインドを1回だけ送る(daily-scheduler-design.md 3.2節)。
PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END = 3

# daily-scheduler-design.md 4節: 決済失敗3日前リマインドの文言(プレーンテキスト。
# 本venture固有のPortalLinkProvider相当が未実装のため、他venture3件のようなFlex Message・
# ボタンではなく他の通知〈payment-failure-dunning-design.md 4節〉と同じ形式に揃える)。
PAYMENT_FAILURE_REMINDER_MESSAGE = (
    "【鞍パシャッと】お支払いのご確認まもなく期限です\n"
    "\n"
    "いつもご利用ありがとうございます。\n"
    "お支払い手続きが完了できないまま、まもなく一時停止の期限を迎えます。\n"
    "このままお支払い方法のご確認・更新がない場合、受注内容整理メモ・納品案内・\n"
    "お手入れ案内の生成を一時停止させていただきます。\n"
    "\n"
    "お手数ですが、ご利用中の決済手続き時にご案内した画面からお支払い方法をご確認\n"
    "いただけますようお願いします。"
)


@dataclass(frozen=True)
class WorkshopTrialEndState:
    """design 3.1節が参照する、workshop 1件分のトライアル終了関連状態。

    trial_start_at・trial_generation_used・trial_end_notified_atは
    usage_counter_workshop.pyのWorkshopStoreProtocolが持つ同名フィールドをそのまま反映する。
    """

    workshop_id: str
    trial_start_at: Optional[datetime]
    trial_generation_used: bool
    trial_end_notified_at: Optional[datetime] = None


def is_trial_end_report_due(
    state: WorkshopTrialEndState,
    now: datetime,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> bool:
    """trial-end-notification-design.md 2節(B)経路の抽出条件をそのままコード化したもの。

    以下すべてを満たす場合のみTrueを返す。
    - trial_start_atが設定済み
    - trial_generation_usedがFalse((A)経路〈生涯最初の生成完了時に便乗送信〉が既に
      発生済みならこの(B)経路の対象外)
    - trial_end_notified_atが未設定(二重送信防止。(A)(B)共通の同一フィールド)
    - now - trial_start_at >= trial_period_days日(「ちょうど」ではなく「以上」の範囲条件
      とすることで、日次実行の遅延・欠落に自然に耐える)
    """

    if state.trial_start_at is None:
        return False
    if state.trial_generation_used:
        return False
    if state.trial_end_notified_at is not None:
        return False
    return now - state.trial_start_at >= timedelta(days=trial_period_days)


def select_due_trial_end_reports(
    states: Sequence[WorkshopTrialEndState],
    now: datetime,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> list[WorkshopTrialEndState]:
    """statesのうちis_trial_end_report_due()がTrueのものだけを、入力順を維持して返す。"""

    return [s for s in states if is_trial_end_report_due(s, now, trial_period_days)]


@dataclass(frozen=True)
class WorkshopPaymentFailureState:
    """design 3.2節が参照する、workshop 1件分の決済失敗関連状態。

    payment_failure_detected_at・payment_failure_reminder_sent_atは
    usage_counter_workshop.pyのWorkshopStoreProtocolが持つ同名フィールドをそのまま反映する。
    """

    workshop_id: str
    payment_failure_detected_at: Optional[datetime]
    payment_failure_reminder_sent_at: Optional[datetime] = None


def is_payment_failure_reminder_due(
    state: WorkshopPaymentFailureState,
    now: datetime,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END,
) -> bool:
    """daily-scheduler-design.md 3.2節の抽出条件をそのままコード化したもの。

    以下すべてを満たす場合のみTrueを返す。
    - payment_failure_detected_atが設定済み
    - payment_failure_reminder_sent_atが未設定(1回のみ送信)
    - now - payment_failure_detected_at >= (grace_period_days - reminder_days_before_end)日
    - now - payment_failure_detected_at < grace_period_days日(既に制限モードに達している
      workshopには今更「まもなく期限」のリマインドを送らない。本ventureは
      payment_suspended_atのような別立てフラグを持たず経過日数の都度算出方式のため、
      aircon-pasha版の`payment_suspended_at is None`条件の代わりにこの上限で表現する)
    """

    if state.payment_failure_detected_at is None:
        return False
    if state.payment_failure_reminder_sent_at is not None:
        return False
    elapsed = now - state.payment_failure_detected_at
    if elapsed < timedelta(days=grace_period_days - reminder_days_before_end):
        return False
    return elapsed < timedelta(days=grace_period_days)


def select_due_payment_failure_reminders(
    states: Sequence[WorkshopPaymentFailureState],
    now: datetime,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END,
) -> list[WorkshopPaymentFailureState]:
    """statesのうちis_payment_failure_reminder_due()がTrueのものだけを、入力順を維持して
    返す。"""

    return [
        s
        for s in states
        if is_payment_failure_reminder_due(s, now, grace_period_days, reminder_days_before_end)
    ]


class DailySchedulerWorkshopStoreProtocol(Protocol):
    """design 2〜3節が参照するメソッドのみを要求する最小限のProtocol。
    `usage_counter_workshop.WorkshopStoreProtocol`(ひいては`InMemoryWorkshopStore`)は
    これらを既に持つため、構造的に(duck typing)本Protocolを満たす
    (payment_suspension_owner_notification.pyと同じ方針)。
    """

    def all_workshop_ids(self):
        ...

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...

    def get_trial_start_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def get_trial_generation_used(self, workshop_id: str) -> bool:
        ...

    def get_trial_end_notified_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def set_trial_end_notified_at(self, workshop_id: str, notified_at: datetime) -> None:
        ...

    def get_payment_failure_detected_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def get_payment_failure_reminder_sent_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def set_payment_failure_reminder_sent_at(self, workshop_id: str, sent_at: datetime) -> None:
        ...


def build_trial_end_states(
    workshop_store: DailySchedulerWorkshopStoreProtocol,
) -> List[WorkshopTrialEndState]:
    """design 2節1): 全workshopから3.1節が参照するフィールドを組み立てる
    (workshop_id昇順、list_blocked_but_billing_candidates()等と同じ方針で呼び出し順の
    非決定性を避ける)。"""

    return [
        WorkshopTrialEndState(
            workshop_id=workshop_id,
            trial_start_at=workshop_store.get_trial_start_at(workshop_id),
            trial_generation_used=workshop_store.get_trial_generation_used(workshop_id),
            trial_end_notified_at=workshop_store.get_trial_end_notified_at(workshop_id),
        )
        for workshop_id in sorted(workshop_store.all_workshop_ids())
    ]


def build_payment_failure_states(
    workshop_store: DailySchedulerWorkshopStoreProtocol,
) -> List[WorkshopPaymentFailureState]:
    """design 2節1): 全workshopから3.2節が参照するフィールドを組み立てる(workshop_id昇順)。"""

    return [
        WorkshopPaymentFailureState(
            workshop_id=workshop_id,
            payment_failure_detected_at=workshop_store.get_payment_failure_detected_at(
                workshop_id
            ),
            payment_failure_reminder_sent_at=(
                workshop_store.get_payment_failure_reminder_sent_at(workshop_id)
            ),
        )
        for workshop_id in sorted(workshop_store.all_workshop_ids())
    ]


@dataclass
class SendResult:
    """1回の抽出・送信での結果(呼び出し側のログ・監視用、
    payment_suspension_owner_notification.SendPaymentSuspensionOwnerNotificationsResultと
    対称)。"""

    sent: list[str] = field(default_factory=list)  # workshop_id
    failed: list[str] = field(default_factory=list)  # workshop_id(送信失敗、次回起動時に再試行)


def send_trial_end_reports(
    now: datetime,
    workshop_store: DailySchedulerWorkshopStoreProtocol,
    push_client: LinePushClient,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> SendResult:
    """design 2節2): (B)トライアル30日到達報告の送信配線(Cloud Function G本体の一部)。

    format_trial_end_notification_message(0)を使う(design 4節: (B)経路は
    trial_generation_used=Falseのworkshopのみが対象のため、生成実績は常に0回)。送信成功時
    のみtrial_end_notified_atを書き込み、送信失敗時は書き込まない(次回起動時に自然に
    再試行対象として残る、payment_suspension_owner_notification.pyと同じ方式)。
    """

    result = SendResult()
    states = build_trial_end_states(workshop_store)
    for state in select_due_trial_end_reports(states, now, trial_period_days):
        text = format_trial_end_notification_message(0)
        recipient = workshop_store.get_contractor_user_id(state.workshop_id)
        try:
            push_client.send_message(recipient, text)
        except LinePushDeliveryError:
            result.failed.append(state.workshop_id)
            continue
        workshop_store.set_trial_end_notified_at(state.workshop_id, now)
        result.sent.append(state.workshop_id)
    return result


def send_payment_failure_reminders(
    now: datetime,
    workshop_store: DailySchedulerWorkshopStoreProtocol,
    push_client: LinePushClient,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = PAYMENT_FAILURE_REMINDER_DAYS_BEFORE_END,
) -> SendResult:
    """design 2節3): 決済失敗3日前リマインドの送信配線(Cloud Function G本体の一部)。
    送信成功時のみpayment_failure_reminder_sent_atを書き込む(上記と同じ方式)。
    """

    result = SendResult()
    states = build_payment_failure_states(workshop_store)
    for state in select_due_payment_failure_reminders(
        states, now, grace_period_days, reminder_days_before_end
    ):
        recipient = workshop_store.get_contractor_user_id(state.workshop_id)
        try:
            push_client.send_message(recipient, PAYMENT_FAILURE_REMINDER_MESSAGE)
        except LinePushDeliveryError:
            result.failed.append(state.workshop_id)
            continue
        workshop_store.set_payment_failure_reminder_sent_at(state.workshop_id, now)
        result.sent.append(state.workshop_id)
    return result


@dataclass
class RunDailyWorkshopChecksResult:
    """design 2節のCloud Function G 1回の起動での結果一式(3系統それぞれのSendResult相当)。"""

    trial_end_reports: SendResult
    payment_failure_reminders: SendResult
    payment_suspension_owner_notifications: SendPaymentSuspensionOwnerNotificationsResult


def run_daily_workshop_checks(
    now: datetime,
    workshop_store: DailySchedulerWorkshopStoreProtocol,
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> RunDailyWorkshopChecksResult:
    """design 2節「Cloud Function G: run_daily_workshop_checks」本体。

    2)(B)トライアル30日到達報告→3)決済失敗3日前リマインド→4)制限モード移行時の
    オーナー通知(payment_suspension_owner_notification.py、フェーズ116)の順に呼び出す
    (design 2節の順序どおり)。4)は選定ロジック・送信配線とも当該モジュール側で完結済み
    のため、本関数からはそのまま呼び出す1行の追加で足りる(daily-scheduler-design.md
    フェーズ117追記のとおり)。
    """

    trial_end_result = send_trial_end_reports(now, workshop_store, push_client)
    payment_failure_result = send_payment_failure_reminders(now, workshop_store, push_client)
    owner_notification_result = send_payment_suspension_owner_notifications(
        now, workshop_store, push_client, owner_line_user_id
    )
    return RunDailyWorkshopChecksResult(
        trial_end_reports=trial_end_result,
        payment_failure_reminders=payment_failure_result,
        payment_suspension_owner_notifications=owner_notification_result,
    )
