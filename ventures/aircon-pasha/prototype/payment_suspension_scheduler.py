#!/usr/bin/env python3
"""
payment-failure-reminder-scheduler-design.md「今後の課題」に残っていた「猶予期間(7日)
経過後に制限モードへ自動移行させるスケジューラ本体」を、実行可能なコードに落とし込んだもの
(フェーズ145)。design該当節が示した想定どおり、payment_failure_reminder_scheduler.pyと
同じ抽出パターンを用い、同じ日次ジョブ内でそのモジュールの後に実行される「Cloud Function G」
という位置づけ。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信はいずれもオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「いつ・どのユーザーを制限モード
  (段階3)へ移行させるべきか」の判定ロジックと、「移行時に送るメッセージの整形・送信・
  payment_suspended_atの書き込み」の配線を実クラウド接続なしで検証可能にしたもの
  (trial_end_scheduler.py・payment_failure_reminder_scheduler.pyと同じ構成)。
- 送信するメッセージ本文はpayment-failure-dunning-design.md 4節「制限モード移行時
  (段階3)」の文言と揃え、cloud_function_webhook.pyのPAYMENT_SUSPENDED_MESSAGE
  (返信時のメッセージ)と同一文言をFlex Message化して使う(段階3のプロアクティブな
  Push通知と、その後ユーザーがメモを送った際のリプライ内容を一致させ、案内の一貫性を保つ)。
  ボタンのlabel・postbackデータもUPDATE_PAYMENT_METHOD_BUTTON_LABEL・
  UPDATE_PAYMENT_METHOD_POSTBACK_DATA(cloud_function_webhook.py)をそのまま再利用する。

設計の参照元: payment-failure-reminder-scheduler-design.md, payment-failure-dunning-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol, Sequence

from cloud_function_webhook import (
    PAYMENT_SUSPENDED_MESSAGE,
    UPDATE_PAYMENT_METHOD_BUTTON_LABEL,
    UPDATE_PAYMENT_METHOD_POSTBACK_DATA,
)

# payment-failure-dunning-design.md 3節: 猶予期間は7日。
DEFAULT_GRACE_PERIOD_DAYS = 7


@dataclass(frozen=True)
class PaymentSuspensionUserState:
    """本モジュールが参照する、ユーザー1件分の`user_profile`状態。

    payment_failure_detected_at・payment_suspended_atはuser_id_linking.pyの
    UserProfile(フェーズ140で追加した2フィールド)をそのまま反映する。"""

    user_id: str
    payment_failure_detected_at: Optional[datetime]
    payment_suspended_at: Optional[datetime] = None


def select_due_payment_suspensions(
    users: Sequence[PaymentSuspensionUserState],
    now: datetime,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
) -> list[PaymentSuspensionUserState]:
    """payment-failure-reminder-scheduler-design.md「今後の課題」が示した抽出パターン
    (`now - payment_failure_detected_at >= timedelta(days=7)`かつ`payment_suspended_at
    is None`)をそのままコード化したもの。

    以下すべてを満たすユーザーのみを対象として返す(順序はusersの入力順を維持する)。
    - payment_failure_detected_atが設定済み
    - payment_suspended_atが未設定(1回のみ移行、既に制限モードのユーザーを再処理しない)
    - now - payment_failure_detected_at >= grace_period_days日
      (「ちょうど」の時刻一致ではなく「以上」の範囲条件とすることで、日次実行の遅延・欠落に
      自然に耐える。trial_end_scheduler.py・payment_failure_reminder_scheduler.pyと
      同じ設計判断)
    """

    threshold = timedelta(days=grace_period_days)
    due: list[PaymentSuspensionUserState] = []
    for user in users:
        if user.payment_failure_detected_at is None:
            continue
        if user.payment_suspended_at is not None:
            continue
        if now - user.payment_failure_detected_at >= threshold:
            due.append(user)
    return due


# ---------------------------------------------------------------------------
# メッセージ整形(payment-failure-dunning-design.md 4節「制限モード移行時(段階3)」)
# ---------------------------------------------------------------------------

PAYMENT_SUSPENSION_ALT_TEXT = "[エアコンパシャッと] 生成を一時停止しました"


def build_payment_suspension_flex_message() -> dict:
    """design 4節「制限モード移行時(段階3)」の文言をFlex Messageのボタン込みで組み立てる。

    本文はcloud_function_webhook.pyのPAYMENT_SUSPENDED_MESSAGE(返信時に使う文言)と
    同一のものを再利用する(プロアクティブなPush通知とリプライ時の案内で文言が食い違う
    ことを避けるため)。ボタンのlabel・postbackデータもUPDATE_PAYMENT_METHOD_BUTTON_LABEL・
    UPDATE_PAYMENT_METHOD_POSTBACK_DATAをそのまま再利用する。

    戻り値はLINE Messaging APIのFlex Message `contents`(bubble)相当のdictで、
    実送信時はこれを`{"type": "flex", "altText": ..., "contents": ...}`として
    Push Message APIへ渡す想定。
    """
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": PAYMENT_SUSPENSION_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": PAYMENT_SUSPENDED_MESSAGE,
                    "wrap": True,
                    "margin": "md",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "postback",
                        "label": UPDATE_PAYMENT_METHOD_BUTTON_LABEL,
                        "data": UPDATE_PAYMENT_METHOD_POSTBACK_DATA,
                    },
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function G本体)
# ---------------------------------------------------------------------------


class LinePushDeliveryError(Exception):
    """LINE Push Message API呼び出し失敗(タイムアウト・5xx・429等)を表す。
    trial_end_scheduler.LinePushDeliveryError・payment_failure_reminder_scheduler.
    LinePushDeliveryErrorと対称の位置づけ。"""


class LinePushClient(Protocol):
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        ...


class InMemoryLinePushClient:
    """実LINE Push Message API接続の代わりに送信内容を記録するだけの検証用クライアント
    (他スケジューラのInMemoryLinePushClientと同じ位置づけ)。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        self.sent.append((user_id, alt_text, contents))


