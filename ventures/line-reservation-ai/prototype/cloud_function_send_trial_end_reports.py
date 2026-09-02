#!/usr/bin/env python3
"""
trial-end-scheduler-design.md 5節「Cloud Function E本体の実装」に対応した、
trial_end_scheduler.py(送信要否判定)とtrial_end_report_scheduler.py
(render_trial_end_report_message、メッセージ整形)・LinePushClient
(実送信、cloud_function_process_event.pyで定義済み)を実際につなぐ
「Cloud Function E: send_trial_end_reports」の配線を実装したもの。

位置づけ:
- 実際のCloud Scheduler新規作成・Firestoreからの実集計・LINE公式アカウント開設・
  LINE Push Message API接続はいずれもオーナー承認待ち(pending-approval.md参照)。
  本モジュールはcloud_function_send_reminders.py・
  course-set-pasha/trial_end_scheduler.py send_trial_end_notifications()と同じく、
  実クラウド接続なしで検証可能な「配線ロジック自体」を実装する。
- auto_handled_inquiry_count(自動対応できたお問い合わせ件数)は
  trial_end_report_scheduler.py TrialUsageSummaryのdocstring通り、集計処理自体
  (Firestoreクエリ・NotificationLogAggregatorとの結線)は本モジュールのスコープ外とし、
  呼び出し元が集計済みの値を渡す想定とする(booking_countをtrial_end_scheduler.py
  StoreTrialStateがそのまま受け取る設計、trial-end-scheduler-design.md 3節と同じ方針)。
- report_sent_writer(TrialEndReportSentAtWriter)は、engine.py
  ConversationFlowStateMachine.mark_trial_end_report_sent(now)をそのまま満たす
  Protocolとした。同クラスは店舗ごとに1インスタンスのため(design 1節前提)、
  course-set-pasha側のようにuser_id引数を取らない。

設計の参照元: trial-end-scheduler-design.md 5節
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol, Sequence

sys.path.insert(0, str(Path(__file__).parent))

from checkout_session import (  # noqa: E402
    DEFAULT_LIFF_ID,
    build_liff_checkout_link,
)
from cloud_function_process_event import (  # noqa: E402
    InMemoryLinePushClient,
    LinePushClient,
    LinePushDeliveryError,
)
from trial_end_report_scheduler import (  # noqa: E402
    TrialUsageSummary,
    render_trial_end_report_message,
)
from trial_end_scheduler import (  # noqa: E402
    StoreTrialState,
    select_due_trial_end_reports,
)


class TrialEndReportSentAtWriter(Protocol):
    def mark_trial_end_report_sent(self, now: datetime) -> None:
        ...


@dataclass(frozen=True)
class TrialEndReportCandidate:
    """1店舗ぶんの送信要否判定・メッセージ整形の両方に必要な入力をまとめたもの。
    trial_end_scheduler.StoreTrialStateの4フィールド(選定ロジック用)に加え、
    trial_end_report_scheduler.TrialUsageSummaryが必要とするauto_handled_inquiry_count・
    送信先(店舗オーナーのLINE user_id)・メッセージトーン
    (owner-settings-wireframe.md「メッセージトーン」設定)・冪等性書き込み先を持つ。
    """

    store_id: str
    trial_start_at: Optional[datetime]
    trial_end_report_sent_at: Optional[datetime]
    booking_count: int
    auto_handled_inquiry_count: int
    owner_line_user_id: str
    report_sent_writer: TrialEndReportSentAtWriter
    message_tone: str = "standard"

    def to_trial_state(self) -> StoreTrialState:
        return StoreTrialState(
            store_id=self.store_id,
            trial_start_at=self.trial_start_at,
            trial_end_report_sent_at=self.trial_end_report_sent_at,
            booking_count=self.booking_count,
        )


class TrialEndReportEngineState(Protocol):
    """ConversationFlowStateMachineが満たす読み取り用インターフェース(店舗ごとに1インスタンス、
    trial-end-scheduler-design.md 1節前提)。TrialEndReportSentAtWriterの書き込みメソッドに
    加え、build_trial_end_report_candidates()が読み出す2getterをまとめたもの。"""

    def get_trial_start_at(self) -> Optional[datetime]:
        ...

    def get_trial_end_report_sent_at(self) -> Optional[datetime]:
        ...

    def mark_trial_end_report_sent(self, now: datetime) -> None:
        ...


class TrialEndReportBookingCountReader(Protocol):
    """InMemoryBookingRecordStoreが満たすインターフェース(全店舗共有の1インスタンス、
    store_idで引く)。"""

    def count_confirmed_bookings(self, store_id: str) -> int:
        ...


@dataclass(frozen=True)
class TrialEndReportStoreInputs:
    """1店舗ぶんの`build_trial_end_report_candidates()`への入力をまとめたもの。engineは
    ConversationFlowStateMachine、booking_store・log_aggregatorはengine.pyの
    InMemoryBookingRecordStore・NotificationLogAggregatorをそのまま想定する。

    owner_line_user_id・message_toneは店舗設定(オーナー設定画面)由来の値で、その集計・
    永続化元(StoreProfileStore等への追加)は本モジュールのスコープ外
    (呼び出し元が解決済みの値を渡す想定、cloud_function_send_dunning_notifications.pyの
    DunningStateと同じ方針)。
    """

    store_id: str
    engine: TrialEndReportEngineState
    booking_store: TrialEndReportBookingCountReader
    log_aggregator: "NotificationLogAggregatorLike"
    owner_line_user_id: str
    message_tone: str = "standard"


class NotificationLogAggregatorLike(Protocol):
    """engine.NotificationLogAggregatorが満たすインターフェース(店舗ごとに1インスタンス、
    trial-end-scheduler-design.md 5節前提)。auto_handled_faq_countはプロパティではなく
    公開属性として実装されているため、Protocolでも属性として宣言する。"""

    auto_handled_faq_count: int


def build_trial_end_report_candidates(
    stores: Sequence[TrialEndReportStoreInputs],
) -> list[TrialEndReportCandidate]:
    """trial-end-scheduler-design.md 5節に残っていた「候補組み立て処理(呼び出し元)への
    実配線」のうち、実Firestore接続なしで検証可能な部分に対応する。course-set-pasha/
    trial_end_scheduler.pyの`build_trial_user_states()`と同じ役割分担で、これまで
    AutoHandledFaqCountWiringTests・BookingCountWiringTestsがそれぞれ個別の値を手動で
    TrialEndReportCandidateへ渡して検証していたのに対し、実際のConversationFlowStateMachine・
    InMemoryBookingRecordStore・NotificationLogAggregatorの3インスタンスから1店舗ぶんの
    TrialEndReportCandidateを一括で組み立てる関数自体がこれまで存在しなかった配線漏れを
    解消する。
    """
    candidates: list[TrialEndReportCandidate] = []
    for store in stores:
        candidates.append(
            TrialEndReportCandidate(
                store_id=store.store_id,
                trial_start_at=store.engine.get_trial_start_at(),
                trial_end_report_sent_at=store.engine.get_trial_end_report_sent_at(),
                booking_count=store.booking_store.count_confirmed_bookings(store.store_id),
                auto_handled_inquiry_count=store.log_aggregator.auto_handled_faq_count,
                owner_line_user_id=store.owner_line_user_id,
                report_sent_writer=store.engine,
                message_tone=store.message_tone,
            )
        )
    return candidates


@dataclass
class SendTrialEndReportsResult:
    """1回のCloud Function E起動での送信結果(呼び出し側のログ・監視用、
    cloud_function_send_reminders.py SendRemindersResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # store_id
    failed: list[str] = field(default_factory=list)  # store_id(送信失敗、次回再試行)


def send_trial_end_reports(
    candidates: Sequence[TrialEndReportCandidate],
    now: datetime,
    push_client: LinePushClient,
    liff_id: str = DEFAULT_LIFF_ID,
) -> SendTrialEndReportsResult:
    """trial-end-scheduler-design.md 2節の全体構成図における「Cloud Function E:
    send_trial_end_reports」本体。引数のcandidatesは呼び出し元でFirestoreから読み取った
    候補一覧(booking_count・auto_handled_inquiry_countは集計済みの値)を想定し、
    実際の絞り込みはselect_due_trial_end_reports()が行う。

    決済ページURLは、checkout-initiation-flow-design.md 11節・
    store-id-resolution-and-owner-identity-design.md「残課題」対応として、候補ごとに
    `build_liff_checkout_link(candidate.store_id, liff_id=liff_id)`で個別に組み立てる
    (design 9節手順1が読み取る`store_id`クエリパラメータを埋め込むため、以前のような
    全店舗共通の固定プレースホルダ文字列では手順1が成立しない)。

    送信成功時のみcandidate.report_sent_writer.mark_trial_end_report_sent(now)を呼び、
    送信失敗時は呼ばない(4節の冪等性設計、send_reminders()と同じ「書き込み一発+次回実行時に
    自然に再送対象として残る」方式)。
    """
    result = SendTrialEndReportsResult()

    due_store_ids = {
        state.store_id
        for state in select_due_trial_end_reports(
            [candidate.to_trial_state() for candidate in candidates], now
        )
    }

    for candidate in candidates:
        if candidate.store_id not in due_store_ids:
            continue
        summary = TrialUsageSummary(
            booking_count=candidate.booking_count,
            auto_handled_inquiry_count=candidate.auto_handled_inquiry_count,
        )
        payment_page_url = build_liff_checkout_link(
            candidate.store_id, liff_id=liff_id
        )
        text = render_trial_end_report_message(
            summary, payment_page_url, tone=candidate.message_tone
        )
        try:
            push_client.send_message(candidate.owner_line_user_id, text)
        except LinePushDeliveryError:
            result.failed.append(candidate.store_id)
            continue
        candidate.report_sent_writer.mark_trial_end_report_sent(now)
        result.sent.append(candidate.store_id)

    return result


def _demo() -> None:
    class _StubWriter:
        def __init__(self) -> None:
            self.sent_at: Optional[datetime] = None

        def mark_trial_end_report_sent(self, now: datetime) -> None:
            if self.sent_at is None:
                self.sent_at = now

    now = datetime(2026, 9, 1, 4, 0, 0)

    # 1) 期間条件で到達: 送信される
    writer_a = _StubWriter()
    candidate_a = TrialEndReportCandidate(
        store_id="store-a",
        trial_start_at=datetime(2026, 8, 15, 10, 0, 0),
        trial_end_report_sent_at=None,
        booking_count=6,
        auto_handled_inquiry_count=4,
        owner_line_user_id="U-owner-a",
        report_sent_writer=writer_a,
        message_tone="casual",
    )

    # 2) いずれの条件も未到達: 送信されない
    writer_b = _StubWriter()
    candidate_b = TrialEndReportCandidate(
        store_id="store-b",
        trial_start_at=datetime(2026, 8, 30, 10, 0, 0),
        trial_end_report_sent_at=None,
        booking_count=2,
        auto_handled_inquiry_count=1,
        owner_line_user_id="U-owner-b",
        report_sent_writer=writer_b,
    )

    push = InMemoryLinePushClient()
    result = send_trial_end_reports([candidate_a, candidate_b], now, push)
    print(f"sent={result.sent}, failed={result.failed}")
    print(f"writer_a.sent_at={writer_a.sent_at}, writer_b.sent_at={writer_b.sent_at}")
    print(f"push: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
