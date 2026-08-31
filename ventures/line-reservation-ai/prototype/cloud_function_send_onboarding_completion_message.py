#!/usr/bin/env python3
"""
onboarding-completion-message-design.md「残課題」に残っていた、
store_profile_store.evaluate_onboarding_completion_message_dispatch()(判定ロジック、
2026-08-30実装済み)とonboarding_completion_message.render_onboarding_completion_message()
(メッセージ整形)・LinePushClient(実送信、cloud_function_process_event.pyで定義済み)を
実際につなぐ配線を実装したもの。

位置づけ:
- owner-settings-wireframe.mdのフォーム保存処理から、店舗設定の保存の都度呼ばれる想定
  (dormant通知・リマインド等のCloud Scheduler起動のバッチ配線とは異なり、1店舗ぶんの
  保存イベント1件に対して同期的に呼ばれる、Cloud Function Bと同種の配線)。
- evaluate_onboarding_completion_message_dispatch()は判定と同時に送信済みフラグを
  立てる「consume」型の関数(first-booking-self-check-notification-design.mdの
  consume_first_booking_self_check()と同じ設計)。そのため本モジュールも同じ制約を
  引き継ぐ: LinePushClient.send_message()がLinePushDeliveryErrorを送出した場合でも
  送信済みフラグは既に立っており、次回以降の保存では再送されない(MVPスコープの
  割り切りとして許容し、再送機構は設けない)。
- 実際のowner-settings-wireframe.mdフォーム保存処理自体(Firestore書き込み・実UI)は
  ホスティング基盤確定後の配線が引き続き必要(オーナー承認待ち)。本モジュールは
  実クラウド接続なしで検証可能な「判定→整形→送信呼び出し」の配線ロジック自体を扱う。

設計の参照元: onboarding-completion-message-design.md 3節・4節、
store_profile_store.evaluate_onboarding_completion_message_dispatch()
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import LinePushClient  # noqa: E402
from onboarding_completion_message import (  # noqa: E402
    render_onboarding_completion_message,
)
from store_profile_store import (  # noqa: E402
    StoreProfileStoreProtocol,
    evaluate_onboarding_completion_message_dispatch,
)


def handle_onboarding_completion_message_dispatch(
    user_id: str,
    *,
    business_hours_configured: bool,
    slot_interval_minutes: Optional[int],
    concurrent_capacity: Optional[int],
    menu_count: int,
    store: StoreProfileStoreProtocol,
    payment_page_url: str,
    push_client: LinePushClient,
    tone: str = "standard",
) -> bool:
    """owner-settings-wireframe.mdのフォーム保存処理から都度呼ばれる想定の配線本体。

    evaluate_onboarding_completion_message_dispatch()がTrueを返した場合のみ
    (=今回の保存で初めてMVPの最低限必須項目が揃った場合のみ)、
    render_onboarding_completion_message()でメッセージ本文を組み立てて
    push_client.send_message()で送信する。戻り値は送信を試みたかどうか
    (evaluate側の判定結果)であり、送信自体が成功したかどうかは表さない
    (LinePushDeliveryError発生時は呼び出し元に例外がそのまま伝播する)。
    """
    should_dispatch = evaluate_onboarding_completion_message_dispatch(
        user_id,
        business_hours_configured=business_hours_configured,
        slot_interval_minutes=slot_interval_minutes,
        concurrent_capacity=concurrent_capacity,
        menu_count=menu_count,
        store=store,
    )
    if not should_dispatch:
        return False

    message = render_onboarding_completion_message(payment_page_url, tone=tone)
    push_client.send_message(user_id, message)
    return True
