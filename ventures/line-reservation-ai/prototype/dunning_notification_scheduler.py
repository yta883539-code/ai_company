#!/usr/bin/env python3
"""
payment-failure-dunning-design.md 6節(猶予期間の値による通知文言・リマインド
タイミングへの影響の事前整理)で設計した、猶予日数・リマインド回数・タイミングの
パラメータ化を、実行可能なコードに落とし込んだもの。

位置づけ:
- 決済代行サービスの選定(猶予期間7日を維持〈config A〉/標準スマートリトライを使い
  14日に延長〈config B〉のどちらを選ぶか)自体は、サービス契約を伴うため引き続き
  オーナー承認待ち(pending-approval.md参照)。
- 本モジュールは「どちらの構成が選ばれても設定値の変更のみで対応できる」ことを
  検証可能にするためのもので、実際のWebhook受信・Firestore書き込み・LINE送信は
  行わない(reminder_scheduler.py同様、判断・整形ロジックのみを切り出す)。

設計の参照元: payment-failure-dunning-design.md 3節・4節・6節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class DunningConfig:
    """猶予期間の構成(payment-failure-dunning-design.md 5節の二択A/Bに対応)。

    reminder_offsets: 検知時刻から何日後にリマインドを送るかのタプル。
        1件の場合は「終了直前リマインド」のみ(3節の3日前ルールに対応する値を渡す)、
        2件の場合は先頭を「中間地点の状況確認」・末尾を「終了直前リマインド」として扱う
        (6.2節: 14日構成のみ中間地点リマインドを追加する)。
    """

    name: str
    grace_period_days: int
    reminder_offsets: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.reminder_offsets:
            raise ValueError("reminder_offsets must contain at least the final reminder")
        if any(offset >= self.grace_period_days for offset in self.reminder_offsets):
            raise ValueError("reminder_offsets must all be before grace_period_days")
        if list(self.reminder_offsets) != sorted(self.reminder_offsets):
            raise ValueError("reminder_offsets must be in ascending order")


# 6.1節: (a)7日構成 - 検知時1通+終了3日前(検知から4日後)に1通の計2通構成。
DUNNING_CONFIG_A_7DAYS = DunningConfig(
    name="a_7days", grace_period_days=7, reminder_offsets=(4,)
)

# 6.2節: (b)14日構成 - 検知時1通+中間地点(検知から7日後)+終了3日前(検知から11日後)の計3通構成。
DUNNING_CONFIG_B_14DAYS = DunningConfig(
    name="b_14days", grace_period_days=14, reminder_offsets=(7, 11)
)


@dataclass(frozen=True)
class DunningEvent:
    event_type: str  # "detected" / "reminder" / "suspended"
    scheduled_at: datetime
    label: str = ""  # "midpoint" / "final"(event_type == "reminder"の場合のみ)


def compute_dunning_schedule(detected_at: datetime, config: DunningConfig) -> list[DunningEvent]:
    """3節の3段階(通常運用→猶予期間→制限モード)に沿って、決済失敗検知時刻を起点に
    通知イベントの予定時刻を並べる。実際の送信要否は各Cloud Scheduler実行時に
    (未送信 かつ 予定時刻を過ぎている かつ 猶予期間中に決済成功していない)で判定する
    想定で、本関数はその予定表自体の算出のみを担う(reminder_scheduler.pyの
    compute_initial_reminder_target()と同じ役割分担)。
    """
    events = [DunningEvent(event_type="detected", scheduled_at=detected_at)]

    offsets = config.reminder_offsets
    labels = ("final",) if len(offsets) == 1 else ("midpoint",) * (len(offsets) - 1) + ("final",)
    for offset, label in zip(offsets, labels):
        events.append(
            DunningEvent(
                event_type="reminder",
                scheduled_at=detected_at + timedelta(days=offset),
                label=label,
            )
        )

    events.append(
        DunningEvent(
            event_type="suspended",
            scheduled_at=detected_at + timedelta(days=config.grace_period_days),
        )
    )
    return events


_MESSAGE_DETECTED = """【予約とれる君】お支払いの確認をお願いします

いつもご利用ありがとうございます。
今回のお支払い手続きが完了できませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、サービスは通常通りご利用いただけます。
{猶予日数}日以内にお支払い方法をご確認・更新いただけますようお願いします。

▼ お支払い方法を確認する
{決済ページURL}"""

_MESSAGE_REMINDER_FINAL = """【予約とれる君】お支払い確認のお願い(再送)

お支払い手続きが未完了のままです。
このままですと{リマインド送付日数前}日後に新規のご予約受付を一時停止いたします
(すでに確定済みのご予約・前日リマインドには影響しません)。

▼ お支払い方法を確認する
{決済ページURL}"""

# 6.2節: 14日構成のみで送る中間地点の状況確認(payment-failure-dunning-design.mdに
# 文面自体はまだ無かったため、4節の他文言・tone-and-manner-guideline.mdの標準トーンに
# 合わせて本モジュールで新規に書き下した)。
_MESSAGE_REMINDER_MIDPOINT = """【予約とれる君】お支払い確認の状況をご案内します

お支払い手続きがまだ完了していないようです。
検知から{経過日数}日が経過しました。猶予期間は残り{残り日数}日です。
お手数ですが、お支払い方法のご確認・更新をお願いします。

▼ お支払い方法を確認する
{決済ページURL}"""

_MESSAGE_SUSPENDED = """【予約とれる君】新規予約受付を一時停止しました

お支払い手続きが確認できないため、新規のご予約受付を停止しました。
すでに確定済みのご予約と前日リマインドは引き続き通常通り対応します。

お支払い方法をご確認いただければ、確認完了後に自動で新規受付を再開します。

▼ お支払い方法を確認する
{決済ページURL}"""

_MESSAGE_RECOVERED = """【予約とれる君】お支払いを確認しました

お支払い手続きが完了しました。ご不便をおかけしました。
新規のご予約受付を再開しましたので、引き続きよろしくお願いします。"""


def render_dunning_message(
    event: DunningEvent, config: DunningConfig, payment_page_url: str
) -> str:
    """DunningEventと選択済みconfig(A/B)から、4節の文言テンプレートを埋めて返す。
    決済成功による復旧通知(event_type対象外)はrender_recovery_message()を使う。
    """
    if event.event_type == "detected":
        return _MESSAGE_DETECTED.format(
            猶予日数=config.grace_period_days, 決済ページURL=payment_page_url
        )
    if event.event_type == "reminder" and event.label == "final":
        days_before_end = config.grace_period_days - config.reminder_offsets[-1]
        return _MESSAGE_REMINDER_FINAL.format(
            リマインド送付日数前=days_before_end, 決済ページURL=payment_page_url
        )
    if event.event_type == "reminder" and event.label == "midpoint":
        elapsed_days = config.reminder_offsets[0]
        remaining_days = config.grace_period_days - elapsed_days
        return _MESSAGE_REMINDER_MIDPOINT.format(
            経過日数=elapsed_days, 残り日数=remaining_days, 決済ページURL=payment_page_url
        )
    if event.event_type == "suspended":
        return _MESSAGE_SUSPENDED.format(決済ページURL=payment_page_url)
    raise ValueError(f"unknown event: {event.event_type}/{event.label}")


def render_recovery_message() -> str:
    """4節末尾: 決済成功による復旧時の文言。config(A/B)に依存しないため引数なし。"""
    return _MESSAGE_RECOVERED
