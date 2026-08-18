#!/usr/bin/env python3
"""
payment-failure-dunning-design.md 4節末尾の「決済成功による復旧通知」を、決済代行
サービスのWebhook(`payment_succeeded`)を直接トリガーとする経路として実装したもの。
フェーズ続き114の`cloud_function_send_dunning_notifications.py`(Cloud Scheduler起動で
検知時・リマインド・制限モード移行の3種類を送る経路)がスコープ外としていた残りの経路。

位置づけ:
- 決済代行サービスとの契約・実際のWebhookエンドポイント公開・Firestore書き込み・LINE
  Push Message APIでの送信は「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち
  (pending-approval.md参照)。本モジュールは実クラウド接続なしで検証可能な「判断・配線
  ロジック自体」のみを実装する。
- 店舗の状態は`cloud_function_send_dunning_notifications.py`の`StoreDunningState`を
  そのまま再利用する(同じstoresドキュメントの同じフィールドを読み書きするため)。

設計上の判断(本モジュールで新たに確定した点):
- 4節末尾は復旧通知の送信条件を「`suspension_reason`が`payment_failed`の場合のみ」と
  していたが、この条件だと猶予期間中(検知通知は届いているが、まだ制限モードに入っていない)に
  決済が成功したケースで通知が一切送られず、検知通知を受け取ったオーナーが解決したか
  分からないまま放置される。かといって復旧文言をそのまま流用すると「新規のご予約受付を
  再開しました」となり、実際には一度も止まっていない受付が止まっていたかのような誤解を
  与える。そのため次の3分岐とし、猶予期間中用の文言を新設した
  (`render_payment_confirmed_in_grace_message()`)。
    1. `suspension_reason == "payment_failed"` → 復旧通知(受付再開を伝える)
    2. 猶予期間中(検知済み)かつdunning通知を1通以上送信済み → 猶予期間中用の完了通知
    3. 猶予期間中だがdunning通知を未送信 → オーナーは決済失敗自体を知らないため通知しない
       (状態のリセットのみ行う)
- dunning中でない店舗の`payment_succeeded`(毎月の正常な課金成功)は通知しない。
  Webhookの再送で復旧通知が二重に届かない冪等性も、状態リセット後は本分岐に落ちることで
  自然に担保される(reminder-scheduler-design.mdの冪等性の考え方と同じく、送信済みかどうかを
  状態そのものから判定する)。
- 送信に失敗した場合は状態を一切変更せずに返す。呼び出し側がHTTP 5xxを返して決済代行
  サービスのWebhookリトライに委ねれば、次の再送で同じ分岐に入り再送信される。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    LinePushClient,
    LinePushDeliveryError,
)
from cloud_function_send_dunning_notifications import StoreDunningState  # noqa: E402
from dunning_notification_scheduler import (  # noqa: E402
    render_payment_confirmed_in_grace_message,
    render_recovery_message,
)

# classify_payment_succeeded()が返す分類。
OUTCOME_RECOVERED_FROM_SUSPENSION = "recovered_from_suspension"
OUTCOME_CONFIRMED_IN_GRACE = "confirmed_in_grace"
OUTCOME_SILENT_RESET = "silent_reset"
OUTCOME_NO_DUNNING = "no_dunning"

# handle_payment_succeeded()のみが返す、送信失敗を表す分類。
OUTCOME_SEND_FAILED = "send_failed"


@dataclass
class PaymentSucceededResult:
    """1回の`payment_succeeded`Webhook処理の結果(呼び出し側のログ・HTTPステータス判断用)。

    outcomeがOUTCOME_SEND_FAILEDの場合、状態は変更されていないため呼び出し側は
    5xxを返してWebhookのリトライに委ねる。
    """

    outcome: str
    notified: bool = False
    state_reset: bool = False


def classify_payment_succeeded(state: StoreDunningState) -> str:
    """店舗の現在の状態から、決済成功時にどの通知経路に該当するかを判定する。"""
    if state.suspension_reason == "payment_failed":
        return OUTCOME_RECOVERED_FROM_SUSPENSION
    if state.payment_failure_detected_at is None:
        return OUTCOME_NO_DUNNING
    if state.sent_event_keys:
        return OUTCOME_CONFIRMED_IN_GRACE
    return OUTCOME_SILENT_RESET


def _clear_dunning_state(state: StoreDunningState) -> None:
    """決済成功を受けてdunning進行状態を初期化する。

    `suspension_reason`は"payment_failed"のときだけ解除する。"trial_unselected"等の
    別要因による休止モード(dormant-mode-renotification-design.md)は決済成功とは無関係の
    ため、ここで解除してしまうと本来止めるべき受付を再開させてしまう。
    """
    state.payment_failure_detected_at = None
    state.sent_event_keys = set()
    if state.suspension_reason == "payment_failed":
        state.suspension_reason = None


def handle_payment_succeeded(
    state: StoreDunningState, push_client: LinePushClient
) -> PaymentSucceededResult:
    """決済代行サービスの`payment_succeeded`Webhook受信時の処理本体。

    引数のstateは呼び出し元でFirestoreから読み取った当該店舗の状態を想定し、
    本関数は必要な通知送信と状態の書き換えを行う(実際のFirestore書き戻しは呼び出し側)。
    """
    outcome = classify_payment_succeeded(state)

    if outcome == OUTCOME_NO_DUNNING:
        return PaymentSucceededResult(outcome=outcome)

    if outcome == OUTCOME_SILENT_RESET:
        _clear_dunning_state(state)
        return PaymentSucceededResult(outcome=outcome, state_reset=True)

    if outcome == OUTCOME_RECOVERED_FROM_SUSPENSION:
        text = render_recovery_message(state.message_tone)
    else:
        text = render_payment_confirmed_in_grace_message(state.message_tone)

    try:
        push_client.send_message(state.owner_line_user_id, text)
    except LinePushDeliveryError:
        return PaymentSucceededResult(outcome=OUTCOME_SEND_FAILED)

    _clear_dunning_state(state)
    return PaymentSucceededResult(outcome=outcome, notified=True, state_reset=True)


def _demo() -> None:
    from datetime import datetime

    from cloud_function_process_event import InMemoryLinePushClient
    from dunning_notification_scheduler import DUNNING_CONFIG_A_7DAYS

    push = InMemoryLinePushClient()
    store = StoreDunningState(
        store_id="store-1",
        owner_line_user_id="owner-line-1",
        payment_failure_detected_at=datetime(2026, 8, 17, 10, 0),
        config=DUNNING_CONFIG_A_7DAYS,
        payment_page_url="https://example.com/billing",
        suspension_reason="payment_failed",
        sent_event_keys={"detected", "reminder:final", "suspended"},
    )

    # 1) 制限モードからの復旧: 受付再開を伝える復旧通知が届き、状態が初期化される。
    print("1回目(制限モードからの復旧):", handle_payment_succeeded(store, push))
    print("  状態:", store.suspension_reason, store.payment_failure_detected_at)

    # 2) Webhook再送: 既に初期化済みのため二重送信されない(冪等性の確認)。
    print("2回目(Webhook再送):", handle_payment_succeeded(store, push))

    # 3) 猶予期間中(検知通知のみ送信済み)の決済成功: 受付再開とは書かない文言を送る。
    in_grace = StoreDunningState(
        store_id="store-2",
        owner_line_user_id="owner-line-2",
        payment_failure_detected_at=datetime(2026, 8, 18, 9, 0),
        config=DUNNING_CONFIG_A_7DAYS,
        payment_page_url="https://example.com/billing",
        sent_event_keys={"detected"},
    )
    print("3回目(猶予期間中の決済成功):", handle_payment_succeeded(in_grace, push))

    print("送信済みログ件数:", len(push.sent))
    for _, text in push.sent:
        print("---")
        print(text)


if __name__ == "__main__":
    _demo()
