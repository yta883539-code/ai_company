#!/usr/bin/env python3
"""
payment-suspension-owner-notification-design.mdで設計した「Cloud Function F:
send_payment_suspension_owner_notifications」を、実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のオーナーLINEユーザーID(または運営用グループID)の取得・設定、実LINE Push Message
  APIでの送信はオーナー承認待ち(README.md「実LLM呼び出し・実LINE API接続」の記載範囲に
  含まれる、新規の承認待ち事項ではない)。本モジュールはそれとは別に、「いつ・どの顧客の
  制限モード移行をオーナーへ知らせるべきか」の判定ロジック(design 3節)と、「実際に送る
  メッセージの整形・送信・冪等性のための書き込み」の配線を実クラウド接続なしで検証可能に
  したもの(payment_failure_reminder_scheduler.pyと同じ位置づけ)。
- LinePushClient・LinePushDeliveryErrorはtrial_end_scheduler.pyで既に定義済みのものを
  そのまま再利用する(本モジュールで重複定義しない)。ただし本通知の送信先は顧客ごとの
  user_idではなく固定のオーナー1件であるため、send_message()に渡すidは
  OWNER_LINE_USER_ID_PLACEHOLDERで固定する。

設計の参照元: payment-suspension-owner-notification-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol, Sequence

from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# payment-failure-dunning-design.md 3節と同じ暫定値(他venture共通、実測データなし)。
DEFAULT_GRACE_PERIOD_DAYS = 7

# design 2節: 実際のオーナーLINEユーザーIDが確定するまでのプレースホルダ。
# trial_end_scheduler.pyのLIFF_URL_PLACEHOLDERと同じ考え方(実値は実LINE API接続後に
# 設定値として差し込む)。
OWNER_LINE_USER_ID_PLACEHOLDER = "{オーナーLINEユーザーID}"


@dataclass(frozen=True)
class PaymentSuspensionCustomerState:
    """payment-suspension-owner-notification-design.md 3節が参照する、顧客1件分の
    usage_counter状態。payment_failure_detected_at・payment_suspension_owner_notified_atは
    InMemoryUsageCounter(cloud_function_webhook.py)に既存のフィールドをそのまま反映する。"""

    user_id: str
    payment_failure_detected_at: Optional[datetime]
    payment_suspension_owner_notified_at: Optional[datetime] = None


def select_due_payment_suspension_owner_notifications(
    customers: Sequence[PaymentSuspensionCustomerState],
    now: datetime,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
) -> list[PaymentSuspensionCustomerState]:
    """payment-suspension-owner-notification-design.md 3節の抽出条件をそのままコード化した
    もの。

    以下すべてを満たす顧客のみを対象として返す(順序はcustomersの入力順を維持する)。
    - payment_failure_detected_atが設定済み
    - now - payment_failure_detected_at >= grace_period_days
      (design 3節: 既に制限モードへ移行済みの顧客のみを対象とする。
      select_due_payment_failure_reminders()の上限側条件「< grace_period_days」と
      ちょうど対になる)
    - payment_suspension_owner_notified_atが未設定(1回のみ送信)
    """

    threshold = timedelta(days=grace_period_days)
    due: list[PaymentSuspensionCustomerState] = []
    for customer in customers:
        if customer.payment_failure_detected_at is None:
            continue
        if customer.payment_suspension_owner_notified_at is not None:
            continue
        elapsed = now - customer.payment_failure_detected_at
        if elapsed < threshold:
            continue
        due.append(customer)
    return due


class PaymentSuspensionCustomerStateReader(Protocol):
    """InMemoryUsageCounter(cloud_function_webhook.py)のうち、
    build_payment_suspension_customer_states()が実際に使う2メソッドのみを要求する
    最小限のProtocol(trial_end_scheduler.pyのTrialUserStateReaderと同じ考え方)。"""

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        ...

    def get_payment_suspension_owner_notified_at(self, user_id: str) -> Optional[datetime]:
        ...


def build_payment_suspension_customer_states(
    usage_counter: PaymentSuspensionCustomerStateReader,
    user_ids: Sequence[str],
) -> list[PaymentSuspensionCustomerState]:
    """usage_counterの各getterから、user_idごとにPaymentSuspensionCustomerStateを組み立てる。

    trial_end_scheduler.build_trial_user_states()(フェーズ130)と同種の配線漏れの
    観点で発見: stripe_webhook.dispatch_stripe_event()が`invoice.payment_failed`受信時に
    書き込むpayment_failure_detected_atと、select_due_payment_suspension_owner_
    notifications()が読むpayment_failure_detected_atは、これまでPaymentSuspension
    CustomerStateが各テスト・_demo()内で手動構築されるのみで、実際のUsageCounterProtocol
    実装(InMemoryUsageCounter等)から読み取って組み立てる関数が存在しなかったため、
    実際に同一のusage_counter経由でつながることを確認する手段がなかった。呼び出し元は
    実際にはFirestoreクエリの結果としてuser_idsを得る想定で、本関数はその後の1件ずつの
    フィールド読み出し部分のみを担う(design 3節「usage_counterストアから対象顧客を抽出」
    に相当)。
    """
    states: list[PaymentSuspensionCustomerState] = []
    for user_id in user_ids:
        states.append(
            PaymentSuspensionCustomerState(
                user_id=user_id,
                payment_failure_detected_at=usage_counter.get_payment_failure_detected_at(
                    user_id
                ),
                payment_suspension_owner_notified_at=(
                    usage_counter.get_payment_suspension_owner_notified_at(user_id)
                ),
            )
        )
    return states


# ---------------------------------------------------------------------------
# メッセージ整形(payment-suspension-owner-notification-design.md 4節)
# ---------------------------------------------------------------------------

PAYMENT_SUSPENSION_OWNER_NOTIFICATION_TEMPLATE = (
    "[コースセットパシャッと運営] 制限モード移行のお知らせ\n"
    "\n"
    "以下の顧客が決済失敗の猶予期間({grace_period_days}日)を超え、投稿文生成の"
    "制限モードへ移行しました。\n"
    "\n"
    "顧客ID: {user_id}\n"
    "決済失敗検知からの経過日数: {elapsed_days}日\n"
    "\n"
    "必要に応じて顧客への個別フォロー(お支払い方法のご案内等)をご検討ください。"
)


def format_payment_suspension_owner_notification_message(
    customer: PaymentSuspensionCustomerState,
    now: datetime,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
) -> str:
    """design 4節の文言を、顧客ごとの`user_id`・経過日数を埋め込んで組み立てる。
    全顧客共通の固定文言だったpayment_failure_reminder_scheduler.pyの通知文言とは異なり
    顧客ごとに内容が変わるため、呼び出し側(ループ内)で1件ずつ組み立てる想定。"""
    assert customer.payment_failure_detected_at is not None
    elapsed_days = (now - customer.payment_failure_detected_at).days
    return PAYMENT_SUSPENSION_OWNER_NOTIFICATION_TEMPLATE.format(
        grace_period_days=grace_period_days,
        user_id=customer.user_id,
        elapsed_days=elapsed_days,
    )


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function F本体)
# ---------------------------------------------------------------------------


class PaymentSuspensionOwnerNotifiedAtWriter(Protocol):
    """cloud_function_webhook.py UsageCounterProtocolのうち、本モジュールが実際に使う
    1メソッドのみを要求する最小限のProtocol(payment_failure_reminder_scheduler.pyの
    PaymentFailureReminderSentAtWriterと同じ考え方)。"""

    def set_payment_suspension_owner_notified_at(self, user_id: str, notified_at: datetime) -> None:
        ...


@dataclass
class SendPaymentSuspensionOwnerNotificationsResult:
    """1回のCloud Function F起動での送信結果(呼び出し側のログ・監視用、
    SendPaymentFailureRemindersResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id(顧客側の識別子)
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_payment_suspension_owner_notifications(
    customers: Sequence[PaymentSuspensionCustomerState],
    now: datetime,
    usage_counter: PaymentSuspensionOwnerNotifiedAtWriter,
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
) -> SendPaymentSuspensionOwnerNotificationsResult:
    """payment-suspension-owner-notification-design.md 5節「Cloud Function F」本体。
    引数のcustomersは呼び出し元でFirestoreから読み取った候補一覧を想定し(3節の抽出条件を
    クエリ化したものに相当)、実際の絞り込みはselect_due_payment_suspension_owner_
    notifications()が行う。

    送信先は顧客ごとのuser_idではなく固定のowner_line_user_id(design 2節)。
    送信成功時のみusage_counter.set_payment_suspension_owner_notified_at()を対象顧客の
    user_idに対して書き込み、送信失敗時は書き込まない(payment_failure_reminder_
    scheduler.pyのsend_payment_failure_reminders()と同じ「書き込み一発+次回実行時に
    自然に再試行対象として残る」方式)。顧客ごとに文面が変わるため、メッセージ整形は
    ループ内で1件ずつ行う。
    """
    result = SendPaymentSuspensionOwnerNotificationsResult()

    for customer in select_due_payment_suspension_owner_notifications(
        customers, now, grace_period_days
    ):
        text = format_payment_suspension_owner_notification_message(
            customer, now, grace_period_days
        )
        try:
            push_client.send_message(owner_line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append(customer.user_id)
            continue
        usage_counter.set_payment_suspension_owner_notified_at(customer.user_id, now)
        result.sent.append(customer.user_id)

    return result


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    now = datetime(2026, 8, 29, 15, 0, 0)
    customers = [
        # 検知から10日経過(7日以上): 対象
        PaymentSuspensionCustomerState(
            user_id="u1", payment_failure_detected_at=now - timedelta(days=10)
        ),
        # 検知から5日しか経過していない(まだ猶予期間中): 対象外
        PaymentSuspensionCustomerState(
            user_id="u2", payment_failure_detected_at=now - timedelta(days=5)
        ),
        # 既にオーナー通知送信済み: 対象外
        PaymentSuspensionCustomerState(
            user_id="u3",
            payment_failure_detected_at=now - timedelta(days=12),
            payment_suspension_owner_notified_at=now - timedelta(days=1),
        ),
        # 決済失敗未検知: 対象外
        PaymentSuspensionCustomerState(user_id="u4", payment_failure_detected_at=None),
    ]
    due = select_due_payment_suspension_owner_notifications(customers, now)
    print([c.user_id for c in due])

    class _InMemoryUsageCounterStub:
        def __init__(self) -> None:
            self.owner_notified_at: dict[str, datetime] = {}

        def set_payment_suspension_owner_notified_at(
            self, user_id: str, notified_at: datetime
        ) -> None:
            self.owner_notified_at[user_id] = notified_at

    usage_counter = _InMemoryUsageCounterStub()
    push = InMemoryLinePushClient()
    result = send_payment_suspension_owner_notifications(customers, now, usage_counter, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
