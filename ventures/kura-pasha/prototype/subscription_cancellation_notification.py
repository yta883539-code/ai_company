"""subscription-cancellation-notification-design.md(フェーズ54)の実送信配線。

subscription-cancellation-flow-design.md(フェーズ23)2節で草案のみ存在し、
`stripe_webhook.handle_customer_subscription_deleted()`(フェーズ53)に一切配線
されていなかった「解約確定時の契約者向けLINE通知」を実装する。

course-set-pasha/prototype/subscription_cancellation_notification.py(フェーズ155)と
同じ「文言定数+`render_*()`+`handle_*()`実送信配線」の構成を踏襲するが、本ventureは
契約が`craftsman_workshop/{workshop_id}`単位・支払い名義人は`contractor_user_id`一人に
限定される構造(craftsman-account-linking-design.md)のため、`handle_subscription_
cancelled()`の引数は`user_id`ではなく`workshop_id`とし、関数内部で送信先(契約者本人の
user_id)を解決する(design 3節)。

フェーズ55: `customer.subscription.updated`のcancel_at_period_end前後比較
(subscription-cancellation-scheduled-notification-design.md)による「解約予約受理」
「解約取り消し」通知を追加した。course-set-pashaフェーズ156と異なりPortalLinkProvider
相当の抽象化を本venture側に持たないため、案内メッセージにURL差し込みは行わない
(同design.md 5節)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Protocol

from usage_counter_workshop import WorkshopStoreProtocol

_JST = timezone(timedelta(hours=9))

# design 2節: 「契約終了」「本日以降、3点セットの生成は利用不可」「再開時は新規契約と
# 同じ手続き」の3点を含む。「それまでは引き続きご利用いただけます」という草案の一文は、
# customer.subscription.deleted受信時点では既に契約終了後であり事実と矛盾するため含めない
# (design 1節・2節)。
SUBSCRIPTION_CANCELLED_MESSAGE = (
    "【鞍パシャッと】ご契約終了のご案内\n"
    "\n"
    "ご契約が終了しました。ご利用ありがとうございました。\n"
    "本日以降、受注内容整理メモ・納品案内・お手入れ案内の生成はご利用いただけません。\n"
    "\n"
    "またのご利用をお待ちしております。再開をご希望の際は、いつでも新規契約と\n"
    "同じお手続きでお申し込みいただけます。"
)


def render_subscription_cancelled_message() -> str:
    """design 2節の文言をそのまま返す(日付・URL等の差し込みが無いため引数なし)。"""
    return SUBSCRIPTION_CANCELLED_MESSAGE


class LinePushDeliveryError(Exception):
    """LINE Push Message送信に失敗したことを表す例外(course-set-pashaと同じ位置づけ)。"""


class LinePushClient(Protocol):
    def send_message(self, user_id: str, text: str) -> None:
        ...


class InMemoryLinePushClient:
    """テスト・デモ用の送信記録のみ行うクライアント(実LINE Push API接続はオーナー
    承認待ち、pending-approval.md参照)。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_message(self, user_id: str, text: str) -> None:
        self.sent.append((user_id, text))


@dataclass
class SubscriptionCancelledNotificationResult:
    """1回の`customer.subscription.deleted`通知送信の結果。

    design 4節のとおり、`set_subscription_status(workshop_id, "canceled")`は本結果の
    成否と独立して常に(呼び出し側で)行われる。本モジュール自身は状態を一切保持・変更
    しない(course-set-pashaと同じ方針)。`contractor_user_id`が解決できた場合のみ
    `notified`の判定に意味を持つ。
    """

    notified: bool
    contractor_user_id: str


def handle_subscription_cancelled(
    workshop_id: str,
    workshop_store: WorkshopStoreProtocol,
    push_client: LinePushClient,
) -> SubscriptionCancelledNotificationResult:
    """`customer.subscription.deleted`受信時(`stripe_customer_id → workshop_id`逆引き後)に
    呼ぶ処理本体。design 3節のとおり送信先は契約者本人(`contractor_user_id`)に限定し、
    共同利用者(その他のメンバー)には送らない。送信失敗時も呼び出し側での状態変更
    (`set_subscription_status`)をブロックしない設計のため、本関数自体は例外を外へ
    漏らさず`notified=False`を返すのみで完結する。
    """
    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
    text = render_subscription_cancelled_message()
    try:
        push_client.send_message(contractor_user_id, text)
    except LinePushDeliveryError:
        return SubscriptionCancelledNotificationResult(
            notified=False, contractor_user_id=contractor_user_id
        )
    return SubscriptionCancelledNotificationResult(
        notified=True, contractor_user_id=contractor_user_id
    )


# subscription-cancellation-scheduled-notification-design.md(フェーズ55)4節。
OUTCOME_CANCELLATION_SCHEDULED = "cancellation_scheduled"
OUTCOME_CANCELLATION_RESCHEDULED = "cancellation_rescheduled"
OUTCOME_NO_CHANGE = "no_change"


