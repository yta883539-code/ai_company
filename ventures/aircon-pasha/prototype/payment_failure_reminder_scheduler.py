#!/usr/bin/env python3
"""
payment-failure-reminder-scheduler-design.md(フェーズ143)で設計した「Cloud Function F:
send_payment_failure_reminders」を、実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信はいずれもオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「いつ・どのユーザーに決済失敗
  猶予期間終了直前リマインドを送るべきか」の判定ロジック(design 3節)と、「実際に送る
  メッセージの整形・送信・冪等性のための書き込み」の配線を実クラウド接続なしで検証可能に
  したもの(trial_end_scheduler.pyと同じ位置づけ・同じ構成)。
- ボタンのlabel・postbackデータはcloud_function_webhook.pyの
  UPDATE_PAYMENT_METHOD_BUTTON_LABEL・UPDATE_PAYMENT_METHOD_POSTBACK_DATA(制限モード
  案内向けにフェーズ141〜142で導入済み)をそのまま再利用する(design 4節)。

設計の参照元: payment-failure-reminder-scheduler-design.md, payment-failure-dunning-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol, Sequence

from cloud_function_webhook import (
    UPDATE_PAYMENT_METHOD_BUTTON_LABEL,
    UPDATE_PAYMENT_METHOD_POSTBACK_DATA,
)

# payment-failure-dunning-design.md 3節: 猶予期間は7日、そのうち3日前(=検知から4日後)に
# リマインドを1回だけ送る(design 2節)。
DEFAULT_GRACE_PERIOD_DAYS = 7
DEFAULT_REMINDER_DAYS_BEFORE_END = 3


@dataclass(frozen=True)
class PaymentFailureReminderUserState:
    """design 3節が参照する、ユーザー1件分の`user_profile`状態。

    payment_failure_detected_at・payment_suspended_at・payment_failure_reminder_sent_at
    はuser_id_linking.pyのUserProfile(フェーズ140・143で追加した3フィールド)をそのまま
    反映する。"""

    user_id: str
    payment_failure_detected_at: Optional[datetime]
    payment_suspended_at: Optional[datetime] = None
    payment_failure_reminder_sent_at: Optional[datetime] = None


def select_due_payment_failure_reminders(
    users: Sequence[PaymentFailureReminderUserState],
    now: datetime,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
) -> list[PaymentFailureReminderUserState]:
    """design 3節の抽出条件をそのままコード化したもの。

    以下すべてを満たすユーザーのみを対象として返す(順序はusersの入力順を維持する)。
    - payment_failure_detected_atが設定済み
    - payment_suspended_atが未設定(既に制限モードへ移行済みならリマインドは不要)
    - payment_failure_reminder_sent_atが未設定(1回のみ送信)
    - now - payment_failure_detected_at >= (grace_period_days - reminder_days_before_end)日
      (「ちょうど」の時刻一致ではなく「以上」の範囲条件とすることで、日次実行の遅延・欠落に
      自然に耐える。trial_end_scheduler.pyのselect_due_trial_end_notifications()と同じ
      設計判断)
    """

    threshold = timedelta(days=grace_period_days - reminder_days_before_end)
    due: list[PaymentFailureReminderUserState] = []
    for user in users:
        if user.payment_failure_detected_at is None:
            continue
        if user.payment_suspended_at is not None:
            continue
        if user.payment_failure_reminder_sent_at is not None:
            continue
        if now - user.payment_failure_detected_at >= threshold:
            due.append(user)
    return due


# ---------------------------------------------------------------------------
# メッセージ整形(design 4節、payment-failure-dunning-design.md 4節)
# ---------------------------------------------------------------------------

PAYMENT_FAILURE_REMINDER_ALT_TEXT = "[エアコンパシャッと] お支払い確認のお願い(再送)です"

# GENERATION_PAUSED_MESSAGE・PAYMENT_SUSPENDED_MESSAGE(cloud_function_webhook.py)と
# 同じく、本文中に生URLを埋め込まずボタン(postback)を別途添付する短縮形に揃える。
PAYMENT_FAILURE_REMINDER_BODY_TEXT = (
    "お支払い手続きが未完了のままです。このままですと3日後に作業完了報告・お手入れ案内の"
    "生成を一時停止いたします。"
)


def build_payment_failure_reminder_flex_message() -> dict:
    """design 4節: 通知メッセージをFlex Messageのボタン込みで組み立てる
    (プレーンテキストリンクではない、trial_end_scheduler.pyと同じ形)。

    ボタンのlabel・postbackデータはcloud_function_webhook.pyの
    UPDATE_PAYMENT_METHOD_BUTTON_LABEL・UPDATE_PAYMENT_METHOD_POSTBACK_DATAをそのまま
    再利用する。実際のStripe Customer Portalへの遷移は、既存の
    process_postback_event()(フェーズ142)がそのまま処理する。

    戻り値はLINE Messaging APIのFlex Message `contents`(bubble)相当のdictで、
    実送信時はこれを`{"type": "flex", "altText": ..., "contents": ...}`として
    Push Message APIへ渡す想定。
    """
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": PAYMENT_FAILURE_REMINDER_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": PAYMENT_FAILURE_REMINDER_BODY_TEXT,
                    "wrap": True,
                    "margin": "md",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "postback",
                        "label": UPDATE_PAYMENT_METHOD_BUTTON_LABEL,
                        "data": UPDATE_PAYMENT_METHOD_POSTBACK_DATA,
                    },
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function F本体、design 6節の残課題の一部)
# ---------------------------------------------------------------------------


class LinePushDeliveryError(Exception):
    """LINE Push Message API呼び出し失敗(タイムアウト・5xx・429等)を表す。
    trial_end_scheduler.LinePushDeliveryErrorと対称の位置づけ。"""


class LinePushClient(Protocol):
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        ...


class InMemoryLinePushClient:
    """実LINE Push Message API接続の代わりに送信内容を記録するだけの検証用クライアント
    (trial_end_scheduler.InMemoryLinePushClientと同じ位置づけ)。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        self.sent.append((user_id, alt_text, contents))


