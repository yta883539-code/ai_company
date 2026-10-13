#!/usr/bin/env python3
"""
store-deletion-candidate-final-confirmation-design.md 5節で設計した、削除候補店舗への
最終確認送信(store_deletion_candidate.list_store_deletion_candidates()・
render_store_deletion_final_confirmation_message())と、LinePushClient(実送信、
cloud_function_process_event.pyで定義済み)を実際につなぐ「削除候補の最終確認送信」の
配線を実装したもの。

位置づけ:
- cloud_function_send_dormant_notifications.pyと同じ役割分担・同じアーキテクチャ
  (本体ロジックと実配線を分離する「薄いmain(request)」構成は採らず、本ファイル自体が
  依存注入でテスト可能な送信本体を直接提供する)を踏襲する。aircon-pashaフェーズ310の
  横断点検が確認したとおり、本venture(line-reservation-ai)はCloud Scheduler起動の
  バッチ系Cloud Functionsについて「本体を別関数に分離しmain(request)だけが薄い配線を
  担う」構成を採らず、各`cloud_function_*.py`ファイル自身が本体ロジックを直接定義する
  構成を一貫して採用しているため、store-deletion-candidate-final-confirmation-
  design.md 5節が参照したaircon-pasha/course-set-pasha型の薄いラッパー構成ではなく、
  本venture自身の既存の構成(dormant_mode_scheduler.py本体 + cloud_function_send_
  dormant_notifications.py配線、の2ファイル分割)に合わせて実装した。
- design 5節の簡略化方針どおり、owner_line_user_id宛のLINE push送信を1回試み、失敗
  (LinePushDeliveryError)した場合は直ちに連絡不能として扱う(「直近4回の履歴を遡る」
  判定は行わない)。owner_line_user_id自体が未設定の店舗(owner-notification-channel-
  design.mdのowner_user_id特定フローが未完了のまま削除候補化に至ったケース)も、同様に
  連絡不能として扱う。
- メール代替経路は実送信サービス接続(SendGrid等のアカウント作成、オーナー承認待ち)まで
  引き続きモック止まりのため、本モジュールでは一切呼び出さない(design 5節どおり)。
- 実際のCloud Scheduler設定(月次1回想定)・実LINE Push Message API接続は引き続き
  オーナー承認待ち(pending-approval.md参照、新規の承認待ち事項ではない)。本モジュールは
  実クラウド接続なしで検証可能な配線ロジック自体を実装する。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    LinePushClient,
    LinePushDeliveryError,
)
from store_deletion_candidate import (  # noqa: E402
    UNREACHABLE_REASON_LINE_PUSH_DELIVERY_FAILED,
    UNREACHABLE_REASON_OWNER_LINE_USER_ID_NOT_SET,
    list_store_deletion_candidates,
    render_store_deletion_final_confirmation_message,
)


@dataclass
class StoreDeletionState:
    """1店舗ぶんの削除候補関連状態(store_deletion_candidate.StoreDeletionCandidateStateと
    同じフィールド名に、送信・状態書き込みに必要な項目を加えたもの)。

    store_deletion_candidate.StoreDeletionCandidateStateはfrozenのため送信成功時の
    書き換えができない。list_store_deletion_candidates()はダックタイピングで属性を
    読むだけなので、frozenでない本クラスをそのまま渡して使い回す(cloud_function_send_
    dormant_notifications.StoreDormantStateと同じ考え方)。
    """

    store_id: str
    dormant_renotify_count: int
    dormant_final_renotify_sent_at: Optional[datetime]
    owner_line_user_id: Optional[str] = None
    suspension_reason: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    store_deletion_confirmation_sent_at: Optional[datetime] = None
    store_deletion_confirmation_unreachable_at: Optional[datetime] = None
    store_deletion_confirmation_unreachable_reason: Optional[str] = None


@dataclass
class SendStoreDeletionConfirmationsResult:
    """1回のバッチ実行での送信結果(呼び出し側のログ・監視用、他スケジューラの
    SendResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # LINE push送達成功
    marked_unreachable: list[str] = field(default_factory=list)  # 連絡不能扱い


def send_store_deletion_confirmations(
    stores: list[StoreDeletionState], now: datetime, push_client: LinePushClient
) -> SendStoreDeletionConfirmationsResult:
    """store-deletion-candidate-final-confirmation-design.md 5節の本体。引数のstoresは
    呼び出し元でFirestoreから読み取った店舗一覧全体を想定し、対象の絞り込みは
    list_store_deletion_candidates()が行う(他スケジューラと異なり、本ventureは削除候補
    判定条件自体が絞り込みロジックを兼ねるため、呼び出し側で事前絞り込みを行わない)。

    owner_line_user_idが未設定、またはLINE push送信が失敗した場合はいずれも
    store_deletion_confirmation_unreachable_atを記録するのみに留め(design「オーナーが
    対話セッションで個別に削除可否を判断する運用」のための状態記録)、削除そのものへは
    一切進めない。
    """
    result = SendStoreDeletionConfirmationsResult()
    candidate_ids = set(list_store_deletion_candidates(stores, now))

    for store in stores:
        if store.store_id not in candidate_ids:
            continue

        if store.owner_line_user_id is None:
            store.store_deletion_confirmation_unreachable_at = now
            store.store_deletion_confirmation_unreachable_reason = (
                UNREACHABLE_REASON_OWNER_LINE_USER_ID_NOT_SET
            )
            result.marked_unreachable.append(store.store_id)
            continue

        try:
            push_client.send_message(
                store.owner_line_user_id,
                render_store_deletion_final_confirmation_message(),
            )
        except LinePushDeliveryError:
            store.store_deletion_confirmation_unreachable_at = now
            store.store_deletion_confirmation_unreachable_reason = (
                UNREACHABLE_REASON_LINE_PUSH_DELIVERY_FAILED
            )
            result.marked_unreachable.append(store.store_id)
            continue

        store.store_deletion_confirmation_sent_at = now
        result.sent.append(store.store_id)

    return result


def _demo() -> None:
    from cloud_function_process_event import InMemoryLinePushClient

    final_sent_at = datetime(2026, 8, 20, 10, 0)
    now = final_sent_at + timedelta(days=365)

    due_store = StoreDeletionState(
        store_id="store-1",
        dormant_renotify_count=3,
        dormant_final_renotify_sent_at=final_sent_at,
        owner_line_user_id="owner-1",
        suspension_reason="trial_unselected",
    )
    unreachable_store = StoreDeletionState(
        store_id="store-2",
        dormant_renotify_count=3,
        dormant_final_renotify_sent_at=final_sent_at,
        owner_line_user_id=None,
        suspension_reason="trial_unselected",
    )
    not_yet_due_store = StoreDeletionState(
        store_id="store-3",
        dormant_renotify_count=3,
        dormant_final_renotify_sent_at=now,
        owner_line_user_id="owner-3",
        suspension_reason="trial_unselected",
    )

    push = InMemoryLinePushClient()
    result = send_store_deletion_confirmations(
        [due_store, unreachable_store, not_yet_due_store], now, push
    )
    print("sent:", result.sent)
    print("marked_unreachable:", result.marked_unreachable)
    print("push count:", len(push.sent))


if __name__ == "__main__":
    _demo()
