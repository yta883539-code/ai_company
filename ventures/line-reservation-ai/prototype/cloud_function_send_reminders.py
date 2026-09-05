#!/usr/bin/env python3
"""
reminder-scheduler-design.mdの「未解決のまま残る課題」に残っていた、
reminder_scheduler.py(いつ・どの予約に送るべきかの選定ロジック)とengine.pyの
format_reminder_message()/format_reminder_resend_message()(メッセージ整形)・
LinePushClient(実送信、cloud_function_process_event.pyで定義済み)を実際につなぐ
「Cloud Function C: send_reminders」の配線を実装したもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信は「アカウント作成」
  「支払い」に該当し、引き続きオーナー承認待ち(pending-approval.md参照)。
  本モジュールはCloud Function A(cloud_function_webhook.py)・B(cloud_function_process_event.py)と
  同じく、実クラウド接続なしで検証可能な「配線ロジック自体」を実装する。
- LinePushClient/InMemoryLinePushClient/LinePushDeliveryErrorはCloud Function Bで
  定義済みのものをそのまま再利用する(顧客向け送信先が同じLINE Messaging APIのため)。
- 冪等性はreminder-scheduler-design.md「冪等性の設計」準拠。送信成功時のみ
  `reminder_sent_at`/`resend_sent_at`を更新し、送信失敗(LinePushDeliveryError)時は
  更新しないことで、次回のCloud Scheduler起動時に自然に再送対象として拾われる設計とした。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushClient,
    LinePushDeliveryError,
)
from engine import (  # noqa: E402
    _WEEKDAY_JA,
    format_reminder_message,
    format_reminder_resend_message,
)
from reminder_scheduler import (  # noqa: E402
    ReminderBooking,
    StoreReminderConfig,
    select_confirmed_to_archive,
    select_due_initial_reminders,
    select_due_resends,
)


def _full_label(booking: ReminderBooking) -> str:
    """前日リマインド用の候補ラベル("8/9(土) 15:30〜")。
    AvailabilitySearcher._find_candidates()・label_from_slot_key()と同じ書式に揃える。
    """
    day = booking.booking_date
    h, m = divmod(booking.start_minutes, 60)
    return f"{day.month}/{day.day}({_WEEKDAY_JA[day.weekday()]}) {h:02d}:{m:02d}〜"


def _time_only_label(booking: ReminderBooking) -> str:
    """当日朝の再送用の候補ラベル("15:30〜")。reminder-timing-and-resend-rules.mdの
    再送メッセージ文言は「本日」表記のため日付部分を持たず、時刻のみで足りる。
    """
    h, m = divmod(booking.start_minutes, 60)
    return f"{h:02d}:{m:02d}〜"


@dataclass
class SendRemindersResult:
    """1回のCloud Function C起動での送信結果(呼び出し側のログ・監視用)。"""

    initial_sent: list[str] = field(default_factory=list)  # booking_id
    resend_sent: list[str] = field(default_factory=list)  # booking_id
    failed: list[str] = field(default_factory=list)  # booking_id(送信失敗、次回再試行)
    archived: list[str] = field(default_factory=list)  # booking_id(archive-trigger-unification-design.md)


def send_reminders(
    bookings: list[ReminderBooking],
    now: datetime,
    stores: dict[str, StoreReminderConfig],
    push_client: LinePushClient,
) -> SendRemindersResult:
    """reminder-scheduler-design.mdの全体構成図の「Cloud Function C: send_reminders」本体。
    引数のbookingsは呼び出し元でFirestoreから読み取った未送信・当日再送候補の一覧を想定
    (対象の絞り込み自体はselect_due_initial_reminders()/select_due_resends()が行う)。
    """
    result = SendRemindersResult()

    for booking in select_due_initial_reminders(bookings, now, stores):
        tone = stores[booking.store_id].message_tone
        text = format_reminder_message(_full_label(booking), booking.menu, tone=tone)
        try:
            push_client.send_message(booking.line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append(booking.booking_id)
            continue
        booking.reminder_sent_at = now
        result.initial_sent.append(booking.booking_id)

    for booking in select_due_resends(bookings, now):
        tone = stores[booking.store_id].message_tone
        text = format_reminder_resend_message(_time_only_label(booking), booking.menu, tone=tone)
        try:
            push_client.send_message(booking.line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append(booking.booking_id)
            continue
        booking.resend_sent_at = now
        result.resend_sent.append(booking.booking_id)

    # archive-trigger-unification-design.md準拠。confirmed-state-archival.mdの
    # archive_completed_conversations()の実行トリガーとして、店舗ごとのWebhook到着に
    # 依存するidle-conversation-trigger-design.mdの便乗トリガーだけでなく、全店舗横断で
    # 定期実行される本Cloud Function Cでも実行し、最大遅延をCloud Scheduler起動間隔
    # (暫定15分)まで縮める。送信処理(reminder_sent_at/resend_sent_at)とは独立した
    # 関心事のため、送信失敗の有無に関わらず常に実行する。
    for booking in select_confirmed_to_archive(bookings, now):
        booking.archived_at = now
        result.archived.append(booking.booking_id)

    return result


def _demo() -> None:
    push = InMemoryLinePushClient()
    stores = {
        "store-1": StoreReminderConfig(business_hours=(9 * 60, 18 * 60), message_tone="casual"),
    }

    # 1) 前日リマインド送信対象(目標時刻17:00を過ぎている)
    booking1 = ReminderBooking(
        booking_id="b1",
        store_id="store-1",
        booking_date=datetime(2026, 8, 10).date(),
        start_minutes=15 * 60 + 30,
        confirmed_at=datetime(2026, 8, 8, 12, 0),
        line_user_id="U1",
        menu="カット",
    )
    now1 = datetime(2026, 8, 9, 17, 30)
    result1 = send_reminders([booking1], now1, stores, push)
    print(f"1) initial_sent={result1.initial_sent}")
    print(f"   push: {push.sent[-1][1]}")

    # 2) 当日朝の再送対象(初回送信済み・未返信・営業開始9:00を過ぎている)
    booking2 = ReminderBooking(
        booking_id="b2",
        store_id="store-1",
        booking_date=datetime(2026, 8, 10).date(),
        start_minutes=15 * 60 + 30,
        confirmed_at=datetime(2026, 8, 8, 12, 0),
        reminder_sent_at=datetime(2026, 8, 9, 17, 0),
        line_user_id="U2",
        menu="カラー",
    )
    now2 = datetime(2026, 8, 10, 9, 5)
    result2 = send_reminders([booking2], now2, stores, push)
    print(f"2) resend_sent={result2.resend_sent}")
    print(f"   push: {push.sent[-1][1]}")

    # 3) 送信失敗時は状態を更新せず、次回起動時の再試行に委ねる
    class _FailingClient:
        def send_message(self, user_id: str, text: str) -> None:
            raise LinePushDeliveryError("simulated outage")

    booking3 = ReminderBooking(
        booking_id="b3",
        store_id="store-1",
        booking_date=datetime(2026, 8, 10).date(),
        start_minutes=10 * 60,
        confirmed_at=datetime(2026, 8, 8, 12, 0),
        line_user_id="U3",
        menu="トリートメント",
    )
    result3 = send_reminders([booking3], now1, stores, _FailingClient())
    print(f"3) failed={result3.failed}, reminder_sent_at={booking3.reminder_sent_at}")


if __name__ == "__main__":
    _demo()