def classify_cancel_at_period_end_change(before: bool, after: bool) -> str:
    """design 4節。`cancel_at_period_end`の前後比較のみで分類する
    (course-set-pashaと同一、本ventureも決済失敗ダニング相当の別立て状態を
    持たないためガード条件は無い)。"""
    if not before and after:
        return OUTCOME_CANCELLATION_SCHEDULED
    if before and not after:
        return OUTCOME_CANCELLATION_RESCHEDULED
    return OUTCOME_NO_CHANGE


def _format_period_end_date_jst(current_period_end: object) -> Optional[str]:
    """design 3節。`current_period_end`(Unixタイムスタンプ)をJSTの`YYYY-MM-DD`形式へ
    変換する。存在しない・数値でない・bool(intのサブクラス)の場合は`None`を返す
    (安全側フォールバック)。"""
    if not isinstance(current_period_end, (int, float)) or isinstance(current_period_end, bool):
        return None
    return datetime.fromtimestamp(current_period_end, tz=_JST).strftime("%Y-%m-%d")


def render_subscription_cancellation_scheduled_message(period_end_date: Optional[str]) -> str:
    """design 5節「解約予約受理時の案内メッセージ」。`period_end_date`が`None`の場合
    (`_format_period_end_date_jst`のフォールバック)は日付なしの表現に差し替える。
    本venture側にPortalLinkProvider相当の抽象化が無いためURL差し込みは行わない
    (design 5節)。"""
    until_phrase = (
        f"今回の請求期間の終了日({period_end_date})まで"
        if period_end_date is not None
        else "今回の請求期間の終了日まで"
    )
    return (
        "【鞍パシャッと】解約のお手続きを承りました\n"
        "\n"
        f"解約のお手続きを承りました。{until_phrase}は引き続きご利用いただけます。\n"
        "終了日以降は受注内容整理メモ・納品案内・お手入れ案内の生成はご利用いただけません。\n"
        "\n"
        "取り消しをご希望の場合は、終了日より前にこのトークでその旨をお知らせください。\n"
        "\n"
        "またのご利用をお待ちしております。"
    )


SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE = (
    "【鞍パシャッと】解約のお取り消しを承りました\n"
    "\n"
    "解約のお取り消しを承りました。引き続きご利用いただけます。"
)


def render_subscription_cancellation_rescheduled_message() -> str:
    """design 5節の文言をそのまま返す(差し込み情報なし)。"""
    return SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE


@dataclass
class SubscriptionCancellationUpdateResult:
    """1回の`customer.subscription.updated`(cancel_at_period_end変化)処理の結果。
    `outcome`が`OUTCOME_NO_CHANGE`の場合、送信は行われず`notified`は常に`False`。"""

    outcome: str
    contractor_user_id: Optional[str] = None
    notified: bool = False


def handle_subscription_cancellation_update(
    workshop_id: str,
    cancel_at_period_end_before: bool,
    cancel_at_period_end_after: bool,
    current_period_end: object,
    workshop_store: WorkshopStoreProtocol,
    push_client: LinePushClient,
) -> SubscriptionCancellationUpdateResult:
    """design 6節。`stripe_webhook.handle_customer_subscription_updated()`から
    呼ばれる処理本体。design 6節のとおり本イベントは`set_subscription_status`等の状態
    変更を一切伴わない(本関数も状態変更は行わない)。送信先は解約完了通知(フェーズ54)と
    同じく契約者本人(`contractor_user_id`)に限定する。"""
    outcome = classify_cancel_at_period_end_change(
        cancel_at_period_end_before, cancel_at_period_end_after
    )
    if outcome == OUTCOME_NO_CHANGE:
        return SubscriptionCancellationUpdateResult(outcome=outcome)

    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
    if outcome == OUTCOME_CANCELLATION_SCHEDULED:
        text = render_subscription_cancellation_scheduled_message(
            _format_period_end_date_jst(current_period_end)
        )
    else:
        text = render_subscription_cancellation_rescheduled_message()

    try:
        push_client.send_message(contractor_user_id, text)
    except LinePushDeliveryError:
        return SubscriptionCancellationUpdateResult(
            outcome=outcome, contractor_user_id=contractor_user_id, notified=False
        )

    return SubscriptionCancellationUpdateResult(
        outcome=outcome, contractor_user_id=contractor_user_id, notified=True
    )


def _demo() -> None:
    from usage_counter_workshop import InMemoryWorkshopStore

    store = InMemoryWorkshopStore()
    store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])
    push = InMemoryLinePushClient()
    result = handle_subscription_cancelled("w1", store, push)
    print("result:", result)
    for user_id, text in push.sent:
        print("---", user_id)
        print(text)


if __name__ == "__main__":
    _demo()
