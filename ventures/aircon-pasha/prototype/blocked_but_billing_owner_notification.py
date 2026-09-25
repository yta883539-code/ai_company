#!/usr/bin/env python3
"""
blocked-but-billing-owner-notification-design.md(フェーズ174)で設計した、
`list_blocked_but_billing_candidates()`(フェーズ167)が洗い出した候補user_idを
実際にオーナー(運営者)へLINE Pushで届けるバッチ(Cloud Function G相当)を実装したもの。

位置づけ:
- 実際のオーナーLINEユーザーIDの取得・設定、実LINE Push Message APIでの送信は
  オーナー承認待ち(README.md「実LLM呼び出し・実LINE API接続」の記載範囲に含まれる、
  新規の承認待ち事項ではない)。本モジュールはそれとは別に、「候補一覧のうちどのuser_idを
  新規に通知すべきか」の判定ロジック(design 4節)と、「実際に送るメッセージの整形・送信・
  冪等性のための書き込み」の配線を実クラウド接続なしで検証可能にしたもの
  (course-set-pasha/prototype/blocked_but_billing_owner_notification.pyと同じ位置づけ)。
- 本venture一貫の`LinePushClient`(trial_end_scheduler.py)はプレーンテキストではなく
  Flex Message(`send_flex_message(user_id, alt_text, contents)`)のみを提供するため、
  course-set-pasha版のようにプレーンテキストは送らず、ボタンを持たないシンプルな
  bubble形式のFlex Messageを組み立てる(design 2節)。LinePushClient・
  LinePushDeliveryErrorはtrial_end_scheduler.pyで既に定義済みのものをそのまま再利用する
  (本モジュールで重複定義しない)。送信先は顧客ごとのuser_idではなく固定のオーナー1件で
  あるため、send_flex_message()に渡すidはOWNER_LINE_USER_ID_PLACEHOLDERで固定する。
- `clear_blocked_but_billing_owner_notified_at()`(design 6節「クリア配線」、フェーズ175
  追加)は、フェーズ174時点で未実装のまま残っていた「フォロー再開」・「解約確定」時の
  `blocked_but_billing_owner_notified_at`クリア処理をpayment_failure.py
  `clear_payment_failure_on_success()`と同じ「設定済みの場合のみクリアしTrue/Falseを
  返す」形の純粋関数として実装したもの。呼び出し配線自体は本モジュールの対象外で、
  `cloud_function_webhook.process_follow_event()`(フォロー再開)・`stripe_dispatch.
  dispatch_stripe_event()`の`customer.subscription.deleted`分岐(解約確定)の両方から
  呼ばれる(course-set-pashaのフェーズ144相当)。
- `business_name`併記対応(フェーズ263、business-name-owner-notification-display-
  design.md 5節「今後の課題」への対応)は、`build_blocked_but_billing_owner_notification_
  flex_message()`に`business_name: Optional[str] = None`引数を追加し、
  `_format_customer_identifier_line()`が business_name設定時「顧客名: {business_name}
  (ID: {user_id})」・未設定時は従来通り「顧客ID: {user_id}」のみを組み立てる形で対応した
  (payment_suspension_owner_notification.pyの`_format_business_identifier_line()`と
  同じ考え方、本モジュールの既存文言「顧客ID:」を踏襲し「業者名/業者ID」ではなく
  「顧客名/顧客ID」の表記を採用)。`send_blocked_but_billing_owner_notifications()`には
  新規Protocol`BlockedButBillingBusinessNameReader`を受け取る省略可能引数
  `business_name_reader: Optional[...] = None`を追加し、未指定時は全件business_name
  未設定(従来通りの`user_id`のみの表示)として動作するため後方互換を維持する。実際の
  Firestore配線(`UserProfileStoreProtocol`への`get_business_name`追加・
  `cloud_function_webhook.py`からの実結線)はまだ実装されていない(payment_suspension版と
  同じく、design 4節の通りFirestore接続自体がオーナー承認待ちの範囲であるため)。

設計の参照元: blocked-but-billing-owner-notification-design.md,
business-name-owner-notification-display-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, Sequence

from trial_end_scheduler import LinePushClient, LinePushDeliveryError

# design 1節: course-set-pashaのpayment-suspension-owner-notification-design.mdと
# 同じ考え方のプレースホルダ。実値は実LINE API接続後に設定値として差し込む。
OWNER_LINE_USER_ID_PLACEHOLDER = "{オーナーLINEユーザーID}"

BLOCKED_BUT_BILLING_OWNER_NOTIFICATION_ALT_TEXT = (
    "[エアコンパシャッと運営] ブロック中かつ契約継続中のお知らせ"
)


class BlockedButBillingOwnerNotifiedAtReader(Protocol):
    """design 4節の抽出条件が参照する`blocked_but_billing_owner_notified_at`の
    読み出しのみを要求する最小限のProtocol。"""

    def get_blocked_but_billing_owner_notified_at(self, user_id: str) -> Optional[datetime]:
        ...


class BlockedButBillingOwnerNotifiedAtWriter(Protocol):
    """design 4節「送信成功時のみ書き込む」が使う書き込み専用のProtocol
    (course-set-pasha版と同じ考え方)。design 6節のクリア配線(フェーズ175)は同じ
    メソッドに`None`を渡すことで表現する(payment_failure.pyのset_payment_failure_
    detected_at等、本venture一貫の「クリアも同じsetterで表現する」方針を踏襲)。"""

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        ...


class BlockedButBillingBusinessNameReader(Protocol):
    """business-name-owner-notification-display-design.md 5節への対応(フェーズ263)。
    メッセージ整形時に業者(顧客)のbusiness_nameを引くための、読み出しのみを要求する
    最小限のProtocol(他のReader Protocolと同じ考え方)。"""

    def get_business_name(self, user_id: str) -> Optional[str]:
        ...


class BlockedButBillingOwnerNotifiedAtStoreProtocol(
    BlockedButBillingOwnerNotifiedAtReader, BlockedButBillingOwnerNotifiedAtWriter, Protocol
):
    """design 6節「クリア配線」(フェーズ175)が使う、読み書き両方を要求する合成Protocol。"""


def select_new_blocked_but_billing_candidates_for_notification(
    candidate_user_ids: Sequence[str],
    notified_at_reader: BlockedButBillingOwnerNotifiedAtReader,
) -> list[str]:
    """blocked-but-billing-owner-notification-design.md 4節の抽出条件をそのままコード化した
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


