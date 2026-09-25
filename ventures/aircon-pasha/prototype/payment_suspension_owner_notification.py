#!/usr/bin/env python3
"""
payment-suspension-owner-notification-design.md(フェーズ255)で設計した「制限モード
移行時のオーナー(運営者)向け能動通知」を、実行可能なコードに落とし込んだもの。

course-set-pashaのpayment-suspension-owner-notification-design.md(フェーズ125)・
kura-pashaの同種実装を本ventureへ横展開したもので、blocked_but_billing_owner_
notification.py(フェーズ174)と対になる、オーナー(運営者)宛の能動通知2件目にあたる。

位置づけ:
- 実際のオーナーLINEユーザーID(`OWNER_LINE_USER_ID_PLACEHOLDER`)の取得・設定、実LINE
  Push Message APIでの送信はいずれもオーナー承認待ち(README.md「実LLM呼び出し・実LINE
  API接続」の記載範囲に含まれる、新規の承認待ち事項ではない)。本モジュールはそれとは
  別に、「いつ・どの業者の制限モード移行をオーナーへ知らせるべきか」の判定ロジック
  (design 3節)と、「実際に送るメッセージの整形・送信・冪等性のための書き込み」の配線を
  実クラウド接続なしで検証可能にしたもの。
- `LinePushClient`・`LinePushDeliveryError`はtrial_end_scheduler.pyで既に定義済みの
  ものをそのまま再利用する(blocked_but_billing_owner_notification.pyと同じ方針、本
  モジュールで重複定義しない)。送信先は業者ごとのuser_idではなく固定のオーナー1件で
  あるため、send_flex_message()に渡すidはOWNER_LINE_USER_ID_PLACEHOLDER(blocked_but_
  billing_owner_notification.pyで定義済みの定数)で固定する。
- course-set-pasha版はUsageCounterProtocolが専用フラグを持たず`_is_payment_suspended()`
  による都度算出のみで制限モードを判定するため、経過日数を毎回再計算する抽出条件を採る。
  本ventureは`payment_suspended_at`フィールド(フェーズ140)を既に持ち、制限モードへの
  移行時点をpayment_suspension_scheduler.send_payment_suspensions()が明示的に書き込む
  設計を採用しているため、本モジュールは`payment_suspended_at`の設定有無のみで判定する
  より単純な条件を採る(design 3節参照)。

設計の参照元: payment-suspension-owner-notification-design.md,
course-set-pasha/prototype/payment_suspension_owner_notification.py,
blocked_but_billing_owner_notification.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Protocol, Sequence

from blocked_but_billing_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

PAYMENT_SUSPENSION_OWNER_NOTIFICATION_ALT_TEXT = (
    "[エアコンパシャッと運営] 制限モード移行のお知らせ"
)


@dataclass(frozen=True)
class PaymentSuspensionOwnerNotificationUserState:
    """design 3節が参照する、業者1件分の`user_profile`状態。

    payment_failure_detected_at・payment_suspended_at・payment_suspension_owner_
    notified_atはuser_id_linking.pyのUserProfile(フェーズ140・255で追加したフィールド)
    をそのまま反映する。business_nameも同UserProfileの既存必須フィールド(user_id_
    linking.py)をそのまま反映する想定だが、本モジュール単体でのテスト容易性のため
    Optionalとし、未設定時はuser_idのみの表示にフォールバックする(design 8節・
    business-name-owner-notification-display-design.md参照)。"""

    user_id: str
    payment_suspended_at: Optional[datetime]
    payment_failure_detected_at: Optional[datetime] = None
    payment_suspension_owner_notified_at: Optional[datetime] = None
    business_name: Optional[str] = None


def select_due_payment_suspension_owner_notifications(
    users: Sequence[PaymentSuspensionOwnerNotificationUserState],
) -> list[PaymentSuspensionOwnerNotificationUserState]:
    """payment-suspension-owner-notification-design.md 3節の抽出条件をそのままコード化した
    もの。

    以下すべてを満たす業者のみを対象として返す(順序はusersの入力順を維持する)。
    - payment_suspended_atが設定済み(既に制限モードへ移行済み)
    - payment_suspension_owner_notified_atが未設定(1回のみ送信)

    course-set-pasha版のように猶予期間からの経過日数を再計算しない(design 3節「course-
    set-pashaとの設計上の違い」参照。本venture固有のpayment_suspended_atフィールドが
    既に「制限モードへ移行済みか」を直接表現しているため)。
    """

    due: list[PaymentSuspensionOwnerNotificationUserState] = []
    for user in users:
        if user.payment_suspended_at is None:
            continue
        if user.payment_suspension_owner_notified_at is not None:
            continue
        due.append(user)
    return due


# ---------------------------------------------------------------------------
# メッセージ整形(design 4節)
# ---------------------------------------------------------------------------


def _format_elapsed_days(
    user: PaymentSuspensionOwnerNotificationUserState, now: datetime
) -> Optional[int]:
    """design 4節の`elapsed_days`(決済失敗検知からの経過日数)を算出する。
    payment_failure_detected_atが未設定(理論上は起きない想定だが、safety側として
    Noneを許容する)の場合はNoneを返し、呼び出し側で表示を省略する。"""
    if user.payment_failure_detected_at is None:
        return None
    return (now - user.payment_failure_detected_at).days


def _format_business_identifier_line(
    user: PaymentSuspensionOwnerNotificationUserState,
) -> str:
    """business-name-owner-notification-display-design.md 3節: business_nameが
    設定されていれば「業者名(ID: user_id)」形式、未設定であれば従来通り「業者ID:
    user_id」のみを返す(オーナーが一見して業者を識別できることを優先しつつ、
    user_idも併記して個別フォロー時の突合を可能にする)。"""
    if user.business_name:
        return f"業者名: {user.business_name}(ID: {user.user_id})"
    return f"業者ID: {user.user_id}"


def build_payment_suspension_owner_notification_flex_message(
    user: PaymentSuspensionOwnerNotificationUserState, now: datetime
) -> dict:
    """design 2・4節: ボタンを持たない、テキストのみのbubble形式のFlex Messageを組み立てる
    (blocked_but_billing_owner_notification.build_blocked_but_billing_owner_
    notification_flex_message()と同じ構成)。"""
    elapsed_days = _format_elapsed_days(user, now)
    elapsed_days_line = (
        f"決済失敗検知からの経過日数: {elapsed_days}日"
        if elapsed_days is not None
        else "決済失敗検知からの経過日数: 不明"
    )
    business_identifier_line = _format_business_identifier_line(user)
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": PAYMENT_SUSPENSION_OWNER_NOTIFICATION_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": (
                        "以下の業者が決済失敗の猶予期間(7日)を超え、作業完了報告・"
                        "お手入れ案内生成の制限モードへ移行しました。\n"
                        f"{business_identifier_line}\n"
                        f"{elapsed_days_line}"
                    ),
                    "wrap": True,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": (
                        "必要に応じて業者への個別フォロー(お支払い方法のご案内等)を"
                        "ご検討ください。"
                    ),
                    "wrap": True,
                    "margin": "md",
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function H本体、design 5・6節)
# ---------------------------------------------------------------------------


class PaymentSuspensionOwnerNotifiedAtWriter(Protocol):
    """user_id_linking.py UserProfileStoreProtocolのうち、本モジュールが実際に使う
    1メソッドのみを要求する最小限のProtocol(他モジュールのWriter Protocolと同じ
    考え方)。"""

    def set_payment_suspension_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        ...


@dataclass
class SendPaymentSuspensionOwnerNotificationsResult:
    """1回のCloud Function H起動での送信結果(呼び出し側のログ・監視用、他スケジューラの
    SendResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id(業者側の識別子)
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_payment_suspension_owner_notifications(
    users: Sequence[PaymentSuspensionOwnerNotificationUserState],
    now: datetime,
    notified_at_store: PaymentSuspensionOwnerNotifiedAtWriter,
    push_client: LinePushClient,
    owner_line_user_id: str = OWNER_LINE_USER_ID_PLACEHOLDER,
) -> SendPaymentSuspensionOwnerNotificationsResult:
    """payment-suspension-owner-notification-design.md 5〜6節「Cloud Function H」本体。

    引数のusersは呼び出し元でFirestoreから読み取った候補一覧を想定し、実際の絞り込みは
    select_due_payment_suspension_owner_notifications()が行う。送信先は業者ごとの
    user_idではなく固定のowner_line_user_id(design 2節)。送信成功時のみnotified_at_
    store.set_payment_suspension_owner_notified_at()を対象業者のuser_idに対して書き込み、
    送信失敗時は書き込まない(blocked_but_billing_owner_notification.send_blocked_but_
    billing_owner_notifications()と同じ「書き込み一発+次回実行時に自然に再試行対象として
    残る」方式)。業者ごとに文面が変わるため、メッセージ整形はループ内で1件ずつ行う。
    """
    result = SendPaymentSuspensionOwnerNotificationsResult()

    for user in select_due_payment_suspension_owner_notifications(users):
        contents = build_payment_suspension_owner_notification_flex_message(user, now)
        try:
            push_client.send_flex_message(
                owner_line_user_id,
                PAYMENT_SUSPENSION_OWNER_NOTIFICATION_ALT_TEXT,
                contents,
            )
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        notified_at_store.set_payment_suspension_owner_notified_at(user.user_id, now)
        result.sent.append(user.user_id)

    return result


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient

    now = datetime(2026, 9, 23, 4, 0, 0)
    users = [
        # 制限モードへ移行済み・未通知: 対象
        PaymentSuspensionOwnerNotificationUserState(
            user_id="u1",
            payment_suspended_at=now,
            payment_failure_detected_at=now,
        ),
        # まだ猶予期間中(制限モード未移行): 対象外
        PaymentSuspensionOwnerNotificationUserState(
            user_id="u2",
            payment_suspended_at=None,
            payment_failure_detected_at=now,
        ),
        # 既にオーナー通知送信済み: 対象外
        PaymentSuspensionOwnerNotificationUserState(
            user_id="u3",
            payment_suspended_at=now,
            payment_failure_detected_at=now,
            payment_suspension_owner_notified_at=now,
        ),
    ]
    due = select_due_payment_suspension_owner_notifications(users)
    print([u.user_id for u in due])

    class _NotifiedAtStub:
        def __init__(self) -> None:
            self.notified_at: dict[str, datetime] = {}

        def set_payment_suspension_owner_notified_at(
            self, user_id: str, notified_at: Optional[datetime]
        ) -> None:
            self.notified_at[user_id] = notified_at

    store = _NotifiedAtStub()
    push = InMemoryLinePushClient()
    result = send_payment_suspension_owner_notifications(users, now, store, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
