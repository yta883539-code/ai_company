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

`customer.subscription.updated`のcancel_at_period_end前後比較(course-set-pashaの
`classify_cancel_at_period_end_change()`相当)は本venture未着手のため対象外
(design 5節、次の課題)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from usage_counter_workshop import WorkshopStoreProtocol

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