class PaymentFailureReminderSentAtWriter(Protocol):
    """user_id_linking.py UserProfileStoreProtocolのうち、本モジュールが実際に使う
    1メソッドのみを要求する最小限のProtocol(trial_end_scheduler.TrialEndNotifiedAtWriter
    と同じ「呼び出し側は具象クラスに直接依存しない」という考え方)。"""

    def set_payment_failure_reminder_sent_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        ...


@dataclass
class SendPaymentFailureRemindersResult:
    """1回のCloud Function F起動での送信結果(呼び出し側のログ・監視用、
    trial_end_scheduler.SendTrialEndNotificationsResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_payment_failure_reminders(
    users: Sequence[PaymentFailureReminderUserState],
    now: datetime,
    profile_store: PaymentFailureReminderSentAtWriter,
    push_client: LinePushClient,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
) -> SendPaymentFailureRemindersResult:
    """design 1節の全体構成図における「Cloud Function F: send_payment_failure_reminders」
    本体。引数のusersは呼び出し元でFirestoreから読み取った候補一覧を想定し(design 3節の
    抽出条件をクエリ化したものに相当)、実際の絞り込みはselect_due_payment_failure_
    reminders()が行う。

    送信成功時のみ`profile_store.set_payment_failure_reminder_sent_at()`を書き込み、
    送信失敗時は書き込まない(design 5節の冪等性設計、trial_end_scheduler.
    send_trial_end_notifications()と同じ「書き込み一発+次回実行時に自然に再試行対象として
    残る」方式)。
    """
    result = SendPaymentFailureRemindersResult()

    for user in select_due_payment_failure_reminders(
        users, now, grace_period_days, reminder_days_before_end
    ):
        contents = build_payment_failure_reminder_flex_message()
        try:
            push_client.send_flex_message(
                user.user_id, PAYMENT_FAILURE_REMINDER_ALT_TEXT, contents
            )
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        profile_store.set_payment_failure_reminder_sent_at(user.user_id, now)
        result.sent.append(user.user_id)

    return result


def _demo() -> None:
    now = datetime(2026, 8, 28, 4, 0, 0)
    users = [
        # 検知から4日経過: 対象
        PaymentFailureReminderUserState(
            user_id="u1", payment_failure_detected_at=now - timedelta(days=4)
        ),
        # 検知から3日しか経過していない: 対象外
        PaymentFailureReminderUserState(
            user_id="u2", payment_failure_detected_at=now - timedelta(days=3)
        ),
        # 既にリマインド送信済み: 対象外
        PaymentFailureReminderUserState(
            user_id="u3",
            payment_failure_detected_at=now - timedelta(days=6),
            payment_failure_reminder_sent_at=now - timedelta(days=1),
        ),
        # 既に制限モードへ移行済み: 対象外
        PaymentFailureReminderUserState(
            user_id="u4",
            payment_failure_detected_at=now - timedelta(days=10),
            payment_suspended_at=now - timedelta(days=3),
        ),
        # 決済失敗が検知されていない: 対象外
        PaymentFailureReminderUserState(user_id="u5", payment_failure_detected_at=None),
    ]
    due = select_due_payment_failure_reminders(users, now)
    print([u.user_id for u in due])

    class _InMemoryProfileStoreStub:
        def __init__(self) -> None:
            self.reminder_sent_at: dict[str, datetime] = {}

        def set_payment_failure_reminder_sent_at(
            self, user_id: str, value: Optional[datetime]
        ) -> None:
            self.reminder_sent_at[user_id] = value

    profile_store = _InMemoryProfileStoreStub()
    push = InMemoryLinePushClient()
    result = send_payment_failure_reminders(users, now, profile_store, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push alt_text: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
