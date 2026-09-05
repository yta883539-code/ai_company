#!/usr/bin/env python3
"""
reminder-scheduler-design.mdで設計した「Cloud Function C: send_reminders」の
判断ロジックを、実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信は「アカウント作成」
  「支払い」に該当し、引き続きオーナー承認待ち(pending-approval.md参照)。
  本モジュールはそれとは別に、「いつ・どの予約にリマインド/再送を送るべきか」という
  判断ロジック自体を実クラウド接続なしで検証可能にしたもの。
- engine.pyのformat_reminder_message()と組み合わせて使う想定
  (本モジュールは送信要否の判定のみを担当し、メッセージ整形・実送信はengine.py/
  cloud_function_process_event.pyのLinePushClientプロトコルの領分とする)。

設計の参照元: reminder-scheduler-design.md, reminder-timing-and-resend-rules.md
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from engine import _normalize_business_hour_ranges  # noqa: E402

# reminder-timing-and-resend-rules.md: デフォルトのリマインド送信時刻は
# 「営業終了1時間前、ただし20:00を上限」。
DEFAULT_REMINDER_LEAD_MINUTES = 60
DEFAULT_REMINDER_CAP_MINUTES = 20 * 60  # 20:00
DEFAULT_BUSINESS_OPEN_MINUTES = 9 * 60  # 9:00(再送の当日朝の基準時刻)

# 定休日が連続する異常設定での無限ループを避けるための遡り上限(1週間分)。
MAX_LOOKBACK_DAYS = 7


class ReminderConfigError(ValueError):
    """定休日設定が7日以上連続する等、目標時刻を決定できない異常設定の場合に送出する。"""


@dataclass
class StoreReminderConfig:
    """1店舗分の、リマインド目標時刻算出に必要な設定
    (owner-settings-wireframe.md / firestore-data-model.md stores/{storeId} の一部)。
    """

    business_hours: object  # (開始,終了) または [(開始,終了), ...]、engine.py同様
    closed_weekdays: frozenset = frozenset()
    closed_dates: frozenset = frozenset()  # ad-hoc-closed-dates-support.md準拠(臨時休業日、date集合)
    weekday_business_hours: Optional[dict] = None
    reminder_time_minutes: Optional[int] = None  # 店舗が明示設定したリマインド送信時刻(分)
    message_tone: str = "standard"  # owner-settings-wireframe.md「メッセージトーン」設定
    # (message-tone-variants.md準拠。format_reminder_message()/format_reminder_resend_message()の
    # tone引数にそのまま渡す想定。未知の値はengine.py側で"standard"にフォールバックする)


@dataclass
class ReminderBooking:
    """予約1件分の、リマインド送信判定に必要な情報
    (firestore-data-model.md conversations/{sessionId} のうちreminder関連フィールド)。
    """

    booking_id: str
    store_id: str
    booking_date: date
    start_minutes: int  # 予約開始時刻(0時からの分)
    confirmed_at: datetime
    reminder_sent_at: Optional[datetime] = None
    reminder_skipped: bool = False
    resend_sent_at: Optional[datetime] = None
    customer_replied_at: Optional[datetime] = None
    # archive-trigger-unification-design.md準拠。confirmed-state-archival.mdの
    # archivedAtフィールドに対応(select_confirmed_to_archive()の選定対象・除外条件に使う)。
    archived_at: Optional[datetime] = None
    # 以下2フィールドは選定ロジック自体では未使用だが、選定結果をそのまま
    # cloud_function_send_reminders.pyでのメッセージ整形・送信に渡せるよう、
    # firestore-data-model.mdのconversationsドキュメントが元々保持している値をここにも運ぶ。
    line_user_id: str = ""  # LINE Push Message API送信先(未設定のまま送信対象になった場合は呼び出し側の設計ミス)
    menu: str = ""  # format_reminder_message()/format_reminder_resend_message()のmenu引数


def _business_end_minutes(target_date: date, store: StoreReminderConfig) -> int:
    ranges = _normalize_business_hour_ranges(
        (store.weekday_business_hours or {}).get(target_date.weekday(), store.business_hours)
    )
    return max(close for _, close in ranges)


def compute_initial_reminder_target(booking_date: date, store: StoreReminderConfig) -> datetime:
    """reminder-timing-and-resend-rules.md ルール1準拠。
    予約日の前日を起点に、定休日(曜日単位)または臨時休業日(特定日付単位)であれば
    前営業日へ遡り、その営業日の目標時刻(分)を店舗設定または「営業終了1時間前・20:00上限」の
    デフォルトで決定する。
    """
    day = booking_date - timedelta(days=1)
    lookback = 0
    while day.weekday() in store.closed_weekdays or day in store.closed_dates:
        day -= timedelta(days=1)
        lookback += 1
        if lookback > MAX_LOOKBACK_DAYS:
            raise ReminderConfigError(
                f"定休日設定が{MAX_LOOKBACK_DAYS}日を超えて連続しており、"
                "リマインド送信日を決定できません"
            )

    if store.reminder_time_minutes is not None:
        target_minutes = store.reminder_time_minutes
    else:
        end_minutes = _business_end_minutes(day, store)
        target_minutes = min(end_minutes - DEFAULT_REMINDER_LEAD_MINUTES, DEFAULT_REMINDER_CAP_MINUTES)

    return datetime(day.year, day.month, day.day) + timedelta(minutes=target_minutes)


def should_send_initial_reminder(target_datetime: datetime, confirmed_at: datetime) -> bool:
    """reminder-timing-and-resend-rules.md ルール2準拠。
    確定した時点で既に目標送信時刻を過ぎている場合は、前日リマインドを送らず
    確定メッセージでの代用に委ねる(呼び出し側は確定処理時にもこの関数を呼び、
    Trueが返った場合のみ`reminder_sent_at`未設定のまま予約を作成する想定)。
    """
    return confirmed_at <= target_datetime


def select_due_initial_reminders(
    bookings: list[ReminderBooking],
    now: datetime,
    stores: dict[str, StoreReminderConfig],
) -> list[ReminderBooking]:
    """reminder-scheduler-design.md「冪等性の設計」準拠。
    店舗ごとの目標時刻ちょうどへの一致は要求せず、(1)未送信、(2)目標時刻を過ぎている、
    (3)予約日をまだ迎えていない、の3条件のみで判定することで、Cloud Schedulerの
    実行間隔・遅延に対して自然に追いつける。

    `stores`は`{storeId: StoreReminderConfig}`(firestore-data-model.mdの
    `stores/{storeId}`に対応)。全店舗分のbookingsを1回のCloud Scheduler起動で
    まとめて処理するため、`booking.store_id`で対応する設定を引く。
    """
    due: list[ReminderBooking] = []
    for booking in bookings:
        if booking.reminder_sent_at is not None or booking.reminder_skipped:
            continue
        if booking.booking_date <= now.date():
            continue
        store = stores[booking.store_id]
        target = compute_initial_reminder_target(booking.booking_date, store)
        if not should_send_initial_reminder(target, booking.confirmed_at):
            booking.reminder_skipped = True
            continue
        if target <= now:
            due.append(booking)
    return due


def select_due_resends(
    bookings: list[ReminderBooking],
    now: datetime,
    business_open_minutes: int = DEFAULT_BUSINESS_OPEN_MINUTES,
) -> list[ReminderBooking]:
    """reminder-timing-and-resend-rules.md ルール3(再送は当日朝1回のみ)準拠。
    - 初回リマインド未送信、既に再送済み、返信済みの予約は対象外。
    - 予約日が当日でない場合は対象外。
    - 予約開始時刻が営業開始時刻(デフォルト9:00)より前の場合、当日朝の再送は
      間に合わないため対象外(ルール3「再送を行わないケース」)。
    - 現在時刻が営業開始時刻を過ぎていない場合はまだ対象外(翌回以降の実行を待つ)。
    """
    due: list[ReminderBooking] = []
    for booking in bookings:
        if booking.reminder_sent_at is None:
            continue
        if booking.resend_sent_at is not None or booking.customer_replied_at is not None:
            continue
        if booking.booking_date != now.date():
            continue
        if booking.start_minutes < business_open_minutes:
            continue
        open_dt = datetime(now.year, now.month, now.day) + timedelta(minutes=business_open_minutes)
        if now >= open_dt:
            due.append(booking)
    return due


# confirmed-state-archival.mdのARCHIVE_AFTER_VISIT(1日)と同じ値。
# archive-trigger-unification-design.md準拠でCloud Function C側にも複製する
# (ロジックの整合性はテストで担保する。confirmed-state-archival.md側の値を
# 変更した場合は本値も合わせて変更すること)。
ARCHIVE_AFTER_VISIT_DAYS = 1


def select_confirmed_to_archive(
    bookings: list[ReminderBooking],
    now: datetime,
    after_visit_days: int = ARCHIVE_AFTER_VISIT_DAYS,
) -> list[ReminderBooking]:
    """archive-trigger-unification-design.md準拠。
    confirmed-state-archival.mdのarchive_completed_conversations()と同じ判定
    (来店日からafter_visit_days日以上経過、かつ未アーカイブ)を、Cloud Function C
    (send_reminders、全店舗横断で15分間隔起動)側でも実行できるようにしたもの。

    idle-conversation-trigger-design.mdのWebhook便乗トリガー(maybe_run_archive())は
    店舗ごとにWebhookが届かない限り実行されず、来店日超過後にその店舗への問い合わせが
    途絶えると際限なく遅延しうる。Cloud Function Cは店舗の問い合わせ有無に関係なく
    全店舗を定期的に見て回るため、こちらを正規のトリガーとすることで最大遅延を
    Cloud Schedulerの起動間隔(暫定15分)まで縮められる。
    """
    to_archive: list[ReminderBooking] = []
    for booking in bookings:
        if booking.archived_at is not None:
            continue
        if (now.date() - booking.booking_date).days < after_visit_days:
            continue
        to_archive.append(booking)
    return to_archive
