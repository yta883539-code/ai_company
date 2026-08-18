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


# message-tone-variants.mdの3トーン(formal/standard/casual)出し分けを適用する。
# 送信先は店舗オーナー自身(オーナー用トークルーム)だが、billing-upgrade-flow-design.md・
# dormant-mode-renotification-design.mdの前例(オーナー向け状態通知にも店舗設定の
# message_toneを適用する方針)を踏襲した。engine.pyのMESSAGE_TONES/_render_by_tone()と
# 同じ考え方だが、本モジュールはengine.pyに依存しない設計(reminder_scheduler.py同様)の
# ためローカルに複製する。
MESSAGE_TONES = ("formal", "standard", "casual")


def _render_by_tone(tone: str, variants: dict) -> str:
    """未知のtone値はstandardにフォールバックする(engine.py側と同じ安全側の挙動)。"""
    return variants.get(tone, variants["standard"])


_MESSAGE_DETECTED = {
    "formal": """【予約とれる君】お支払いの確認をお願いいたします

いつも大変お世話になっております。
今回のお支払い手続きが完了いたしませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、サービスは通常通りご利用いただけます。
{猶予日数}日以内にお支払い方法のご確認・更新をいただけますよう、お願い申し上げます。

▼ お支払い方法を確認する
{決済ページURL}""",
    "standard": """【予約とれる君】お支払いの確認をお願いします

いつもご利用ありがとうございます。
今回のお支払い手続きが完了できませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、サービスは通常通りご利用いただけます。
{猶予日数}日以内にお支払い方法をご確認・更新いただけますようお願いします。

▼ お支払い方法を確認する
{決済ページURL}""",
    "casual": """【予約とれる君】お支払いの確認をお願いします🙏

いつもありがとうございます!
今回のお支払い手続きが完了できませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、サービスはいつも通り使えます。
{猶予日数}日以内にお支払い方法の確認・更新をお願いします。

▼ お支払い方法を確認する
{決済ページURL}""",
}

_MESSAGE_REMINDER_FINAL = {
    "formal": """【予約とれる君】お支払い確認のお願い(再送)

お支払い手続きが未完了のままとなっております。
このままですと{リマインド送付日数前}日後に新規のご予約受付を一時停止いたしますので、
何卒お早めのご確認をお願い申し上げます
(すでに確定済みのご予約・前日リマインドには影響ございません)。

▼ お支払い方法を確認する
{決済ページURL}""",
    "standard": """【予約とれる君】お支払い確認のお願い(再送)

お支払い手続きが未完了のままです。
このままですと{リマインド送付日数前}日後に新規のご予約受付を一時停止いたします
(すでに確定済みのご予約・前日リマインドには影響しません)。

▼ お支払い方法を確認する
{決済ページURL}""",
    "casual": """【予約とれる君】お支払い確認のお願い(再送)🙏

お支払い手続きがまだ完了していません。
このままだと{リマインド送付日数前}日後に新規のご予約受付を一時停止しちゃいます
(すでに確定済みのご予約・前日リマインドには影響ないので安心してください!)。

▼ お支払い方法を確認する
{決済ページURL}""",
}

# 6.2節: 14日構成のみで送る中間地点の状況確認(payment-failure-dunning-design.mdに
# 文面自体はまだ無かったため、4節の他文言・tone-and-manner-guideline.mdの標準トーンに
# 合わせて本モジュールで新規に書き下した)。
_MESSAGE_REMINDER_MIDPOINT = {
    "formal": """【予約とれる君】お支払い確認の状況をご案内いたします

お支払い手続きがまだ完了していないようでございます。
検知から{経過日数}日が経過いたしました。猶予期間は残り{残り日数}日でございます。
お手数をおかけいたしますが、お支払い方法のご確認・更新をお願い申し上げます。

▼ お支払い方法を確認する
{決済ページURL}""",
    "standard": """【予約とれる君】お支払い確認の状況をご案内します

お支払い手続きがまだ完了していないようです。
検知から{経過日数}日が経過しました。猶予期間は残り{残り日数}日です。
お手数ですが、お支払い方法のご確認・更新をお願いします。

▼ お支払い方法を確認する
{決済ページURL}""",
    "casual": """【予約とれる君】お支払い確認の状況をお知らせします

お支払い手続きがまだ完了していないみたいです。
検知から{経過日数}日経過、猶予期間は残り{残り日数}日です!
お手数ですが、お支払い方法の確認・更新をお願いします🙏

▼ お支払い方法を確認する
{決済ページURL}""",
}