def clear_blocked_but_billing_owner_notified_at(
    store: BlockedButBillingOwnerNotifiedAtStoreProtocol, user_id: str,
) -> bool:
    """design 6節「クリア配線」(フェーズ175): 「フォロー再開」(is_followingがTrueに
    戻る)、または「解約確定」(customer.subscription.deleted受信でcurrent_plan_idが
    Noneに戻る)のいずれかが起きた時点で呼ぶ。`blocked_but_billing_owner_notified_at`が
    設定済みの場合のみクリアし、変更があったかどうか(True/False)を返す
    (payment_failure.py`clear_payment_failure_on_success()`と同じ、呼び出し側が
    ログ確認できる冪等設計)。未設定(そもそも一度も通知対象になったことがない、または
    既にクリア済み)の場合は何もせず`False`を返す。

    呼び出し配線自体は本関数の対象外で、`cloud_function_webhook.process_follow_event()`
    (フォロー再開)・`stripe_dispatch.dispatch_stripe_event()`の`customer.subscription.
    deleted`分岐(解約確定)の両方から呼ばれる。
    """
    if store.get_blocked_but_billing_owner_notified_at(user_id) is None:
        return False
    store.set_blocked_but_billing_owner_notified_at(user_id, None)
    return True


# ---------------------------------------------------------------------------
# メッセージ整形(design 2節)
# ---------------------------------------------------------------------------


def _format_customer_identifier_line(user_id: str, business_name: Optional[str]) -> str:
    """business-name-owner-notification-display-design.md 3節・5節「今後の課題」への
    対応(フェーズ263): business_nameが設定されていれば「顧客名: {business_name}
    (ID: {user_id})」形式、未設定であれば従来通り「顧客ID: {user_id}」のみを返す
    (payment_suspension_owner_notification._format_business_identifier_line()と同じ
    考え方だが、本モジュール既存の「顧客ID:」表記を踏襲し「業者名/業者ID」ではなく
    「顧客名/顧客ID」の語を使う)。"""
    if business_name:
        return f"顧客名: {business_name}(ID: {user_id})"
    return f"顧客ID: {user_id}"


def build_blocked_but_billing_owner_notification_flex_message(
    user_id: str, business_name: Optional[str] = None
) -> dict:
    """design 2節: ボタンを持たない、テキストのみのbubble形式のFlex Messageを組み立てる。

    build_trial_end_notification_flex_message()(trial_end_scheduler.py)と同じ
    `bubble`形式のうち、`footer`(ボタン)を持たない構成とした。`business_name`は
    フェーズ263で追加した省略可能引数(business-name-owner-notification-display-
    design.md 5節)、未指定時は従来通り`user_id`のみを表示する。
    """
    customer_identifier_line = _format_customer_identifier_line(user_id, business_name)
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": BLOCKED_BUT_BILLING_OWNER_NOTIFICATION_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": (
                        "以下の顧客がLINEをブロックしていますが、Stripeでの契約(決済)は"
                        "継続中です。\n"
                        f"{customer_identifier_line}"
                    ),
                    "wrap": True,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": (
                        "必要に応じて顧客への個別フォロー(再フォローのお願い・解約意向の"
                        "確認等)をご検討ください。"
                    ),
                    "wrap": True,
                    "margin": "md",
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function G本体)
# ---------------------------------------------------------------------------


