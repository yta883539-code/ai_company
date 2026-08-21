#!/usr/bin/env python3
"""
dormant-mode-renotification-design.md 1節(猶予期間)・2節(再通知頻度表)・
3節(通知文言)・4.2節(復旧通知文言)で設計した、休止モード移行タイミングの算出と
再通知イベントのスケジュール計算・文言生成を、実行可能なコードに落とし込んだもの。

位置づけ:
- 実際の決済代行サービスの選定・Cloud Schedulerによる定期実行の実装配線は
  引き続きオーナー承認待ち(pending-approval.md参照)。
- 本モジュールは dunning_notification_scheduler.py と同じ役割分担
  (判断・整形ロジックのみを切り出し、Webhook受信・Firestore書き込み・LINE送信は行わない)。

設計の参照元: dormant-mode-renotification-design.md 1節・2節・3節・4.2節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# 1節: 利用実績レポート送信から休止モード移行までの猶予期間(暫定値、実測データ無し)。
GRACE_PERIOD_DAYS = 3

# 2節: 休止モード移行時点を起点とした再通知オフセット(日数)。4通目で打ち切り、以降は送らない。
RENOTIFY_OFFSETS_DAYS = (7, 30, 90)
RENOTIFY_LABELS = ("2nd", "3rd", "final")


@dataclass(frozen=True)
class DormantEvent:
    event_type: str  # "transitioned"(1通目=移行時) / "renotify"(2〜4通目)
    scheduled_at: datetime
    label: str = ""  # "2nd" / "3rd" / "final"(event_type == "renotify"の場合のみ)


def compute_dormant_schedule(report_sent_at: datetime) -> list[DormantEvent]:
    """1節の3日間の猶予期間・2節の再通知表(移行時/7日後/30日後/90日後)に沿って、
    利用実績レポート送信時刻を起点に休止モード関連イベントの予定時刻を並べる。
    実際の送信要否は各実行時に(未送信 かつ 予定時刻を過ぎている かつ
    その間にプラン選択が完了していない)で判定する想定で、本関数はその予定表自体の
    算出のみを担う(compute_dunning_schedule()と同じ役割分担)。
    """
    transitioned_at = report_sent_at + timedelta(days=GRACE_PERIOD_DAYS)
    events = [DormantEvent(event_type="transitioned", scheduled_at=transitioned_at)]
    for offset, label in zip(RENOTIFY_OFFSETS_DAYS, RENOTIFY_LABELS):
        events.append(
            DormantEvent(
                event_type="renotify",
                scheduled_at=transitioned_at + timedelta(days=offset),
                label=label,
            )
        )
    return events


# message-tone-variants.mdの3トーン(formal/standard/casual)出し分けを適用する。
# dunning_notification_scheduler.py同様、engine.pyに依存しないローカル複製とする。
MESSAGE_TONES = ("formal", "standard", "casual")


def _render_by_tone(tone: str, variants: dict) -> str:
    """未知のtone値はstandardにフォールバックする(engine.py側と同じ安全側の挙動)。"""
    return variants.get(tone, variants["standard"])


_MESSAGE_TRANSITIONED = {
    "formal": """【予約とれる君】休止モードへの移行について

無料トライアルの利用実績レポートからプランのご選択がなかったため、
本日より休止モードへ移行いたしました。

・新規のご予約受付を停止いたしました(お客様には自動で受付停止中の旨をご案内いたします)
・すでに確定済みのご予約と前日リマインドは引き続き通常通り対応いたします
・データは削除いたしませんので、いつでもプランをお選びいただければ再開いただけます

▼ プランを見る・登録する
{決済ページURL}

ご不明点はこのトークルームにご返信くださいませ。""",
    "standard": """【予約とれる君】休止モードへの移行について

無料トライアルの利用実績レポートからプランのご選択がなかったため、
本日より休止モードへ移行しました。

・新規のご予約受付を停止しました(お客様には自動で受付停止中の旨をご案内します)
・すでに確定済みのご予約と前日リマインドは引き続き通常通り対応します
・データは削除されませんので、いつでもプランをお選びいただければ再開できます

▼ プランを見る・登録する
{決済ページURL}

ご不明点はこのトークルームにご返信ください。""",
    "casual": """【予約とれる君】休止モードへの移行について

無料トライアルの利用実績レポートからプランの選択がなかったので、
本日から休止モードに移行しました。

・新規のご予約受付を停止しました(お客様には自動で受付停止中の旨を案内します)
・すでに確定済みのご予約と前日リマインドはこれまで通り対応します
・データは削除されないので、いつでもプランを選べば再開できます!

▼ プランを見る・登録する
{決済ページURL}

わからないことがあれば、このトークルームに返信してくださいね🙆""",
}

_MESSAGE_RENOTIFY_2ND = {
    "formal": """【予約とれる君】休止モードが継続しております

休止モードへの移行から1週間が経過いたしました。
現在も新規のご予約受付を停止した状態でございます。

再開をご希望の場合は、下記からいつでもプランをお選びいただけますようお願い申し上げます。

▼ プランを見る・登録する
{決済ページURL}""",
    "standard": """【予約とれる君】休止モードが継続しています

休止モードへの移行から1週間が経過しました。
現在も新規のご予約受付を停止した状態です。

再開をご希望の場合は、下記からいつでもプランをお選びいただけます。

▼ プランを見る・登録する
{決済ページURL}""",
    "casual": """【予約とれる君】休止モードが続いています

休止モードへの移行から1週間が経ちました。
今も新規のご予約受付を停止した状態です。

再開したい場合は、いつでも下記からプランを選べます!

