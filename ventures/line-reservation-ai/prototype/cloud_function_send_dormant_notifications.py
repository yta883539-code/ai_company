#!/usr/bin/env python3
"""
dormant-mode-renotification-design.md 2節・4.2節で設計した休止モード関連通知
(dormant_mode_scheduler.pyのselect_due_dormant_events()・render_dormant_message())と、
LinePushClient(実送信、cloud_function_process_event.pyで定義済み)を実際につなぐ
「Cloud Function: send_dormant_notifications」の配線を実装したもの。

位置づけ:
- 実際のCloud Scheduler設定・決済代行サービスとの契約・LINE Push Message APIでの送信は
  引き続きオーナー承認待ち(pending-approval.md参照)。cloud_function_send_dunning_
  notifications.pyと同じく、実クラウド接続なしで検証可能な配線ロジック自体を実装する。
- 復旧通知(render_dormant_recovery_message())は決済代行サービスのWebhook
  (subscription_activated)を直接トリガーとする別経路で送る想定のため、本モジュールの
  スコープ外(スケジュール起動で送る「移行時/2通目/3通目/最終」の4種類のみを扱う)。
  cloud_function_send_dunning_notifications.pyが決済成功復旧通知を対象外にしたのと
  同じ役割分担。
- select_due_dormant_events()は1店舗につき最大1件のイベントしか返さない(移行時
  未送信ならそれのみ、送信済みなら次のrenotifyのみ)ため、本モジュールも1回の起動で
  各店舗につき最大1件のみ送信する。複数回分の未送信が溜まっている場合は次回以降の
  起動で1件ずつ追いつく(dormant_mode_scheduler.select_due_dormant_events()の
  既存の設計をそのまま踏襲、変更しない)。
- 冪等性はselect_due_dormant_events()自体がdormant_transitioned_at・
  dormant_renotify_countの2フィールドで判定するため、本モジュールは送信成功時のみ
  この2フィールドを書き込む(「送信成功時のみ状態を書き込む」設計、aircon-pashaの
  handle_payment_failure_detected()・本venture内のsend_dunning_notifications()と同じ)。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    LinePushClient,
    LinePushDeliveryError,
)
from dormant_mode_scheduler import (  # noqa: E402
    DormantEvent,
    render_dormant_message,
    select_due_dormant_events,
)


@dataclass
class StoreDormantState:
    """1店舗ぶんの休止モード関連状態(select_due_dormant_events()が参照する
    DormantScheduleStateと同じフィールド名に、通知送信に必要な項目を加えたもの)。

    dormant_mode_scheduler.DormantScheduleStateはfrozenのため送信成功時の書き換えが
    できない。select_due_dormant_events()はダックタイピングで属性を読むだけなので、
    frozenでない本クラスをそのまま渡して使い回す(cloud_function_send_dunning_
    notifications.StoreDunningStateと同じ考え方)。
    """

    store_id: str
    owner_line_user_id: str
    payment_page_url: str
    trial_end_report_sent_at: Optional[datetime]
    suspension_reason: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    dormant_transitioned_at: Optional[datetime] = None
    dormant_renotify_count: int = 0
    message_tone: str = "standard"


@dataclass
class SendDormantNotificationsResult:
    """1回のCloud Function起動での送信結果(呼び出し側のログ・監視用)。"""

    sent: list[tuple[str, str]] = field(default_factory=list)  # (store_id, event_key)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (store_id, event_key)


def _event_key(event: DormantEvent) -> str:
    """冪等性ログ・監視用のキー。labelがある場合(renotify)は連結する。"""
    return f"{event.event_type}:{event.label}" if event.label else event.event_type


def send_dormant_notifications(
    stores: list[StoreDormantState], now: datetime, push_client: LinePushClient
) -> SendDormantNotificationsResult:
    """dormant-mode-renotification-design.mdの休止モード関連通知(移行時/2通目/3通目/
    最終)を実際に送信する。引数のstoresは呼び出し元でFirestoreから読み取った、休止モード
    対象(トライアル終了レポート送信済みかつsuspension_reasonがpayment_failedでない)
    店舗一覧を想定する。
    """
    result = SendDormantNotificationsResult()

    for due in select_due_dormant_events(stores, now):
        state = due.state
        event = due.event
        key = _event_key(event)
        text = render_dormant_message(event, state.payment_page_url, tone=state.message_tone)
        try:
            push_client.send_message(state.owner_line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append((state.store_id, key))
            continue
        if event.event_type == "transitioned":
            # dormant_mode_scheduler.select_due_dormant_events()のdocstringが前提とする
            # 「1通目送信時に初めてsuspension_reasonがtrial_unselectedに書き換わる」を、
            # 実際にここで行う(次回起動時のrenotify判定・owner-settings-wireframe.mdの
            # 状態表示が正しく機能するために必須)。
            state.dormant_transitioned_at = event.scheduled_at
            state.suspension_reason = "trial_unselected"
        else:
            state.dormant_renotify_count += 1
        result.sent.append((state.store_id, key))

    return result


def _demo() -> None:
    from cloud_function_process_event import InMemoryLinePushClient
    from dormant_mode_scheduler import GRACE_PERIOD_DAYS

    push = InMemoryLinePushClient()
    report_sent_at = datetime(2026, 8, 20, 10, 0)
    store = StoreDormantState(
        store_id="store-1",
        owner_line_user_id="owner-line-1",
        payment_page_url="https://example.com/billing",
        trial_end_report_sent_at=report_sent_at,
        message_tone="casual",
    )

    # 1) 猶予期間(3日)終了時点: 「transitioned」のみ送信対象。
    transitioned_at = report_sent_at + timedelta(days=GRACE_PERIOD_DAYS)
    result = send_dormant_notifications([store], transitioned_at, push)
    print("1回目(移行時):", result.sent, result.failed)

    # 2) 移行から7日後: 「renotify:2nd」のみが新規送信対象。
    result = send_dormant_notifications([store], transitioned_at + timedelta(days=7), push)
    print("2回目(2通目):", result.sent, result.failed)

    # 3) 同じ時刻で再実行しても、送信済みのため重複送信されない(冪等性の確認)。
    result = send_dormant_notifications([store], transitioned_at + timedelta(days=7), push)
    print("3回目(冪等性確認、空のはず):", result.sent, result.failed)

    print("送信済みログ件数:", len(push.sent))
    print("店舗の状態:", store.dormant_transitioned_at, store.dormant_renotify_count)


if __name__ == "__main__":
    _demo()
