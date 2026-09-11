#!/usr/bin/env python3
"""
blocked-but-billing-owner-notification-design.md(フェーズ81)で設計した、
`list_blocked_but_billing_candidates()`(フェーズ80)が洗い出した候補workshop_idを
実際にオーナー(運営者)へLINE Pushで届けるバッチ(Cloud Function相当)を実装したもの。

位置づけ:
- 実際のオーナーLINEユーザーIDの取得・設定、実LINE Push Message APIでの送信はオーナー
  承認待ち(README.md「実LINE公式アカウント接続」の記載範囲に含まれる、新規の承認待ち
  事項ではない)。本モジュールはそれとは別に、「候補一覧のうちどのworkshop_idを新規に
  通知すべきか」の判定ロジック(design 4節)と、「実際に送るメッセージの整形・送信・
  冪等性のための書き込み」の配線を実クラウド接続なしで検証可能にしたもの
  (aircon-pasha/course-set-pashaのblocked_but_billing_owner_notification.pyと同じ位置づけ)。
- aircon-pasha版はuser_id単位・Flex Messageだが、本ventureは契約単位がworkshopであり
  `list_blocked_but_billing_candidates()`の返り値もworkshop_id(blocked_but_billing_
  candidates.py参照)であるため、本モジュールも一貫してworkshop_id単位で扱う。送信文言の
  組み立てにあたっては`workshop_store.get_contractor_user_id()`で契約者user_idを引き直す。
- 本venture一貫の`LinePushClient`(subscription_cancellation_notification.py)は
  プレーンテキストの`send_message(user_id, text)`のみを提供する(course-set-pasha方式)。
  aircon-pashaのようなFlex Message専用クライアントではないため、本モジュールもプレーン
  テキストを組み立てる。`LinePushClient`・`LinePushDeliveryError`は
  subscription_cancellation_notification.pyで既に定義済みのものをそのまま再利用し、
  本モジュールで重複定義しない。
- `clear_blocked_but_billing_owner_notified_at()`(design 6節「クリア配線」)は、
  「フォロー再開」(契約者本人のis_followingがTrueに戻る)・「解約確定」
  (customer.subscription.deleted受信でsubscription_statusが"canceled"になる)の
  いずれかが起きた時点で`blocked_but_billing_owner_notified_at`をクリアする純粋関数。
  呼び出し配線自体は本モジュールの対象外で、`cloud_function_webhook.process_follow_
  event()`(フォロー再開)・`stripe_webhook.handle_customer_subscription_deleted()`
  (解約確定)の両方から呼ばれる。

設計の参照元: blocked-but-billing-owner-notification-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, Sequence

from subscription_cancellation_notification import LinePushClient, LinePushDeliveryError

# design 1節: 他venture3件と同じ考え方のプレースホルダ。実値は実LINE API接続後に
# 設定値として差し込む。
OWNER_LINE_USER_ID_PLACEHOLDER = "{オーナーLINEユーザーID}"


class BlockedButBillingOwnerNotifiedAtReader(Protocol):
    """design 4節の抽出条件が参照する`blocked_but_billing_owner_notified_at`の
    読み出しのみを要求する最小限のProtocol。"""

    def get_blocked_but_billing_owner_notified_at(self, workshop_id: str) -> Optional[datetime]:
        ...


class BlockedButBillingOwnerNotifiedAtWriter(Protocol):
    """design 4節「送信成功時のみ書き込む」が使う書き込み専用のProtocol。design 6節の
    クリア配線は同じメソッドに`None`を渡すことで表現する(trial_end_notified_at方式とは
    異なり本フィールドは1メソッドでset/clear両方を表現する、usage_counter_workshop.py参照)。
    """

    def set_blocked_but_billing_owner_notified_at(
        self, workshop_id: str, notified_at: Optional[datetime]
    ) -> None:
        ...


class BlockedButBillingOwnerNotifiedAtStoreProtocol(
    BlockedButBillingOwnerNotifiedAtReader, BlockedButBillingOwnerNotifiedAtWriter, Protocol
):
    """design 6節「クリア配線」が使う、読み書き両方を要求する合成Protocol。
    `usage_counter_workshop.WorkshopStoreProtocol`(ひいては`InMemoryWorkshopStore`)は
    これらのメソッドを既に持つため、構造的に(duck typing)本Protocolを満たす。
    """


def select_new_blocked_but_billing_candidates_for_notification(
    candidate_workshop_ids: Sequence[str],
    notified_at_reader: BlockedButBillingOwnerNotifiedAtReader,
) -> list[str]:
    """blocked-but-billing-owner-notification-design.md 4節の抽出条件をそのままコード化した
    もの。

    candidate_workshop_idsは`list_blocked_but_billing_candidates()`が返した「現時点の
    全候補」を想定する。このうち`blocked_but_billing_owner_notified_at`が未設定(=まだ
    一度もオーナーへ通知していない)workshop_idのみを、入力順を維持したまま返す
    (1候補=1回のみ通知、digest形式は採らない)。
    """
    return [
        workshop_id
        for workshop_id in candidate_workshop_ids
        if notified_at_reader.get_blocked_but_billing_owner_notified_at(workshop_id) is None
    ]


def clear_blocked_but_billing_owner_notified_at(
    store: BlockedButBillingOwnerNotifiedAtStoreProtocol, workshop_id: str,
) -> bool:
    """design 6節「クリア配線」: 「フォロー再開」(契約者本人のis_followingがTrueに戻る)、
    または「解約確定」(customer.subscription.deleted受信でsubscription_statusが
    "canceled"になる)のいずれかが起きた時点で呼ぶ。`blocked_but_billing_owner_
    notified_at`が設定済みの場合のみクリアし、変更があったかどうか(True/False)を返す
    (aircon-pasha版と同じ、呼び出し側がログ確認できる冪等設計)。未設定(そもそも一度も
    通知対象になったことがない、または既にクリア済み)の場合は何もせず`False`を返す。

    呼び出し配線自体は本関数の対象外で、`cloud_function_webhook.process_follow_event()`
    (フォロー再開)・`stripe_webhook.handle_customer_subscription_deleted()`
    (解約確定)の両方から呼ばれる。
    """
    if store.get_blocked_but_billing_owner_notified_at(workshop_id) is None:
        return False
    store.set_blocked_but_billing_owner_notified_at(workshop_id, None)
    return True


# ---------------------------------------------------------------------------
# メッセージ整形(design 2節)
# ---------------------------------------------------------------------------


def build_blocked_but_billing_owner_notification_message(contractor_user_id: str) -> str:
    """design 2節: 本venture一貫のプレーンテキスト形式(SUBSCRIPTION_CANCELLED_MESSAGE等と
    同じ、subscription_cancellation_notification.pyの文言スタイルを踏襲)でオーナー通知文を
    組み立てる。
    """
    return (
        "【鞍パシャッと運営】ブロック中かつ契約継続中のお知らせ\n"
        "\n"
        "以下の契約者がLINEをブロックしていますが、Stripeでの契約(決済)は継続中です。\n"
        f"契約者ID: {contractor_user_id}\n"
        "\n"
        "必要に応じて契約者への個別フォロー(再フォローのお願い・解約意向の確認等)を"
        "ご検討ください。"
    )


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function本体)
# ---------------------------------------------------------------------------


@dataclass
class SendBlockedButBillingOwnerNotificationsResult:
    """1回のCloud Function起動での送信結果(呼び出し側のログ・監視用、
    aircon-pasha版SendBlockedButBillingOwnerNotificationsResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # workshop_id
    failed: list[str] = field(default_factory=list)  # workshop_id(送信失敗、次回起動時に再試行)


class BlockedButBillingContractorResolver(Protocol):
    """送信文言に差し込む契約者user_idを解決するための最小限のProtocol
    (`usage_counter_workshop.WorkshopStoreProtocol`はこれを既に満たす)。"""

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...


def send_blocked_but_billing_owner_notifications(
    candidate_workshop_ids: Sequence[str],
    now: datetime,
    notified_at_store: BlockedButBillingOwnerNotifiedAtStoreProtocol,
    push_client: LinePushClient,
    contractor_resolver: BlockedButBillingContractorResolver,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> SendBlockedButBillingOwnerNotificationsResult:
    """blocked-but-billing-owner-notification-design.md 3〜4節「Cloud Function」本体。

    candidate_workshop_idsは呼び出し元が`list_blocked_but_billing_candidates()`
    (blocked_but_billing_candidates.py、フェーズ80)を呼んだ結果を想定する。新規通知対象の
    絞り込みはselect_new_blocked_but_billing_candidates_for_notification()が行う。

    送信先は契約者ごとのuser_idではなく固定のowner_line_user_id(design 1節)。送信成功時
    のみnotified_at_store.set_blocked_but_billing_owner_notified_at()を対象workshop_idに
    対して書き込み、送信失敗時は書き込まない(subscription_cancellation_notification.pyの
    既存通知群と同じ「書き込み一発+次回実行時に自然に再試行対象として残る」方式)。
    """
    result = SendBlockedButBillingOwnerNotificationsResult()

    for workshop_id in select_new_blocked_but_billing_candidates_for_notification(
        candidate_workshop_ids, notified_at_store
    ):
        contractor_user_id = contractor_resolver.get_contractor_user_id(workshop_id)
        text = build_blocked_but_billing_owner_notification_message(contractor_user_id)
        try:
            push_client.send_message(owner_line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append(workshop_id)
            continue
        notified_at_store.set_blocked_but_billing_owner_notified_at(workshop_id, now)
        result.sent.append(workshop_id)

    return result


def _demo() -> None:
    from subscription_cancellation_notification import InMemoryLinePushClient

    now = datetime(2026, 9, 11, 6, 0, 0)
    candidate_workshop_ids = ["w1", "w2", "w3"]

    class _NotifiedAtStub:
        def __init__(self) -> None:
            # w2は既に通知済みという想定(再通知しないことを確認するため)。
            self.notified_at: dict[str, datetime] = {"w2": datetime(2026, 9, 10, 18, 0, 0)}

        def get_blocked_but_billing_owner_notified_at(
            self, workshop_id: str
        ) -> Optional[datetime]:
            return self.notified_at.get(workshop_id)

        def set_blocked_but_billing_owner_notified_at(
            self, workshop_id: str, notified_at: Optional[datetime]
        ) -> None:
            if notified_at is None:
                self.notified_at.pop(workshop_id, None)
            else:
                self.notified_at[workshop_id] = notified_at

    class _ContractorResolverStub:
        def get_contractor_user_id(self, workshop_id: str) -> str:
            return f"contractor-of-{workshop_id}"

    store = _NotifiedAtStub()
    push = InMemoryLinePushClient()
    result = send_blocked_but_billing_owner_notifications(
        candidate_workshop_ids, now, store, push, _ContractorResolverStub()
    )
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