class PaymentSuspendedAtWriter(Protocol):
    """user_id_linking.py UserProfileStoreProtocolのうち、本モジュールが実際に使う
    1メソッドのみを要求する最小限のProtocol(呼び出し側は具象クラスに直接依存しない、
    他スケジューラのWriter Protocolと同じ考え方)。"""

    def set_payment_suspended_at(self, user_id: str, value: Optional[datetime]) -> None:
        ...


@dataclass
class SendPaymentSuspensionsResult:
    """1回のCloud Function G起動での処理結果(呼び出し側のログ・監視用、
    他スケジューラのSendResultと対称)。"""

    suspended: list[str] = field(default_factory=list)  # user_id
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_payment_suspensions(
    users: Sequence[PaymentSuspensionUserState],
    now: datetime,
    profile_store: PaymentSuspendedAtWriter,
    push_client: LinePushClient,
    grace_period_days: int = DEFAULT_GRACE_PERIOD_DAYS,
) -> SendPaymentSuspensionsResult:
    """Cloud Function G本体。引数のusersは呼び出し元でFirestoreから読み取った候補一覧を
    想定し(抽出条件のクエリ化はselect_due_payment_suspensions()が行う)。

    送信成功時のみ`profile_store.set_payment_suspended_at()`を書き込み、送信失敗時は
    書き込まない(他スケジューラと同じ「書き込み一発+次回実行時に自然に再試行対象として
    残る」方式)。書き込みタイミングをPush送信成功後にすることで、送信に失敗したユーザーが
    「Push通知は届かないまま制限モードだけが有効になる」事態を避ける(_is_payment_suspended
    はpayment_suspended_atの設定有無のみで判定するため、書き込みが済めば次回のメモ送信時
    リプライで案内される。書き込みが済んでいなければ次回バッチで再試行され、いずれの経路でも
    ユーザーが無案内のまま生成停止になることはない)。
    """
    result = SendPaymentSuspensionsResult()

    for user in select_due_payment_suspensions(users, now, grace_period_days):
        contents = build_payment_suspension_flex_message()
        try:
            push_client.send_flex_message(
                user.user_id, PAYMENT_SUSPENSION_ALT_TEXT, contents
            )
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        profile_store.set_payment_suspended_at(user.user_id, now)
        result.suspended.append(user.user_id)

    return result


def _demo() -> None:
    now = datetime(2026, 8, 28, 4, 0, 0)
    users = [
        # 検知からちょうど7日経過: 対象
        PaymentSuspensionUserState(
            user_id="u1", payment_failure_detected_at=now - timedelta(days=7)
        ),
        # 検知から6日しか経過していない: 対象外
        PaymentSuspensionUserState(
            user_id="u2", payment_failure_detected_at=now - timedelta(days=6)
        ),
        # 既に制限モードへ移行済み: 対象外
        PaymentSuspensionUserState(
            user_id="u3",
            payment_failure_detected_at=now - timedelta(days=10),
            payment_suspended_at=now - timedelta(days=1),
        ),
        # 決済失敗が検知されていない: 対象外
        PaymentSuspensionUserState(user_id="u4", payment_failure_detected_at=None),
    ]
    due = select_due_payment_suspensions(users, now)
    print([u.user_id for u in due])

    class _InMemoryProfileStoreStub:
        def __init__(self) -> None:
            self.suspended_at: dict[str, datetime] = {}

        def set_payment_suspended_at(self, user_id: str, value: Optional[datetime]) -> None:
            self.suspended_at[user_id] = value

    profile_store = _InMemoryProfileStoreStub()
    push = InMemoryLinePushClient()
    result = send_payment_suspensions(users, now, profile_store, push)
    print(f"suspended={result.suspended}, failed={result.failed}")
    print(f"push alt_text: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