@dataclass
class SendBlockedButBillingOwnerNotificationsResult:
    """1回のCloud Function G起動での送信結果(呼び出し側のログ・監視用、
    trial_end_scheduler.SendTrialEndNotificationsResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id(顧客側の識別子)
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_blocked_but_billing_owner_notifications(
    candidate_user_ids: Sequence[str],
    now: datetime,
    notified_at_store: (
        BlockedButBillingOwnerNotifiedAtReader
        # 読み書き両方を1つのストアで担う想定(user_profileドキュメント、design 4節)。
        # Protocolの合成をタプルで表現できないため、実引数側で両方を満たすオブジェクトを渡す。
    ),
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
    business_name_reader: Optional[BlockedButBillingBusinessNameReader] = None,
) -> SendBlockedButBillingOwnerNotificationsResult:
    """blocked-but-billing-owner-notification-design.md 3〜4節「Cloud Function G」本体。

    candidate_user_idsは呼び出し元が`list_blocked_but_billing_candidates()`
    (blocked_but_billing_candidates.py、フェーズ167)を呼んだ結果を想定する。新規通知対象の
    絞り込みはselect_new_blocked_but_billing_candidates_for_notification()が行う。

    送信先は顧客ごとのuser_idではなく固定のowner_line_user_id(design 1節)。送信成功時のみ
    notified_at_store.set_blocked_but_billing_owner_notified_at()を対象顧客のuser_idに
    対して書き込み、送信失敗時は書き込まない(trial_end_scheduler.pyのsend_trial_end_
    notifications()と同じ「書き込み一発+次回実行時に自然に再試行対象として残る」方式)。

    `business_name_reader`はフェーズ263で追加した省略可能引数(business-name-owner-
    notification-display-design.md 5節)。指定時は`get_business_name(user_id)`の結果を
    メッセージ整形に渡し、未指定時は全件`user_id`のみの表示(従来通り)となるため
    後方互換を維持する。
    """
    result = SendBlockedButBillingOwnerNotificationsResult()

    for user_id in select_new_blocked_but_billing_candidates_for_notification(
        candidate_user_ids, notified_at_store
    ):
        business_name = (
            business_name_reader.get_business_name(user_id)
            if business_name_reader is not None
            else None
        )
        contents = build_blocked_but_billing_owner_notification_flex_message(
            user_id, business_name
        )
        try:
            push_client.send_flex_message(
                owner_line_user_id,
                BLOCKED_BUT_BILLING_OWNER_NOTIFICATION_ALT_TEXT,
                contents,
            )
        except LinePushDeliveryError:
            result.failed.append(user_id)
            continue
        notified_at_store.set_blocked_but_billing_owner_notified_at(user_id, now)
        result.sent.append(user_id)

    return result


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    now = datetime(2026, 9, 2, 18, 0, 0)
    candidate_user_ids = ["u1", "u2", "u3"]

    class _NotifiedAtStub:
        def __init__(self) -> None:
            # u2は既に通知済みという想定(再通知しないことを確認するため)。
            self.notified_at: dict[str, datetime] = {"u2": datetime(2026, 9, 1, 18, 0, 0)}

        def get_blocked_but_billing_owner_notified_at(self, user_id: str) -> Optional[datetime]:
            return self.notified_at.get(user_id)

        def set_blocked_but_billing_owner_notified_at(
            self, user_id: str, notified_at: datetime
        ) -> None:
            self.notified_at[user_id] = notified_at

    class _BusinessNameStub:
        def __init__(self) -> None:
            # u1のみbusiness_name設定済み、u3は未設定という想定(フォールバック表示確認)。
            self.business_names: dict[str, str] = {"u1": "サンプルクリーニング商会"}

        def get_business_name(self, user_id: str) -> Optional[str]:
            return self.business_names.get(user_id)

    store = _NotifiedAtStub()
    push = InMemoryLinePushClient()
    result = send_blocked_but_billing_owner_notifications(
        candidate_user_ids, now, store, push, business_name_reader=_BusinessNameStub()
    )
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
