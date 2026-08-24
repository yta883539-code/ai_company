#!/usr/bin/env python3
"""
trial-end-scheduler-design.mdで設計した「Cloud Function D: send_trial_end_notifications」を、
実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のCloud Scheduler設定・LINE Push Message APIでの送信、およびLIFFアプリの実登録は
  いずれもオーナー承認待ち(pending-approval.md参照)。本モジュールはそれとは別に、
  「いつ・どのユーザーにトライアル終了通知を送るべきか」の判定ロジック(3節)と、
  「実際に送るメッセージの整形・送信・冪等性のための書き込み」の配線(フェーズ104で追加)を
  実クラウド接続なしで検証可能にしたもの
  (line-reservation-ai/cloud_function_send_reminders.pyと同じ位置づけ)。
- LinePushClientはline-reservation-ai/cloud_function_process_event.pyのLinePushClientと
  同じ形のProtocolを本venture向けに独自定義する(本ventureはこれまでLINE Reply APIしか
  使っておらず、Push Message API用のクライアントが未定義だったため)。

設計の参照元: trial-end-scheduler-design.md, trial-end-notification-design.md,
trial-start-anchor-decision.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol, Sequence

# trial-end-notification-design.md 2節(B): トライアル開始から14日でトライアル終了。
DEFAULT_TRIAL_PERIOD_DAYS = 14


@dataclass(frozen=True)
class TrialUserState:
    """trial-end-scheduler-design.md 3節が参照する、ユーザー1件分のusage_counter状態。

    trial_start_at・trial_end_notified_atはInMemoryUsageCounter(cloud_function_webhook.py)
    に既存のフィールドをそのまま反映する。upgraded_atはtrial-end-scheduler-design.md
    2節で新規に提案したフィールドで、実際の書き込み配線(stripe_webhook.py側)は
    本モジュールの範囲外のため、未接続の間は常にNoneとして扱われる想定。
    """

    user_id: str
    trial_start_at: Optional[datetime]
    trial_end_notified_at: Optional[datetime] = None
    upgraded_at: Optional[datetime] = None
    # README.mdフェーズ105: cloud_function_webhook.pyのincrement_trial_generation_count()で
    # 積み上げた、月次カウンタとは別立てのトライアル期間中の生成回数累計。呼び出し元が
    # usage_counter.get_trial_generation_count(user_id)から読み取って渡す想定(他フィールドと
    # 同じく、本モジュールはusage_counterの値をそのまま反映するだけで自ら集計はしない)。
    trial_generation_count: int = 0
    # README.mdフェーズ109: content-generation-time-estimate.md「複数エリア同時更新時の
    # 按分式」用に、cloud_function_webhook.pyのincrement_trial_area_count()で積み上げた
    # トライアル期間中のエリア更新総数累計(各生成のhistory_rows要素数の合計)。呼び出し元が
    # usage_counter.get_trial_area_count(user_id)から読み取って渡す想定。Noneは
    # increment_trial_area_count未対応の既存usage_counter実装からの後方互換用で、
    # format_trial_end_notification_message()側でフェーズ109以前の単純化式にフォールバック
    # させる目印として使う。
    trial_area_count: Optional[int] = None


def select_due_trial_end_notifications(
    users: Sequence[TrialUserState],
    now: datetime,
    trial_period_days: int = DEFAULT_TRIAL_PERIOD_DAYS,
) -> list[TrialUserState]:
    """trial-end-scheduler-design.md 3節の抽出条件をそのままコード化したもの。

    以下すべてを満たすユーザーのみを対象として返す(順序はusersの入力順を維持する)。
    - trial_start_atが設定済み
    - trial_end_notified_atが未設定(条件A側で既に送信済みなら対象外になる想定)
    - upgraded_atが未設定(2節の暫定的な既知の限界: 配線未接続の間は常にNoneのため
      この条件は事実上素通りする)
    - now - trial_start_at >= trial_period_days日
      (「ちょうど」の時刻一致ではなく「以上」の範囲条件とすることで、日次実行の
      遅延・欠落に自然に耐える。reminder-scheduler-design.mdの
      select_due_initial_reminders()と同じ設計判断)
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
# メッセージ整形(trial-end-notification-design.md 3節)
# ---------------------------------------------------------------------------

