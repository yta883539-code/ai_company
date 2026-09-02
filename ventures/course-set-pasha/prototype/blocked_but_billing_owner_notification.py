#!/usr/bin/env python3
"""
blocked-but-billing-owner-notification-design.md(フェーズ143)で設計した、
`list_blocked_but_billing_candidates()`(フェーズ142)が洗い出した候補user_idを
実際にオーナー(運営者)へLINE Pushで届けるバッチ(Cloud Function G相当)を実装したもの。

位置づけ:
- 実際のオーナーLINEユーザーIDの取得・設定、実LINE Push Message APIでの送信は
  オーナー承認待ち(README.md「実LLM呼び出し・実LINE API接続」の記載範囲に含まれる、
  新規の承認待ち事項ではない)。本モジュールはそれとは別に、「候補一覧のうちどのuser_idを
  新規に通知すべきか」の判定ロジック(design 3節)と、「実際に送るメッセージの整形・送信・
  冪等性のための書き込み」の配線を実クラウド接続なしで検証可能にしたもの
  (payment_suspension_owner_notification.pyと同じ位置づけ)。
- LinePushClient・LinePushDeliveryErrorはtrial_end_scheduler.pyで既に定義済みのものを
  そのまま再利用する(本モジュールで重複定義しない)。送信先は顧客ごとのuser_idではなく
  固定のオーナー1件であるため、send_message()に渡すidはOWNER_LINE_USER_ID_PLACEHOLDERで
  固定する。

設計の参照元: blocked-but-billing-owner-notification-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, Sequence

from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# design 1節: payment-suspension-owner-notification-design.mdと同じ考え方の
# プレースホルダ。実値は実LINE API接続後に設定値として差し込む。
OWNER_LINE_USER_ID_PLACEHOLDER = "{オーナーLINEユーザーID}"


class BlockedButBillingOwnerNotifiedAtReader(Protocol):
    """design 3節の抽出条件が参照する`blocked_but_billing_owner_notified_at`の
    読み出しのみを要求する最小限のProtocol。"""

    def get_blocked_but_billing_owner_notified_at(self, user_id: str) -> Optional[datetime]:
        ...


class BlockedButBillingOwnerNotifiedAtWriter(Protocol):
    """design 3節「送信成功時のみ書き込む」が使う書き込み専用のProtocol
    (payment_suspension_owner_notification.PaymentSuspensionOwnerNotifiedAtWriterと
    同じ考え方)。"""

    def set_blocked_but_billing_owner_notified_at(self, user_id: str, notified_at: datetime) -> None:
        ...


def select_new_blocked_but_billing_candidates_for_notification(
    candidate_user_ids: Sequence[str],
    notified_at_reader: BlockedButBillingOwnerNotifiedAtReader,
) -> list[str]:
    """blocked-but-billing-owner-notification-design.md 3節の抽出条件をそのままコード化した
    もの。

    candidate_user_idsは`list_blocked_but_billing_candidates()`が返した「現時点の全候補」を
    想定する。このうち`blocked_but_billing_owner_notified_at`が未設定(=まだ一度もオーナーへ
    通知していない)user_idのみを、入力順を維持したまま返す(1候補=1回のみ通知、digest形式は
    採らない)。
    """
    return [
        user_id
        for user_id in candidate_user_ids
        if notified_at_reader.get_blocked_but_billing_owner_notified_at(user_id) is None
    ]


# ---------------------------------------------------------------------------
# メッセージ整形(design 5節)
# ---------------------------------------------------------------------------

BLOCKED_BUT_BILLING_OWNER_NOTIFICATION_TEMPLATE = (
    "[コースセットパシャッと運営] ブロック中かつ契約継続中のお知らせ\n"
    "\n"
    "以下の顧客がLINEをブロックしていますが、Stripeでの契約(決済)は継続中です。\n"
    "\n"
    "顧客ID: {user_id}\n"
    "\n"
    "必要に応じて顧客への個別フォロー(再フォローのお願い・解約意向の確認等)をご検討ください。"
)


def format_blocked_but_billing_owner_notification_message(user_id: str) -> str:
    """design 5節の文言を、顧客ごとの`user_id`を埋め込んで組み立てる。"""
    return BLOCKED_BUT_BILLING_OWNER_NOTIFICATION_TEMPLATE.format(user_id=user_id)


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function G本体)
# ---------------------------------------------------------------------------


@dataclass
class SendBlockedButBillingOwnerNotificationsResult:
    """1回のCloud Function G起動での送信結果(呼び出し側のログ・監視用、
    SendPaymentSuspensionOwnerNotificationsResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id(顧客側の識別子)
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_blocked_but_billing_owner_notifications(
    candidate_user_ids: Sequence[str],
    now: datetime,
    notified_at_store: (
        BlockedButBillingOwnerNotifiedAtReader
        # 読み書き両方を1つのストアで担う想定(user_profileドキュメント、design 3節)。
        # Protocolの合成をタプルで表現できないため、実引数側で両方を満たすオブジェクトを渡す。
    ),
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> SendBlockedButBillingOwnerNotificationsResult:
    """blocked-but-billing-owner-notification-design.md 2〜3節「Cloud Function G」本体。

    candidate_user_idsは呼び出し元が`list_blocked_but_billing_candidates()`
    (blocked_but_billing_candidates.py、フェーズ142)を呼んだ結果を想定する。新規通知対象の
    絞り込みはselect_new_blocked_but_billing_candidates_for_notification()が行う。

    送信先は顧客ごとのuser_idではなく固定のowner_line_user_id(design 1節)。送信成功時のみ
    notified_at_store.set_blocked_but_billing_owner_notified_at()を対象顧客のuser_idに
    対して書き込み、送信失敗時は書き込まない(payment_suspension_owner_notification.pyの
    send_payment_suspension_owner_notifications()と同じ「書き込み一発+次回実行時に自然に
    再試行対象として残る」方式)。
    """
    result = SendBlockedButBillingOwnerNotificationsResult()

    for user_id in select_new_blocked_but_billing_candidates_for_notification(
        candidate_user_ids, notified_at_store
    ):
        text = format_blocked_but_billing_owner_notification_message(user_id)
        try:
            push_client.send_message(owner_line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append(user_id)
            continue
        notified_at_store.set_blocked_but_billing_owner_notified_at(user_id, now)
        result.sent.append(user_id)

    return result


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    now = datetime(2026, 9, 2, 6, 0, 0)
    candidate_user_ids = ["u1", "u2", "u3"]

    class _NotifiedAtStub:
        def __init__(self) -> None:
            # u2は既に通知済みという想定(再通知しないことを確認するため)。
            self.notified_at: dict[str, datetime] = {"u2": datetime(2026, 9, 1, 6, 0, 0)}

        def get_blocked_but_billing_owner_notified_at(self, user_id: str) -> Optional[datetime]:
            return self.notified_at.get(user_id)

        def set_blocked_but_billing_owner_notified_at(
            self, user_id: str, notified_at: datetime
        ) -> None:
            self.notified_at[user_id] = notified_at

    store = _NotifiedAtStub()
    push = InMemoryLinePushClient()
    result = send_blocked_but_billing_owner_notifications(candidate_user_ids, now, store, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
