#!/usr/bin/env python3
"""
trial-end-scheduler-design.md(フェーズ133)で設計した「Cloud Function E:
send_trial_end_notifications」を、実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信はいずれもオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「いつ・どのユーザーに
  トライアル終了通知を送るべきか」の判定ロジック(design 3節)と、「実際に送るメッセージの
  整形・送信・冪等性のための書き込み」の配線を実クラウド接続なしで検証可能にしたもの
  (course-set-pasha/prototype/trial_end_scheduler.pyと同じ位置づけ)。
- 本ventureはcourse-set-pashaと異なりLIFF不要のpostbackアクションボタン方式
  (checkout-initiation-flow-design.md、design 2節)のため、通知メッセージはプレーン
  テキストではなくボタン付きのFlex Messageとして組み立てる(design 2節)。ボタンの
  postbackデータはcheckout_session.pyのSTART_CHECKOUT_POSTBACK_DATAをそのまま再利用し、
  「Checkout Session作成はボタン押下時のprocess_postback_event()側で行う」という既存の
  役割分担を維持する(design 2節、本モジュールはCheckout Session作成ロジックに依存しない)。

設計の参照元: trial-end-scheduler-design.md, trial-end-notification-design.md,
trial-start-anchor-decision.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol, Sequence

from checkout_session import (
    DEFAULT_CHECKOUT_PLAN,
    PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER,
    build_start_checkout_postback_data,
)
from user_id_linking import UserProfile

# trial-end-notification-design.md 2節(B): トライアル開始から14日でトライアル終了。
DEFAULT_TRIAL_PERIOD_DAYS = 14


@dataclass(frozen=True)
class TrialUserState:
    """design 3節が参照する、ユーザー1件分の`user_profile`状態。

    trial_start_at・trial_end_notified_at・upgraded_atはuser_id_linking.pyの
    UserProfile(フェーズ134で追加した3フィールド)をそのまま反映する。
    trial_generation_countはtrial-end-notification-design.md 5節で予告されている
    トライアル専用生成回数カウンタ(本venture未実装)を想定した値で、呼び出し元が
    別途集計して渡す前提。未接続の間は既定値0のまま(メッセージ文言上「0回」と
    表示されるだけで、選定ロジック自体には影響しない)。
    """

    user_id: str
    trial_start_at: Optional[datetime]
    trial_end_notified_at: Optional[datetime] = None
    upgraded_at: Optional[datetime] = None
    trial_generation_count: int = 0


class TrialUserStateReader(Protocol):
    """user_id_linking.UserProfileStoreProtocolのうち、TrialUserStateの組み立てに
    必要なgetter(get()のみ)を要求する最小限のProtocol(course-set-pashaの
    TrialUserStateReaderと同じ「呼び出し側は具象クラスに直接依存しない」考え方)。
    本ventureはcourse-set-pasha(usage_counterがフィールドごとの個別getterを持つ設計)
    と異なり、UserProfile1件が各フィールドを直接保持する設計(2節)のため、
    get(user_id)一発で足りる。"""

    def get(self, user_id: str) -> Optional[UserProfile]:
        ...


def build_trial_user_states(
    store: TrialUserStateReader,
    user_ids: Sequence[str],
) -> list[TrialUserState]:
    """storeのget()から、user_idごとにTrialUserStateを組み立てる。

    trial-end-scheduler-design.md 1節「user_profileストアから...ユーザーを抽出」の
    Firestoreクエリ相当部分について、これまでTrialUserStateは各テスト・_demo()内で
    手動構築されるのみで、実際のUserProfileStoreProtocol実装(InMemoryUserProfileStore等)
    から読み取って組み立てる関数が存在しなかった配線漏れを解消する(course-set-pashaの
    build_trial_user_states()と同種の観点。呼び出し元は実際にはFirestoreクエリの結果
    としてuser_idsを得る想定で、本関数はその後の1件ずつの読み出し部分のみを担う)。
    存在しないuser_id(store.get()がNoneを返す)はtrial_start_at未設定の
    TrialUserStateとして扱い、select_due_trial_end_notifications()側の既存の除外条件
    (trial_start_at is None)にそのまま乗せる。
    """
    states: list[TrialUserState] = []
    for user_id in user_ids:
        profile = store.get(user_id)
        if profile is None:
            states.append(TrialUserState(user_id=user_id, trial_start_at=None))
            continue
        states.append(
            TrialUserState(
                user_id=user_id,
                trial_start_at=profile.trial_start_at,
                trial_end_notified_at=profile.trial_end_notified_at,
                upgraded_at=profile.upgraded_at,
                trial_generation_count=profile.trial_generation_count,
            )
        )
    return states


def select_due_trial_end_notifications(
    users: Sequence[TrialUserState],
    now: datetime,
    trial_period_days: int = DEFAULT_TRIAL_PERIOD_DAYS,
) -> list[TrialUserState]:
    """design 3節の抽出条件をそのままコード化したもの。

    以下すべてを満たすユーザーのみを対象として返す(順序はusersの入力順を維持する)。
    - trial_start_atが設定済み
    - trial_end_notified_atが未設定(条件A側〈生成回数10回到達〉で既に送信済みなら
      対象外になる想定)
    - upgraded_atが未設定(design 2節の暫定的な既知の限界: 書き込み配線未接続の間は
      常にNoneのためこの条件は事実上素通りする)
    - now - trial_start_at >= trial_period_days日(「ちょうど」の時刻一致ではなく
      「以上」の範囲条件とすることで、日次実行の遅延・欠落に自然に耐える。
      course-set-pashaのselect_due_trial_end_notifications()と同じ設計判断)
    """

    threshold = timedelta(days=trial_period_days)
    due: list[TrialUserState] = []
    for user in users:
        if user.trial_start_at is None:
            continue
        if user.trial_end_notified_at is not None:
            continue
        if user.upgraded_at is not None:
            continue
        if now - user.trial_start_at >= threshold:
            due.append(user)
    return due


# ---------------------------------------------------------------------------
# メッセージ整形(design 2節・trial-end-notification-design.md 3節)
# ---------------------------------------------------------------------------

TRIAL_END_ALT_TEXT = "[エアコンパシャッと] 14日間の無料トライアル、お疲れさまでした!"

TRIAL_END_BUTTON_LABEL = "有料プランへ進む"


def build_trial_end_notification_flex_message(generation_count: int) -> dict:
    """design 1節「本venture固有の差分」: 通知メッセージ自体もFlex Messageの
    ボタン込みで組み立てる(プレーンテキストリンクではない)。

    checkout-session-plan-selection-design.md 3節「次回以降の課題」フェーズ180対応:
    footerのボタンは、pricing-plan.mdの3プラン(`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の
    キー順、スモール/スタンダード/繁忙期対応)ぶんに分割する。各ボタンのpostbackデータは
    `checkout_session.build_start_checkout_postback_data(plan)`
    (`"action=start_checkout&plan=<プラン名>"`)で組み立てる。実際のCheckout Session作成は
    process_postback_event()側の役割のため、本関数はメッセージ整形のみを担う
    (design 2節「独立させる」方針)。トライアル終了通知(Push Message、業者が最初に
    プランを選ぶ入口)のみを本フェーズの対象とし、条件A(生成回数到達)・一時停止/制限
    モード通知等、QuickReplyButton(単一ボタン)経由の他CTAは既定プラン
    (`DEFAULT_CHECKOUT_PLAN`)据え置きのまま次回以降の課題として残す(README.md参照)。

    戻り値はLINE Messaging APIのFlex Message `contents`(bubble)相当のdictで、
    実送信時はこれを`{"type": "flex", "altText": ..., "contents": ...}`として
    Push Message APIへ渡す想定(実送信配線は本モジュール下部のsend_trial_end_
    notifications()を参照)。
    """
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": TRIAL_END_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": (
                        f"これまでの生成実績:\n"
                        f"・作業完了報告・お手入れ案内の生成: {generation_count}回"
                    ),
                    "wrap": True,
                    "margin": "md",
                },
                {
                    "type": "text",
                    "text": (
                        "引き続きご利用いただく場合は、下のボタンから有料プランを"
                        "お選びください。このまま何もしなければ自動課金は発生せず、"
                        "生成のみ一時停止となります。"
                    ),
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
                    "style": "primary" if plan == DEFAULT_CHECKOUT_PLAN else "secondary",
                    "action": {
                        "type": "postback",
                        "label": f"{plan}プランで始める",
                        "data": build_start_checkout_postback_data(plan),
                    },
                }
                for plan in PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER
            ],
        },
    }


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function E本体、design 5節の残課題)
# ---------------------------------------------------------------------------


class LinePushDeliveryError(Exception):
    """LINE Push Message API呼び出し失敗(タイムアウト・5xx・429等)を表す。
    api-call-failure-handling.mdのReply API向け失敗ハンドリングと対称の位置づけ。"""


class LinePushClient(Protocol):
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        ...


class InMemoryLinePushClient:
    """実LINE Push Message API接続の代わりに送信内容を記録するだけの検証用クライアント
    (course-set-pasha/prototype/trial_end_scheduler.py InMemoryLinePushClientと
    同じ位置づけ)。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        self.sent.append((user_id, alt_text, contents))


class TrialEndNotifiedAtWriter(Protocol):
    """user_id_linking.py UserProfileStoreProtocolのうち、本モジュールが実際に使う
    1メソッドのみを要求する最小限のProtocol(course-set-pashaのTrialEndNotifiedAtWriter
    と同じ「呼び出し側は具象クラスに直接依存しない」という考え方)。"""

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        ...


@dataclass
class SendTrialEndNotificationsResult:
    """1回のCloud Function E起動での送信結果(呼び出し側のログ・監視用、
    course-set-pasha SendTrialEndNotificationsResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_trial_end_notifications(
    users: Sequence[TrialUserState],
    now: datetime,
    profile_store: TrialEndNotifiedAtWriter,
    push_client: LinePushClient,
    trial_period_days: int = DEFAULT_TRIAL_PERIOD_DAYS,
) -> SendTrialEndNotificationsResult:
    """design 1節の全体構成図における「Cloud Function E: send_trial_end_notifications」
    本体。引数のusersは呼び出し元でFirestoreから読み取った候補一覧を想定し(design 3節の
    抽出条件をクエリ化したものに相当)、実際の絞り込みはselect_due_trial_end_notifications()
    が行う。

    送信成功時のみ`profile_store.set_trial_end_notified_at()`を書き込み、送信失敗時は
    書き込まない(design 4節の冪等性設計、course-set-pashaのsend_trial_end_notifications()
    と同じ「書き込み一発+次回実行時に自然に再試行対象として残る」方式)。
    """
    result = SendTrialEndNotificationsResult()

    for user in select_due_trial_end_notifications(users, now, trial_period_days):
        contents = build_trial_end_notification_flex_message(
            user.trial_generation_count
        )
        try:
            push_client.send_flex_message(user.user_id, TRIAL_END_ALT_TEXT, contents)
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        profile_store.set_trial_end_notified_at(user.user_id, now)
        result.sent.append(user.user_id)

    return result


def _demo() -> None:
    now = datetime(2026, 8, 28, 4, 0, 0)
    users = [
        # 14日ちょうど経過: 対象
        TrialUserState(user_id="u1", trial_start_at=now - timedelta(days=14)),
        # 13日しか経過していない: 対象外
        TrialUserState(user_id="u2", trial_start_at=now - timedelta(days=13)),
        # 既に通知済み: 対象外(条件Aで先に送信済み等を想定)
        TrialUserState(
            user_id="u3",
            trial_start_at=now - timedelta(days=20),
            trial_end_notified_at=now - timedelta(days=1),
        ),
        # 既に有料転換済み: 対象外
        TrialUserState(
            user_id="u4",
            trial_start_at=now - timedelta(days=20),
            upgraded_at=now - timedelta(days=2),
        ),
        # トライアル未開始(trial_start_at未設定): 対象外
        TrialUserState(user_id="u5", trial_start_at=None),
    ]
    due = select_due_trial_end_notifications(users, now)
    print([u.user_id for u in due])

    class _InMemoryProfileStoreStub:
        def __init__(self) -> None:
            self.notified_at: dict[str, datetime] = {}

        def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
            self.notified_at[user_id] = notified_at

    profile_store = _InMemoryProfileStoreStub()
    push = InMemoryLinePushClient()
    result = send_trial_end_notifications(users, now, profile_store, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push alt_text: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