# content-generation-time-estimate.md: 「浮いた作業時間の目安」は、1回の生成で作られる
# 3点セット(SNS投稿文・LINE/Web告知文・課題入れ替え履歴記録)を手動作成する場合の仮置き
# 試算値(1回あたり平均15分、幅12〜18分)を採用する。実ヒアリングによる検証は未実施のため
# 仮置きであることをメッセージ文言内にも明記する。生成回数(○回)は、README.mdフェーズ105で
# trial_generation_count(usage_counter.get_trial_generation_count()、月次カウンタとは
# 別立ての専用カウンタ)を新設して解消済み。
MINUTES_SAVED_PER_GENERATION = 15

# README.mdフェーズ109: content-generation-time-estimate.md「複数エリア同時更新時の按分式」で
# 導出した`minutes(n) = 10 + 5n`(n=1回の生成で更新したエリア数)をトライアル全体に積み上げると
# `10×生成回数 + 5×エリア更新総数`になる(n=1のみの場合は15×生成回数と一致)。
BASE_MINUTES_PER_GENERATION = 10
ADDITIONAL_MINUTES_PER_AREA = 5

TRIAL_END_NOTIFICATION_TEMPLATE = (
    "[コースセットパシャッと] 14日間の無料トライアル、お疲れさまでした!\n"
    "\n"
    "これまでの生成実績:\n"
    "・投稿文生成: {generation_count}回\n"
    "・浮いた作業時間の目安: 約{minutes_saved}分(1回あたり平均{minutes_per_generation}分と仮定)\n"
    "\n"
    "引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。\n"
    "このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。\n"
    "\n"
    "▼ 有料プランへ進む(カード登録)\n"
    "{liff_url}"
)

# README.mdフェーズ109: trial_area_countが取得できる場合(usage_counterが
# increment_trial_area_count対応済み)に使う、複数エリア同時更新を考慮した文言。
# content-generation-time-estimate.md「現状の実装との差分・次の課題」で提案した表現を採用。
TRIAL_END_NOTIFICATION_TEMPLATE_WITH_AREA_COUNT = (
    "[コースセットパシャッと] 14日間の無料トライアル、お疲れさまでした!\n"
    "\n"
    "これまでの生成実績:\n"
    "・投稿文生成: {generation_count}回\n"
    "・浮いた作業時間の目安: 約{minutes_saved}分"
    "(1エリアの更新につき平均{base_minutes}分、複数エリア同時更新時は1エリア追加ごとに"
    "さらに約{additional_minutes}分と仮定)\n"
    "\n"
    "引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。\n"
    "このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。\n"
    "\n"
    "▼ 有料プランへ進む(カード登録)\n"
    "{liff_url}"
)

# checkout-initiation-flow-design.mdで採用したLIFF方式の決済導線は、Checkout Session個別の
# URLではなくLIFFアプリ自体の固定URL(開いた時点でliff.getIDToken()→サーバ側検証→Checkout
# Session作成→リダイレクトの一連の処理が動く)であるため、cloud_function_webhook.pyの
# PORTAL_LINK_PLACEHOLDERと同じく、実登録(オーナー承認待ち)までは差し替え用の目印文字列とする。
LIFF_URL_PLACEHOLDER = "{有料プランへ進むLIFFアプリ URL}"


def format_trial_end_notification_message(
    generation_count: int,
    liff_url: str = LIFF_URL_PLACEHOLDER,
    minutes_per_generation: int = MINUTES_SAVED_PER_GENERATION,
    area_count: Optional[int] = None,
) -> str:
    """trial-end-notification-design.md 3節の通知メッセージ文面を組み立てる。

    content-generation-time-estimate.md フェーズ109: area_countが渡された場合(usage_counterが
    trial_area_countに対応済み)は`10×generation_count + 5×area_count`の按分式を使う。
    area_countがNone(未対応のusage_counter実装からの後方互換)の場合は、フェーズ109以前の
    `generation_count × minutes_per_generation`(仮置き15分)にフォールバックする。
    """
    if area_count is not None:
        minutes_saved = (
            BASE_MINUTES_PER_GENERATION * generation_count
            + ADDITIONAL_MINUTES_PER_AREA * area_count
        )
        return TRIAL_END_NOTIFICATION_TEMPLATE_WITH_AREA_COUNT.format(
            generation_count=generation_count,
            minutes_saved=minutes_saved,
            base_minutes=BASE_MINUTES_PER_GENERATION + ADDITIONAL_MINUTES_PER_AREA,
            additional_minutes=ADDITIONAL_MINUTES_PER_AREA,
            liff_url=liff_url,
        )
    return TRIAL_END_NOTIFICATION_TEMPLATE.format(
        generation_count=generation_count,
        minutes_saved=generation_count * minutes_per_generation,
        minutes_per_generation=minutes_per_generation,
        liff_url=liff_url,
    )


