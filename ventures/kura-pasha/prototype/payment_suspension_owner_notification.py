#!/usr/bin/env python3
"""
payment-suspension-owner-notification-design.md(フェーズ116)で設計した、決済失敗の猶予期間
(PAYMENT_FAILURE_GRACE_PERIOD_DAYS)を超えて制限モードへ移行したworkshopを検知し、
オーナー(運営者)へLINE Pushで能動的に知らせるバッチ(Cloud Function相当)を実装したもの。

位置づけ:
- payment-failure-dunning-design.md「残課題」(フェーズ56)・README.mdフェーズ115時点まで
  残っていた「運営者向け通知(course-set-pasha/payment-suspension-owner-notification-
  design.md相当)は本venture側に運営者向け通知の送信先・仕組み自体がまだ無いため次の課題」
  に対応する。
- course-set-pasha版は`_is_payment_suspended()`の都度算出方式のみで検知フラグを持たず、
  本venture一貫の`is_payment_suspended()`(usage_counter_workshop.py、フェーズ56)と同じ
  都度算出方式をそのまま利用できる。候補workshop_idの洗い出しは
  `blocked_but_billing_candidates.list_blocked_but_billing_candidates()`のような別ファイルを
  新設せず、本モジュール内の`select_due_payment_suspension_owner_notifications()`一本で
  「全workshop走査→制限モード判定→未通知判定」まで完結させる(判定に必要な情報
  〈payment_failure_detected_at・払込猶予日数・通知済み時刻〉がいずれも`WorkshopStoreProtocol`
  1つに揃っているため、blocked-but-billingのように検知用ストア〈profile_store〉と通知用ストアを
  分ける必要が無い)。
- 実際のオーナーLINEユーザーIDの取得・設定、実LINE Push Message APIでの送信はオーナー
  承認待ち(README.md「実LINE公式アカウント接続」の記載範囲に含まれる、新規の承認待ち
  事項ではない)。本モジュールはそれとは別に、判定ロジックと実クラウド接続なしで検証可能な
  送信配線のみを実装する(blocked_but_billing_owner_notification.pyと同じ位置づけ)。
- 本venture一貫の`LinePushClient`(subscription_cancellation_notification.py)は
  プレーンテキストの`send_message(user_id, text)`のみを提供するため、本モジュールも
  course-set-pasha版のプレーンテキスト文言方式を踏襲する。
- クリア配線(design 6節)は本モジュールに新設しない。`usage_counter_workshop.
  InMemoryWorkshopStore.clear_payment_failure_detected_at()`が
  `payment_suspension_owner_notified_at`もあわせてクリアするように既に改修済み
  (payment_failure_reminder_sent_atを同じ関数内でクリアしている既存方針の踏襲)のため、
  `payment_failure_notification.handle_payment_succeeded()`からの呼び出しを変更する必要が
  無い。

設計の参照元: payment-suspension-owner-notification-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Protocol

from subscription_cancellation_notification import LinePushClient, LinePushDeliveryError
from usage_counter_workshop import is_payment_suspended

# design 1節: 他モジュール(blocked_but_billing_owner_notification.py等)と同じ
# プレースホルダの考え方。実値は実LINE API接続後に設定値として差し込む。
OWNER_LINE_USER_ID_PLACEHOLDER = "{オーナーLINEユーザーID}"


class PaymentSuspensionOwnerNotificationWorkshopStoreProtocol(Protocol):
    """design 3〜5節が参照するメソッドのみを要求する最小限のProtocol。
    `usage_counter_workshop.WorkshopStoreProtocol`(ひいては`InMemoryWorkshopStore`)は
    これらを既に持つため、構造的に(duck typing)本Protocolを満たす。
    """

    def all_workshop_ids(self):
        ...

    def get_payment_failure_detected_at(self, workshop_id: str):
        ...

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...

    def get_payment_suspension_owner_notified_at(self, workshop_id: str):
        ...

    def set_payment_suspension_owner_notified_at(self, workshop_id: str, notified_at) -> None:
        ...


def select_due_payment_suspension_owner_notifications(
    now: datetime,
    workshop_store: PaymentSuspensionOwnerNotificationWorkshopStoreProtocol,
) -> List[str]:
    """design 3節の抽出条件をそのままコード化したもの。以下すべてを満たすworkshop_idのみを
    workshop_id昇順で返す(呼び出し順の非決定性を避けるため、list_blocked_but_billing_
    candidates()と同じ方針)。

    - `is_payment_suspended(workshop_id, now, workshop_store)`が真
      (payment_failure_detected_atが設定済み、かつ検知時刻からPAYMENT_FAILURE_GRACE_
      PERIOD_DAYS以上経過している=既に制限モードへ移行済み)
    - `payment_suspension_owner_notified_at`が未設定(1回のみ送信。日次実行の重複・遅延に
      対しても再送されない)
    """
    return sorted(
        workshop_id
        for workshop_id in workshop_store.all_workshop_ids()
        if is_payment_suspended(workshop_id, now, workshop_store)
        and workshop_store.get_payment_suspension_owner_notified_at(workshop_id) is None
    )


def build_payment_suspension_owner_notification_message(
    contractor_user_id: str, elapsed_days: int
) -> str:
    """design 4節: 顧客(契約者)ごとに内容が変わる管理者向け通知文言を組み立てる。
    course-set-pasha版と同じく契約者識別子・検知からの経過日数を埋め込む。
    """
    return (
        "【鞍パシャッと運営】制限モード移行のお知らせ\n"
        "\n"
        "以下の契約者が決済失敗の猶予期間を超え、受注内容整理メモ・納品案内・お手入れ案内の"
        "生成の制限モードへ移行しました。\n"
        "\n"
        f"契約者ID: {contractor_user_id}\n"
        f"決済失敗検知からの経過日数: {elapsed_days}日\n"
        "\n"
        "必要に応じて契約者への個別フォロー(お支払い方法のご案内等)をご検討ください。"
    )


@dataclass
class SendPaymentSuspensionOwnerNotificationsResult:
    """1回のCloud Function起動での送信結果(呼び出し側のログ・監視用、
    blocked_but_billing_owner_notification版のResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # workshop_id
    failed: list[str] = field(default_factory=list)  # workshop_id(送信失敗、次回起動時に再試行)


def send_payment_suspension_owner_notifications(
    now: datetime,
    workshop_store: PaymentSuspensionOwnerNotificationWorkshopStoreProtocol,
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> SendPaymentSuspensionOwnerNotificationsResult:
    """payment-suspension-owner-notification-design.md 3〜5節「Cloud Function」本体。

    送信先は契約者ごとのuser_idではなく固定のowner_line_user_id(design 2節)。送信成功時
    のみ`workshop_store.set_payment_suspension_owner_notified_at()`を対象workshop_idに
    対して書き込み、送信失敗時は書き込まない(blocked_but_billing_owner_notification.pyと
    同じ「書き込み一発+次回実行時に自然に再試行対象として残る」方式)。
    """
    result = SendPaymentSuspensionOwnerNotificationsResult()

    for workshop_id in select_due_payment_suspension_owner_notifications(now, workshop_store):
        contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
        detected_at = workshop_store.get_payment_failure_detected_at(workshop_id)
        elapsed_days = (now - detected_at).days
        text = build_payment_suspension_owner_notification_message(
            contractor_user_id, elapsed_days
        )
        try:
            push_client.send_message(owner_line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append(workshop_id)
            continue
        workshop_store.set_payment_suspension_owner_notified_at(workshop_id, now)
        result.sent.append(workshop_id)

    return result


def _demo() -> None:
    from subscription_cancellation_notification import InMemoryLinePushClient
    from usage_counter_workshop import InMemoryWorkshopStore

    now = datetime(2026, 9, 14, 10, 0, 0)
    store = InMemoryWorkshopStore()
    store.set_members("w1", contractor_user_id="u1", member_user_ids=["u1"])
    store.set_members("w2", contractor_user_id="u2", member_user_ids=["u2"])
    store.set_payment_failure_detected_at("w1", datetime(2026, 9, 5, 10, 0, 0))  # 9日経過
    store.set_payment_failure_detected_at("w2", datetime(2026, 9, 10, 10, 0, 0))  # 4日経過(猶予期間中)

    push = InMemoryLinePushClient()
    result = send_payment_suspension_owner_notifications(now, store, push)
    print(f"sent={result.sent}, failed={result.failed}")
    for recipient, text in push.sent:
        print("---", recipient)
        print(text)


if __name__ == "__main__":
    _demo()
