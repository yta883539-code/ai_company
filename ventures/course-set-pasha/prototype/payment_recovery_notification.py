#!/usr/bin/env python3
"""
payment-failure-dunning-design.md 4節「決済成功による復旧時(3分岐)」(フェーズ121)の
実送信配線。line-reservation-aiのフェーズ続き115(prototype/cloud_function_payment_webhook.py
`classify_payment_succeeded()`)・aircon-pashaのフェーズ146(prototype/payment_recovery_
notification.py)と同じ考え方を、本venture固有の状態モデルへ翻案したもの。

本ventureとaircon-pashaの違い(移植にあたっての設計判断):
- aircon-pashaは`payment_suspended_at`という保存済みの2値フラグで「既に制限モードへ
  移行済みか」を判定するが、本ventureはpayment-failure-dunning-design.md 3節・
  cloud_function_webhook.py `_is_payment_suspended()`のとおり、別立ての状態フラグを
  持たず「検知時刻(`payment_failure_detected_at`)からの経過日数」を都度算出して
  制限モードか否かを判定する設計を採っている。そのため本モジュールの
  `classify_payment_recovery()`は`payment_suspended_at`の代わりに`now`(イベント受信時刻)を
  引数に取り、`_is_payment_suspended()`と同じ計算式(経過日数 ≧ 猶予期間)で分岐する。
- 本ventureは`payment_failure_reminder_sent_at`が唯一の「送信済み」フラグである点は
  aircon-pashaと同じ(決済失敗検知時〈段階1〉の通知を送る配線がまだ存在しないため)。

位置づけ:
- 実際のStripe Webhook `invoice.payment_succeeded`受信エンドポイントからの呼び出し配線
  (`stripe_webhook.py`の`dispatch_stripe_event()`は現状、通知を送らず状態クリアのみを
  行う実装〈フェーズ119〉のまま)は本モジュールの対象外で次回以降の課題として残る。
  実際のLINE Push Message API接続・決済代行サービスとの契約はオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「決済成功時にどの通知を
  送るべきか(あるいは送らないべきか)」の判定ロジックと、送信・状態リセットの配線を
  実クラウド接続なしで検証可能にしたもの。

設計の参照元: payment-failure-dunning-design.md 4節,
aircon-pasha prototype/payment_recovery_notification.py,
line-reservation-ai prototype/cloud_function_payment_webhook.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Protocol

from cloud_function_webhook import PAYMENT_FAILURE_GRACE_PERIOD_DAYS
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# classify_payment_recovery()が返す分類。line-reservation-ai・aircon-pashaのOUTCOME_*と
# 対称の命名。
OUTCOME_RECOVERED_FROM_SUSPENSION = "recovered_from_suspension"
OUTCOME_CONFIRMED_IN_GRACE = "confirmed_in_grace"
OUTCOME_SILENT_RESET = "silent_reset"
OUTCOME_NO_DUNNING = "no_dunning"

# handle_payment_succeeded()のみが返す、送信失敗を表す分類。
OUTCOME_SEND_FAILED = "send_failed"


def classify_payment_recovery(
    payment_failure_detected_at: Optional[datetime],
    payment_failure_reminder_sent_at: Optional[datetime],
    now: datetime,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
) -> str:
    """`invoice.payment_succeeded`受信時、状態から4種類のいずれに該当するかを判定する。

    本ventureは`payment_suspended_at`のような保存済みフラグを持たないため、
    `_is_payment_suspended()`(cloud_function_webhook.py)と同じ計算式
    (`now - payment_failure_detected_at >= grace_period_days`)で「制限モードからの
    復旧」に該当するかを都度算出する。

    - `payment_failure_detected_at`が未設定 → そもそも決済失敗を検知したことがない
      通常の毎月課金成功。通知不要(OUTCOME_NO_DUNNING)。
    - 検知時刻から猶予期間以上経過している → 制限モード(段階3)からの復旧。
      「再開しました」と案内する。
    - 上記いずれでもなく`payment_failure_reminder_sent_at`が設定済み → 猶予期間中
      (段階2)にリマインドを受け取った後の決済成功。生成は止まっていないため「再開」とは
      書かず「解消されました」と案内する。
    - 上記いずれでもない(検知はされているがリマインド未送信) → 本ventureにはまだ
      当該ユーザーへ届いた通知が(現状の実装上)存在しないため、通知せず状態のみ
      リセットする(OUTCOME_SILENT_RESET)。
    """
    if payment_failure_detected_at is None:
        return OUTCOME_NO_DUNNING
    if (now - payment_failure_detected_at) >= timedelta(days=grace_period_days):
        return OUTCOME_RECOVERED_FROM_SUSPENSION
    if payment_failure_reminder_sent_at is not None:
        return OUTCOME_CONFIRMED_IN_GRACE
    return OUTCOME_SILENT_RESET


# ---------------------------------------------------------------------------
# メッセージ文言(design 4節)
# ---------------------------------------------------------------------------

_TITLE_LINE = "[コースセットパシャッと] お支払いを確認しました"

# design 4節「決済成功による復旧時」分岐1(制限モードから復旧、生成が実際に止まっていた)。
PAYMENT_RECOVERED_MESSAGE = (
    f"{_TITLE_LINE}\n"
    "\n"
    "お支払い手続きが完了しました。ご不便をおかけしました。\n"
    "投稿文の生成を再開しましたので、引き続きよろしくお願いします。"
)

# design 4節分岐2(猶予期間中、生成は止まっていない)専用の文言。「再開しました」ではなく
# 「解消されました」と表現を分ける(実際には止まっていないものを止まっていたかのように
# 書かない配慮、line-reservation-ai・aircon-pashaと同じ考え方)。
PAYMENT_CONFIRMED_IN_GRACE_MESSAGE = (
    f"{_TITLE_LINE}\n"
    "\n"
    "先日ご案内したお支払いに関するご確認事項は解消されました。\n"
    "投稿文の生成は引き続きご利用いただけますので、このままご利用ください。"
)


def build_payment_recovery_message(outcome: str) -> str:
    """OUTCOME_RECOVERED_FROM_SUSPENSION・OUTCOME_CONFIRMED_IN_GRACE以外を渡すとValueErrorを
    送出する(呼び出し側の誤用防止、他ventureの同名関数群と同じ方針)。"""
    if outcome == OUTCOME_RECOVERED_FROM_SUSPENSION:
        return PAYMENT_RECOVERED_MESSAGE
    if outcome == OUTCOME_CONFIRMED_IN_GRACE:
        return PAYMENT_CONFIRMED_IN_GRACE_MESSAGE
    raise ValueError(f"unexpected outcome for message rendering: {outcome!r}")


# ---------------------------------------------------------------------------
# 実送信配線
# ---------------------------------------------------------------------------


class PaymentRecoveryUsageCounterProtocol(Protocol):
    """本モジュールが実際に使う4メソッドのみを要求する最小限のProtocol
    (stripe_webhook.py `PaymentFailureUsageCounterProtocol`と同じ構造的部分型付けの方針)。"""

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        ...

    def get_payment_failure_reminder_sent_at(self, user_id: str) -> Optional[datetime]:
        ...

    def clear_payment_failure_detected_at(self, user_id: str) -> None:
        ...

    def clear_payment_failure_reminder_sent_at(self, user_id: str) -> None:
        ...


@dataclass
class PaymentRecoveryResult:
    """1回の`invoice.payment_succeeded`処理の結果(呼び出し側のログ・HTTPステータス
    判断用、他ventureのPaymentSucceededResult/PaymentRecoveryResultと対称)。

    outcomeがOUTCOME_SEND_FAILEDの場合、状態は変更されていないため呼び出し側は
    5xxを返してWebhookのリトライに委ねる。"""

    outcome: str
    notified: bool = False
    state_reset: bool = False


def handle_payment_succeeded(
    user_id: str,
    usage_counter: PaymentRecoveryUsageCounterProtocol,
    push_client: LinePushClient,
    now: datetime,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
) -> PaymentRecoveryResult:
    """`invoice.payment_succeeded`受信時(`stripe_customer_id → user_id`逆引き後)に呼ぶ
    処理本体。`usage_counter`から現在状態を読み取り、分類・通知・状態クリアまでを行う。

    送信に失敗した場合は状態を一切変更せずにOUTCOME_SEND_FAILEDを返す。呼び出し側が
    HTTP 5xxを返してWebhookリトライに委ねれば、次の再送で同じ分岐に入り再送信される
    (他ventureのhandle_payment_succeeded()と同じ設計)。Webhook再送時は状態クリア済みの
    ためOUTCOME_NO_DUNNINGに落ち、通知が二重に届かない冪等性が状態そのものから自然に
    担保される点も同じ。
    """
    detected_at = usage_counter.get_payment_failure_detected_at(user_id)
    reminder_sent_at = usage_counter.get_payment_failure_reminder_sent_at(user_id)
    outcome = classify_payment_recovery(detected_at, reminder_sent_at, now, grace_period_days)

    if outcome == OUTCOME_NO_DUNNING:
        return PaymentRecoveryResult(outcome=outcome)

    if outcome == OUTCOME_SILENT_RESET:
        usage_counter.clear_payment_failure_detected_at(user_id)
        usage_counter.clear_payment_failure_reminder_sent_at(user_id)
        return PaymentRecoveryResult(outcome=outcome, state_reset=True)

    text = build_payment_recovery_message(outcome)
    try:
        push_client.send_message(user_id, text)
    except LinePushDeliveryError:
        return PaymentRecoveryResult(outcome=OUTCOME_SEND_FAILED)

    usage_counter.clear_payment_failure_detected_at(user_id)
    usage_counter.clear_payment_failure_reminder_sent_at(user_id)
    return PaymentRecoveryResult(outcome=outcome, notified=True, state_reset=True)


def _demo() -> None:
    from cloud_function_webhook import InMemoryUsageCounter
    from trial_end_scheduler import InMemoryLinePushClient

    now = datetime(2026, 8, 29, 1, 0, 0)
    push = InMemoryLinePushClient()

    # 1) 制限モードからの復旧(検知から8日経過): 「再開しました」の案内が届き、状態がクリアされる。
    counter1 = InMemoryUsageCounter()
    counter1.set_payment_failure_detected_at("u1", now - timedelta(days=8))
    print("1) 制限モードからの復旧:", handle_payment_succeeded("u1", counter1, push, now))

    # 2) 猶予期間中(リマインド送信済み、検知から5日経過)の決済成功: 「解消されました」の案内。
    counter2 = InMemoryUsageCounter()
    counter2.set_payment_failure_detected_at("u2", now - timedelta(days=5))
    counter2.set_payment_failure_reminder_sent_at("u2", now - timedelta(days=1))
    print("2) 猶予期間中(リマインド後)の決済成功:", handle_payment_succeeded("u2", counter2, push, now))

    # 3) 猶予期間中(まだ何も送信していない、検知から2日経過)の決済成功: 通知せず状態のみリセット。
    counter3 = InMemoryUsageCounter()
    counter3.set_payment_failure_detected_at("u3", now - timedelta(days=2))
    print("3) 猶予期間中(未通知)の決済成功:", handle_payment_succeeded("u3", counter3, push, now))

    # 4) 決済失敗を検知したことがない通常の課金成功: 何もしない。
    counter4 = InMemoryUsageCounter()
    print("4) 通常の課金成功:", handle_payment_succeeded("u4", counter4, push, now))

    print("送信済みログ件数:", len(push.sent))
    for user_id, text in push.sent:
        print("---", user_id)
        print(text)


if __name__ == "__main__":
    _demo()