# ---------------------------------------------------------------------------
# 実送信配線(Cloud Function D本体、trial-end-scheduler-design.md 5節の残課題)
# ---------------------------------------------------------------------------


class LinePushDeliveryError(Exception):
    """LINE Push Message API呼び出し失敗(タイムアウト・5xx・429等)を表す。
    api-call-failure-handling.mdのReply API向け失敗ハンドリングと対称の位置づけ。"""


class LinePushClient(Protocol):
    def send_message(self, user_id: str, text: str) -> None:
        ...


class InMemoryLinePushClient:
    """実LINE Push Message API接続の代わりに送信内容を記録するだけの検証用クライアント
    (line-reservation-ai/cloud_function_process_event.py InMemoryLinePushClientと同じ位置づけ)。
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_message(self, user_id: str, text: str) -> None:
        self.sent.append((user_id, text))


class TrialEndNotifiedAtWriter(Protocol):
    """cloud_function_webhook.py UsageCounterProtocolのうち、本モジュールが実際に使う
    2メソッドのみを要求する最小限のProtocol(UpgradedAtWriterProtocol、stripe_webhook.pyと
    同じ「呼び出し側は具象クラスに直接依存しない」という考え方)。"""

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        ...


@dataclass
class SendTrialEndNotificationsResult:
    """1回のCloud Function D起動での送信結果(呼び出し側のログ・監視用、
    line-reservation-ai/cloud_function_send_reminders.py SendRemindersResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # user_id
    failed: list[str] = field(default_factory=list)  # user_id(送信失敗、次回起動時に再試行)


def send_trial_end_notifications(
    users: Sequence[TrialUserState],
    now: datetime,
    usage_counter: TrialEndNotifiedAtWriter,
    push_client: LinePushClient,
    liff_url: str = LIFF_URL_PLACEHOLDER,
    trial_period_days: int = DEFAULT_TRIAL_PERIOD_DAYS,
) -> SendTrialEndNotificationsResult:
    """trial-end-scheduler-design.md 1節の全体構成図における「Cloud Function D:
    send_trial_end_notifications」本体。引数のusersは呼び出し元でFirestoreから読み取った
    候補一覧を想定し(3節の抽出条件をクエリ化したものに相当)、実際の絞り込みは
    select_due_trial_end_notifications()が行う。

    送信成功時のみ`usage_counter.set_trial_end_notified_at()`を書き込み、送信失敗時は
    書き込まない(4節の冪等性設計、send_reminders()と同じ「書き込み一発+次回実行時に
    自然に再試行対象として残る」方式)。

    README.mdフェーズ105: 「投稿文生成: ○回」はユーザーごとに値が異なるため、
    TrialUserState.trial_generation_countを使って1ユーザーずつ文面を組み立てる
    (liff_urlは全ユーザー共通のため、フェーズ104までと同じく引数で固定できる)。
    """
    result = SendTrialEndNotificationsResult()

    for user in select_due_trial_end_notifications(users, now, trial_period_days):
        text = format_trial_end_notification_message(
            user.trial_generation_count, liff_url, area_count=user.trial_area_count
        )
        try:
            push_client.send_message(user.user_id, text)
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        usage_counter.set_trial_end_notified_at(user.user_id, now)
        result.sent.append(user.user_id)

    return result


def _demo() -> None:
    now = datetime(2026, 8, 23, 4, 0, 0)
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

    # send_trial_end_notifications()の配線確認: u1のみが送信対象になり、
    # usage_counter.set_trial_end_notified_at()が呼ばれることを確認する。
    class _InMemoryUsageCounterStub:
        def __init__(self) -> None:
            self.notified_at: dict[str, datetime] = {}

        def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
            self.notified_at[user_id] = notified_at

    usage_counter = _InMemoryUsageCounterStub()
    push = InMemoryLinePushClient()
    result = send_trial_end_notifications(users, now, usage_counter, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"push: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