_MESSAGE_SUSPENDED = {
    "formal": """【予約とれる君】新規予約受付を一時停止いたしました

お支払い手続きが確認できなかったため、新規のご予約受付を停止いたしました。
すでに確定済みのご予約と前日リマインドは、引き続き通常通り対応いたします。

お支払い方法をご確認いただけましたら、確認完了後に新規受付を自動で再開いたします。

▼ お支払い方法を確認する
{決済ページURL}""",
    "standard": """【予約とれる君】新規予約受付を一時停止しました

お支払い手続きが確認できないため、新規のご予約受付を停止しました。
すでに確定済みのご予約と前日リマインドは引き続き通常通り対応します。

お支払い方法をご確認いただければ、確認完了後に自動で新規受付を再開します。

▼ お支払い方法を確認する
{決済ページURL}""",
    "casual": """【予約とれる君】新規予約受付を一時停止しました

お支払い手続きが確認できなかったので、新規のご予約受付を停止しました。
すでに確定済みのご予約と前日リマインドは、いつも通り対応します!

お支払い方法を確認してもらえれば、確認できたタイミングで新規受付を自動で再開します。

▼ お支払い方法を確認する
{決済ページURL}""",
}

_MESSAGE_RECOVERED = {
    "formal": """【予約とれる君】お支払いを確認いたしました

お支払い手続きが完了いたしました。ご不便をおかけし、誠に申し訳ございませんでした。
新規のご予約受付を再開いたしましたので、今後ともよろしくお願い申し上げます。""",
    "standard": """【予約とれる君】お支払いを確認しました

お支払い手続きが完了しました。ご不便をおかけしました。
新規のご予約受付を再開しましたので、引き続きよろしくお願いします。""",
    "casual": """【予約とれる君】お支払いを確認しました🙌

お支払い手続きが完了しました。ご不便かけてすみませんでした。
新規のご予約受付を再開したので、引き続きよろしくお願いします!""",
}

# 猶予期間中(制限モードに入る前)に決済が成功した場合の文言。_MESSAGE_RECOVEREDと違い
# 予約受付は一度も止まっていないため、「再開しました」とは書けない(書くと止まっていた
# という誤解を与える)。検知時通知を受け取ったオーナーに完了を伝えることだけが目的。
_MESSAGE_PAYMENT_CONFIRMED_IN_GRACE = {
    "formal": """【予約とれる君】お支払いを確認いたしました

お支払い手続きが完了いたしました。お手数をおかけし、誠に申し訳ございませんでした。
ご予約の受付はこれまでどおり継続しております。今後ともよろしくお願い申し上げます。""",
    "standard": """【予約とれる君】お支払いを確認しました

お支払い手続きが完了しました。お手数をおかけしました。
ご予約の受付はこれまでどおり続いています。引き続きよろしくお願いします。""",
    "casual": """【予約とれる君】お支払いを確認しました🙌

お支払い手続きが完了しました。お手数かけてすみませんでした。
ご予約の受付はこれまでどおり続いています。引き続きよろしくお願いします!""",
}


def render_dunning_message(
    event: DunningEvent, config: DunningConfig, payment_page_url: str, tone: str = "standard"
) -> str:
    """DunningEventと選択済みconfig(A/B)から、4節の文言テンプレートを埋めて返す。
    toneはmessage-tone-variants.md準拠(formal/standard/casual、既定standard、
    店舗のmessage_tone設定をそのまま渡す想定)。未知の値はstandardにフォールバックする。
    決済成功による復旧通知(event_type対象外)はrender_recovery_message()を使う。
    """
    if event.event_type == "detected":
        template = _render_by_tone(tone, _MESSAGE_DETECTED)
        return template.format(猶予日数=config.grace_period_days, 決済ページURL=payment_page_url)
    if event.event_type == "reminder" and event.label == "final":
        days_before_end = config.grace_period_days - config.reminder_offsets[-1]
        template = _render_by_tone(tone, _MESSAGE_REMINDER_FINAL)
        return template.format(リマインド送付日数前=days_before_end, 決済ページURL=payment_page_url)
    if event.event_type == "reminder" and event.label == "midpoint":
        elapsed_days = config.reminder_offsets[0]
        remaining_days = config.grace_period_days - elapsed_days
        template = _render_by_tone(tone, _MESSAGE_REMINDER_MIDPOINT)
        return template.format(
            経過日数=elapsed_days, 残り日数=remaining_days, 決済ページURL=payment_page_url
        )
    if event.event_type == "suspended":
        template = _render_by_tone(tone, _MESSAGE_SUSPENDED)
        return template.format(決済ページURL=payment_page_url)
    raise ValueError(f"unknown event: {event.event_type}/{event.label}")


def render_recovery_message(tone: str = "standard") -> str:
    """4節末尾: 制限モード(suspension_reason="payment_failed")からの復旧時の文言。
    config(A/B)には依存しないが、toneは他のrender_dunning_message()と同様に
    message-tone-variants.md準拠で受け取る。
    まだ制限モードに入っていない猶予期間中の決済成功には
    render_payment_confirmed_in_grace_message()を使う。
    """
    return _render_by_tone(tone, _MESSAGE_RECOVERED)


def render_payment_confirmed_in_grace_message(tone: str = "standard") -> str:
    """猶予期間中(制限モード移行前)に決済が成功した場合の文言。
    予約受付が止まっていない状態のため「再開しました」とは書かない。
    """
    return _render_by_tone(tone, _MESSAGE_PAYMENT_CONFIRMED_IN_GRACE)
