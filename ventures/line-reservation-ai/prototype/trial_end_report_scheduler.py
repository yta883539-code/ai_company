#!/usr/bin/env python3
"""
billing-upgrade-flow-design.md 1節(トライアル終了時の利用実績レポート+プラン案内
メッセージ)を、実行可能なコードに落とし込んだもの。

位置づけ:
- トライアル終了トリガー(14日経過 or 予約20件到達)の検知・実際のCloud Scheduler/
  Webhookへの配線、Firestoreからの実利用実績集計、LINE Push Message API接続は、
  GCPプロジェクト作成・LINE公式アカウント開設を伴うため引き続きオーナー承認待ち
  (pending-approval.md参照)。
- 本モジュールはdunning_notification_scheduler.py/dormant_mode_scheduler.pyと同じ
  役割分担(判断・整形ロジックのみを切り出す)で、集計済みの利用実績値を受け取って
  メッセージ文言を組み立てる部分のみを担う。

設計の参照元: billing-upgrade-flow-design.md 1節
"""

from __future__ import annotations

from dataclasses import dataclass

# 1節: 「目安対応時間の根拠値は今後の課題として残す」とされていた仮定値。
# 出典なしの一般的な仮定(1件あたり約7〜8分の手作業を代替)の中間値を採用。
# 実測データが得られ次第、この定数の見直しをunit-economics-estimate.mdの前例に倣い検討する。
ASSUMED_MINUTES_SAVED_PER_AUTO_HANDLED_CASE = 7.5


@dataclass(frozen=True)
class TrialUsageSummary:
    """notification-log-classification-labels.md/booking-record-store-design.mdで
    集計可能な値を渡す想定の入力。集計処理自体(Firestoreクエリ)は本モジュールの
    スコープ外(design 1節「3項目は既に集計可能な値を流用する」)。
    """

    booking_count: int
    auto_handled_inquiry_count: int

    def __post_init__(self) -> None:
        if self.booking_count < 0:
            raise ValueError("booking_count must not be negative")
        if self.auto_handled_inquiry_count < 0:
            raise ValueError("auto_handled_inquiry_count must not be negative")

    @property
    def estimated_hours_saved(self) -> float:
        minutes = self.auto_handled_inquiry_count * ASSUMED_MINUTES_SAVED_PER_AUTO_HANDLED_CASE
        return round(minutes / 60, 1)


MESSAGE_TONES = ("formal", "standard", "casual")


def _render_by_tone(tone: str, variants: dict) -> str:
    """未知のtone値はstandardにフォールバックする
    (dunning_notification_scheduler.py/dormant_mode_scheduler.pyと同じ安全側の挙動)。"""
    return variants.get(tone, variants["standard"])


# design 1節のstandardトーン文言例をベースに、formal/casualを新規に書き下した
# (message-tone-variants.md準拠: casualは絵文字許容、formalは敬語をやや強める程度の差分)。
_MESSAGE_TRIAL_END_REPORT = {
    "formal": """【予約とれる君】無料トライアル終了のお知らせ

14日間の無料トライアルが終了いたしました。この間の利用実績は以下の通りでございます。

・処理した予約件数: {予約件数}件
・自動対応できたお問い合わせ: {自動対応件数}件
・概算の削減対応時間: 約{削減時間}時間

引き続きご利用いただく場合は、下記からプランをお選びくださいませ。
ご登録いただくまでは自動課金されませんのでご安心ください。

▼ プランを見る・登録する
{決済ページURL}

ご不明点はこのトークルームにご返信くださいませ。""",
    "standard": """【予約とれる君】無料トライアル終了のお知らせ

14日間の無料トライアルが終了しました。この間の利用実績は以下の通りです。

・処理した予約件数: {予約件数}件
・自動対応できたお問い合わせ: {自動対応件数}件
・概算の削減対応時間: 約{削減時間}時間

引き続きご利用いただく場合は、下記からプランをお選びください。
ご登録いただくまでは自動課金されませんのでご安心ください。

▼ プランを見る・登録する
{決済ページURL}

ご不明点はこのトークルームにご返信ください。""",
    "casual": """【予約とれる君】無料トライアル終了のお知らせ🎉

14日間の無料トライアルが終了しました!この間の利用実績はこちらです。

・処理した予約件数: {予約件数}件
・自動対応できたお問い合わせ: {自動対応件数}件
・概算の削減対応時間: 約{削減時間}時間

引き続き使う場合は、下記からプランを選んでください。
登録するまでは自動課金されないので安心してくださいね。

▼ プランを見る・登録する
{決済ページURL}

わからないことがあれば、このトークルームに返信してください!""",
}


def render_trial_end_report_message(
    summary: TrialUsageSummary, payment_page_url: str, tone: str = "standard"
) -> str:
    """design 1節のトライアル終了時メッセージを組み立てる。
    削減対応時間はTrialUsageSummary.estimated_hours_savedの仮定値をそのまま表示する
    (実測データが無いMVP段階の暫定表示、design 1節参照)。
    """
    template = _render_by_tone(tone, _MESSAGE_TRIAL_END_REPORT)
    hours = summary.estimated_hours_saved
    hours_text = str(int(hours)) if hours == int(hours) else str(hours)
    return template.format(
        予約件数=summary.booking_count,
        自動対応件数=summary.auto_handled_inquiry_count,
        削減時間=hours_text,
        決済ページURL=payment_page_url,
    )
