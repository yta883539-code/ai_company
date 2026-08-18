#!/usr/bin/env python3
"""
payment-failure-dunning-design.mdの残課題だった、dunning_notification_scheduler.py
(いつ・どの店舗にどの通知を送るべきかの予定表算出・文面整形)とLinePushClient(実送信、
cloud_function_process_event.pyで定義済み)を実際につなぐ「Cloud Function D:
send_dunning_notifications」の配線を実装したもの。

位置づけ:
- 実際のCloud Scheduler設定・決済代行サービスとの契約・LINE Push Message APIでの送信は
  「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち(pending-approval.md参照)。
  本モジュールはcloud_function_send_reminders.py(Cloud Function C)と同じく、実クラウド
  接続なしで検証可能な「配線ロジック自体」を実装する。
- LinePushClient/InMemoryLinePushClient/LinePushDeliveryErrorはCloud Function Bで
  定義済みのものをそのまま再利用する(送信先が店舗オーナーであっても同じLINE Messaging APIの
  ため。reminder_scheduler.py・payment-failure-dunning-design.md 4節の前例を踏襲)。
- 決済成功による復旧通知(render_recovery_message())は、決済代行サービスのWebhook
  (payment_succeeded)を直接トリガーとする別経路(Cloud Function A/B相当)で送る想定のため、
  本モジュールのスコープ外(スケジュール起動で送る「検知時・リマインド・制限モード移行」の
  3種類のみを扱う)。
- 冪等性はreminder-scheduler-design.mdの冪等性の設計に倣い、`sent_event_keys`に送信済み
  イベントのキー("detected"/"reminder:midpoint"/"reminder:final"/"suspended")を記録する
  ことで、次回のCloud Scheduler起動時に重複送信しない設計とした。同一店舗内のイベントは
  古い順(検知→中間地点→終了直前→制限モード移行)に依存関係があるため、送信失敗時は
  その店舗のそれ以降のイベントを送らずに次回に持ち越す(reminder_scheduler.pyの各予約は
  互いに独立という前提と異なり、dunningは同一店舗内で時系列の前提があるための差分)。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    LinePushClient,
    LinePushDeliveryError,
)
from dunning_notification_scheduler import (  # noqa: E402
    DunningConfig,
    DunningEvent,
    compute_dunning_schedule,
    render_dunning_message,
)


def _event_key(event: DunningEvent) -> str:
    """sent_event_keysで使う冪等性判定用のキー。labelがある場合は連結する。"""
    return f"{event.event_type}:{event.label}" if event.label else event.event_type


@dataclass
class StoreDunningState:
    """1店舗ぶんのdunning進行状態(Firestoreのstoresドキュメントに相当する項目のみ抜粋)。

    payment_failure_detected_atがNoneの店舗は決済失敗が検知されていない(=対象外)。
    sent_event_keysは呼び出し元でFirestoreから読み取った送信済みイベントキーの集合を想定。
    """

    store_id: str
    owner_line_user_id: str
    payment_failure_detected_at: datetime | None
    config: DunningConfig
    payment_page_url: str
    message_tone: str = "standard"
    suspension_reason: str | None = None
    sent_event_keys: set[str] = field(default_factory=set)


@dataclass
class SendDunningNotificationsResult:
    """1回のCloud Function D起動での送信結果(呼び出し側のログ・監視用)。"""

    sent: list[tuple[str, str]] = field(default_factory=list)  # (store_id, event_key)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (store_id, event_key)


def select_due_dunning_events(state: StoreDunningState, now: datetime) -> list[DunningEvent]:
    """state.payment_failure_detected_atを起点に予定表を算出し、未送信かつ予定時刻を
    過ぎているイベントのみを古い順に返す(compute_dunning_schedule()自体が既に時系列順)。
    """
    if state.payment_failure_detected_at is None:
        return []
    schedule = compute_dunning_schedule(state.payment_failure_detected_at, state.config)
    return [
        event
        for event in schedule
        if event.scheduled_at <= now and _event_key(event) not in state.sent_event_keys
    ]


def send_dunning_notifications(
    stores: list[StoreDunningState], now: datetime, push_client: LinePushClient
) -> SendDunningNotificationsResult:
    """payment-failure-dunning-design.mdの「Cloud Function D: send_dunning_notifications」本体。
    引数のstoresは呼び出し元でFirestoreから読み取った、決済失敗検知中の店舗一覧を想定。
    """
    result = SendDunningNotificationsResult()

    for state in stores:
        for event in select_due_dunning_events(state, now):
            key = _event_key(event)
            text = render_dunning_message(
                event, state.config, state.payment_page_url, tone=state.message_tone
            )
            try:
                push_client.send_message(state.owner_line_user_id, text)
            except LinePushDeliveryError:
                result.failed.append((state.store_id, key))
                # 同一店舗内は時系列の前提があるため、失敗した回より後のイベントは
                # 今回は送らず次回起動に持ち越す(検知未送信のまま先にリマインドを送る等の
                # 矛盾を避けるため)。
                break
            state.sent_event_keys.add(key)
            if event.event_type == "suspended":
                state.suspension_reason = "payment_failed"
            result.sent.append((state.store_id, key))

    return result


def _demo() -> None:
    from cloud_function_process_event import InMemoryLinePushClient
    from dunning_notification_scheduler import DUNNING_CONFIG_A_7DAYS

    push = InMemoryLinePushClient()
    detected_at = datetime(2026, 8, 17, 10, 0)
    store = StoreDunningState(
        store_id="store-1",
        owner_line_user_id="owner-line-1",
        payment_failure_detected_at=detected_at,
        config=DUNNING_CONFIG_A_7DAYS,
        payment_page_url="https://example.com/billing",
        message_tone="casual",
    )

    # 1) 検知時刻ちょうど: 「detected」のみ送信対象。
    result = send_dunning_notifications([store], detected_at, push)
    print("1回目(検知時):", result.sent, result.failed)

    # 2) 4日後(終了直前リマインド予定時刻): 「reminder:final」のみが新規送信対象。
    result = send_dunning_notifications([store], detected_at.replace(day=21), push)
    print("2回目(終了直前リマインド):", result.sent, result.failed)

    # 3) 同じ時刻で再実行しても、送信済みのため重複送信されない(冪等性の確認)。
    result = send_dunning_notifications([store], detected_at.replace(day=21), push)
    print("3回目(冪等性確認、空のはず):", result.sent, result.failed)

    print("送信済みログ件数:", len(push.sent))
    print("店舗の状態:", store.suspension_reason, store.sent_event_keys)


if __name__ == "__main__":
    _demo()