▼ プランを見る・登録する
{決済ページURL}""",
}

_MESSAGE_RENOTIFY_3RD = {
    "formal": """【予約とれる君】休止モードが継続しております(30日経過)

休止モードへの移行から1か月が経過いたしました。
確定済みのご予約・前日リマインドは引き続き通常通り対応いたしておりますが、
新規のご予約受付は停止したままでございます。

再開をご希望の場合は、下記からいつでもプランをお選びいただけますようお願い申し上げます。
{決済ページURL}""",
    "standard": """【予約とれる君】休止モードが継続しています(30日経過)

休止モードへの移行から1か月が経過しました。
確定済みのご予約・前日リマインドは引き続き通常通り対応していますが、
新規のご予約受付は停止したままです。

再開をご希望の場合は、下記からいつでもプランをお選びいただけます。
{決済ページURL}""",
    "casual": """【予約とれる君】休止モードが続いています(30日経過)

休止モードへの移行から1か月が経ちました。
確定済みのご予約・前日リマインドはこれまで通り対応していますが、
新規のご予約受付は停止したままです。

再開したい場合は、いつでも下記からプランを選べます!
{決済ページURL}""",
}

_MESSAGE_RENOTIFY_FINAL = {
    "formal": """【予約とれる君】休止モードのご案内(最終)

休止モードへの移行から3か月が経過いたしました。
これ以降、休止モードに関する定期のご案内はお送りいたしません。

このままご利用にならない場合も、確定済みのご予約・前日リマインドの対応は継続いたします。
再開をご希望になった際は、いつでも下記からプランをお選びいただけますようお願い申し上げます。

▼ プランを見る・登録する
{決済ページURL}""",
    "standard": """【予約とれる君】休止モードのご案内(最終)

休止モードへの移行から3か月が経過しました。
これ以降、休止モードに関する定期のご案内はお送りしません。

このままご利用にならない場合も、確定済みのご予約・前日リマインドの対応は継続します。
再開をご希望になった際は、いつでも下記からプランをお選びいただけます。

▼ プランを見る・登録する
{決済ページURL}""",
    "casual": """【予約とれる君】休止モードのご案内(最終)

休止モードへの移行から3か月が経ちました。
これ以降、休止モードに関する定期のご案内は送りません。

このまま利用しない場合も、確定済みのご予約・前日リマインドの対応は続けます。
再開したくなったら、いつでも下記からプランを選べます!

▼ プランを見る・登録する
{決済ページURL}""",
}

# 4.2節: 休止モード(trial_unselected)からの復旧通知。billing-upgrade-flow-design.md 3節
# (初回登録)・payment-failure-dunning-design.md 4節(決済失敗からの復旧)とは別文言。
_MESSAGE_RECOVERY = {
    "formal": """【予約とれる君】新規予約受付を再開いたしました

プランのご登録が完了いたしました。ご不便をおかけし、誠に申し訳ございませんでした。
本日より新規のご予約受付を再開いたしました。

休止期間中に確定していたご予約・前日リマインドは、そのまま引き続き対応いたしております。

・次回請求日: {次回請求日}
・ご登録内容の確認・変更: {決済ページURL}(マイページ)

引き続きよろしくお願い申し上げます。""",
    "standard": """【予約とれる君】新規予約受付を再開しました

プランのご登録が完了しました。ご不便をおかけしました。
本日より新規のご予約受付を再開しました。

休止期間中に確定していたご予約・前日リマインドはそのまま引き続き対応しています。

・次回請求日: {次回請求日}
・ご登録内容の確認・変更: {決済ページURL}(マイページ)

引き続きよろしくお願いいたします。""",
    "casual": """【予約とれる君】新規予約受付を再開しました

プランの登録が完了しました。ご不便かけてすみませんでした。
本日から新規のご予約受付を再開しました!

休止期間中に確定していたご予約・前日リマインドは、そのまま引き続き対応しています。

・次回請求日: {次回請求日}
・登録内容の確認・変更: {決済ページURL}(マイページ)

引き続きよろしくお願いします。""",
}


def render_dormant_message(event: DormantEvent, payment_page_url: str, tone: str = "standard") -> str:
    """DormantEventから、3節の文言テンプレートを埋めて返す。
    toneはmessage-tone-variants.md準拠(formal/standard/casual、既定standard)。
    休止モードからの復旧通知はrender_dormant_recovery_message()を使う。
    """
    if event.event_type == "transitioned":
        template = _render_by_tone(tone, _MESSAGE_TRANSITIONED)
        return template.format(決済ページURL=payment_page_url)
    if event.event_type == "renotify" and event.label == "2nd":
        template = _render_by_tone(tone, _MESSAGE_RENOTIFY_2ND)
        return template.format(決済ページURL=payment_page_url)
    if event.event_type == "renotify" and event.label == "3rd":
        template = _render_by_tone(tone, _MESSAGE_RENOTIFY_3RD)
        return template.format(決済ページURL=payment_page_url)
    if event.event_type == "renotify" and event.label == "final":
        template = _render_by_tone(tone, _MESSAGE_RENOTIFY_FINAL)
        return template.format(決済ページURL=payment_page_url)
    raise ValueError(f"unknown event: {event.event_type}/{event.label}")


def render_dormant_recovery_message(
    next_billing_date: str, payment_page_url: str, tone: str = "standard"
) -> str:
    """4.2節: 休止モード(suspension_reason == "trial_unselected")からの復旧通知。
    next_billing_dateは決済代行サービスのWebhookペイロードの値をそのまま渡す想定
    (billing-upgrade-flow-design.md 3節と同じ扱い)。
    """
    template = _render_by_tone(tone, _MESSAGE_RECOVERY)
    return template.format(次回請求日=next_billing_date, 決済ページURL=payment_page_url)
