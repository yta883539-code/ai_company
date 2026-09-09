"""payment-failure-dunning-design.md(フェーズ56)の実送信配線。

course-set-pasha/prototype/payment_recovery_notification.pyと同じ「文言定数+
`render_*()`/`classify_*()`+`handle_*()`実送信配線」の構成を踏襲するが、本ventureは
(1)契約が`craftsman_workshop/{workshop_id}`単位・支払い名義人は`contractor_user_id`一人に
限定される構造、(2)PortalLinkProvider相当の抽象化が未実装のためURLを差し込まない、
(3)3日前リマインド送信インフラが本フェーズの対象外(design 6節「残課題」)のため
`payment_failure_reminder_sent_at`相当の状態を持たない、という3点で異なる。(3)の結果、
`classify_payment_recovery()`は他venture3件の3〜4分岐ではなく2分岐(design 4節)に
簡略化している。

`LinePushClient`/`LinePushDeliveryError`は`subscription_cancellation_notification.py`の
ものをそのまま再利用する(モジュールごとに別クラスの例外を定義しない)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from subscription_cancellation_notification import LinePushClient, LinePushDeliveryError
from usage_counter_workshop import PAYMENT_FAILURE_GRACE_PERIOD_DAYS, WorkshopStoreProtocol

# design 4節「決済失敗検知時(猶予期間開始)」。PortalLinkProvider相当が未実装のため、
# 他venture3件と異なりURLは差し込まず「ご利用中の決済手続き時にご案内した画面」という
# 表現に留める(design 1節)。
PAYMENT_FAILURE_DETECTED_MESSAGE = (
    "【鞍パシャッと】お支払いの確認をお願いします\n"
    "\n"
    "いつもご利用ありがとうございます。\n"
    "今回のお支払い手続きが完了できませんでした\n"
    "(カードの有効期限切れ・利用限度額等が考えられます)。\n"
    "\n"
    "現在、受注内容整理メモ・納品案内・お手入れ案内の生成は通常どおりご利用いただけます。\n"
    "7日以内にお支払い方法をご確認・更新いただけますようお願いします\n"
    "(ご利用中の決済手続き時にご案内した画面からご確認いただけます)。"
)


def render_payment_failure_detected_message() -> str:
    """design 4節の文言をそのまま返す(差し込み情報なし)。"""
    return PAYMENT_FAILURE_DETECTED_MESSAGE


@dataclass
class PaymentFailureDetectedResult:
    """1回の`invoice.payment_failed`通知送信の結果。

    design 5節のとおり、`set_subscription_status(workshop_id, "past_due")`・
    `set_payment_failure_detected_at(workshop_id, ...)`は本結果の成否と独立して常に
    (呼び出し側で)行われる。本モジュール自身は状態を一切保持・変更しない
    (subscription_cancellation_notification.pyと同じ方針)。
    """

    notified: bool
    contractor_user_id: str


def handle_payment_failure_detected(
    workshop_id: str,
    workshop_store: WorkshopStoreProtocol,
    push_client: LinePushClient,
) -> PaymentFailureDetectedResult:
    """`invoice.payment_failed`受信時(`stripe_customer_id → workshop_id`逆引き後)に呼ぶ
    処理本体。送信先は契約者本人(`contractor_user_id`)に限定する。送信失敗時も呼び出し側
    での状態変更をブロックしない設計のため、本関数自体は例外を外へ漏らさず`notified=False`を
    返すのみで完結する。
    """
    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
    text = render_payment_failure_detected_message()
    try:
        push_client.send_message(contractor_user_id, text)
    except LinePushDeliveryError:
        return PaymentFailureDetectedResult(
            notified=False, contractor_user_id=contractor_user_id
        )
    return PaymentFailureDetectedResult(notified=True, contractor_user_id=contractor_user_id)


# design 4節「決済成功による復旧時(2分岐)」。他venture3件のOUTCOME_*と対称の命名だが、
# 本ventureは`payment_failure_reminder_sent_at`相当を持たないためOUTCOME_CONFIRMED_IN_GRACE
# (リマインド後の解消)とOUTCOME_SILENT_RESET(リマインド未送信のまま解消)を区別できず、
# 猶予期間中の解消は一律OUTCOME_SILENT_RESETとする(design 4節)。
OUTCOME_RECOVERED_FROM_SUSPENSION = "recovered_from_suspension"
OUTCOME_SILENT_RESET = "silent_reset"
OUTCOME_NOT_APPLICABLE = "not_applicable"


def classify_payment_recovery(
    payment_failure_detected_at: Optional[datetime],
    now: datetime,
    grace_period_days: int = PAYMENT_FAILURE_GRACE_PERIOD_DAYS,
) -> str:
    """`invoice.payment_succeeded`受信時、状態から3種類のいずれに該当するかを判定する。

    - `payment_failure_detected_at`が未設定 → 通常の毎月課金成功(OUTCOME_NOT_APPLICABLE)。
    - 検知時刻から猶予期間(既定7日)以上経過している → 制限モードからの復旧
      (OUTCOME_RECOVERED_FROM_SUSPENSION、「再開しました」と案内する)。
    - 上記いずれでもない(猶予期間中の解消) → 通知せず状態のみリセットする
      (OUTCOME_SILENT_RESET)。
    """
    if payment_failure_detected_at is None:
        return OUTCOME_NOT_APPLICABLE
    if (now - payment_failure_detected_at) >= timedelta(days=grace_period_days):
        return OUTCOME_RECOVERED_FROM_SUSPENSION
    return OUTCOME_SILENT_RESET


PAYMENT_RECOVERED_MESSAGE = (
    "【鞍パシャッと】お支払いを確認しました\n"
    "\n"
    "お支払い手続きが完了しました。ご不便をおかけしました。\n"
    "受注内容整理メモ・納品案内・お手入れ案内の生成を再開しましたので、引き続きよろしく"
    "お願いします。"
)


@dataclass
class PaymentRecoveryResult:
    """1回の`invoice.payment_succeeded`処理の結果。`outcome`が`OUTCOME_SEND_FAILED`の
    場合、状態は変更されていないため呼び出し側は5xxを返してWebhookのリトライに委ねる
    (course-set-pashaのhandle_payment_succeeded()と同じ設計)。
    """

    outcome: str
    contractor_user_id: Optional[str] = None
    notified: bool = False


OUTCOME_SEND_FAILED = "send_failed"


def handle_payment_succeeded(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
    push_client: LinePushClient,
) -> PaymentRecoveryResult:
    """`invoice.payment_succeeded`受信時(`stripe_customer_id → workshop_id`逆引き後)に
    呼ぶ処理本体。`workshop_store`から現在状態を読み取り、分類・通知・状態クリアまでを行う。

    送信に失敗した場合は状態を一切変更せずOUTCOME_SEND_FAILEDを返す(次のWebhook再送で
    同じ分岐に入り再送信される)。Webhook再送時は状態クリア済みのためOUTCOME_NOT_APPLICABLEに
    落ち、通知が二重に届かない冪等性が状態そのものから自然に担保される。
    """
    detected_at = workshop_store.get_payment_failure_detected_at(workshop_id)
    outcome = classify_payment_recovery(detected_at, now)

    if outcome == OUTCOME_NOT_APPLICABLE:
        return PaymentRecoveryResult(outcome=outcome)

    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)

    if outcome == OUTCOME_SILENT_RESET:
        workshop_store.clear_payment_failure_detected_at(workshop_id)
        return PaymentRecoveryResult(outcome=outcome, contractor_user_id=contractor_user_id)

    try:
        push_client.send_message(contractor_user_id, PAYMENT_RECOVERED_MESSAGE)
    except LinePushDeliveryError:
        return PaymentRecoveryResult(outcome=OUTCOME_SEND_FAILED, contractor_user_id=contractor_user_id)

    workshop_store.clear_payment_failure_detected_at(workshop_id)
    return PaymentRecoveryResult(
        outcome=outcome, contractor_user_id=contractor_user_id, notified=True
    )


def _demo() -> None:
    from datetime import timezone

    from usage_counter_workshop import InMemoryWorkshopStore

    store = InMemoryWorkshopStore()
    store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])

    class _StubPushClient:
        def __init__(self) -> None:
            self.sent: list[tuple[str, str]] = []

        def send_message(self, user_id: str, text: str) -> None:
            self.sent.append((user_id, text))

    push = _StubPushClient()
    detected_result = handle_payment_failure_detected("w1", store, push)
    print("detected:", detected_result)

    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    store.set_payment_failure_detected_at("w1", now - timedelta(days=8))
    recovery_result = handle_payment_succeeded("w1", now, store, push)
    print("recovery:", recovery_result)
    for user_id, text in push.sent:
        print("---", user_id)
        print(text)


if __name__ == "__main__":
    _demo()
