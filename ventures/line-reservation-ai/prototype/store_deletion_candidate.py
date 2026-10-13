#!/usr/bin/env python3
"""
store-deletion-candidate-final-confirmation-design.md(フェーズ続き317)4節・5節で設計した、
休止モード店舗レコードの削除候補選定ロジックと最終確認通知文言を、実行可能なコードに
落とし込んだもの。

位置づけ:
- dormant_mode_scheduler.pyと同じ役割分担(判断・整形ロジックのみを切り出し、Firestore
  読み取り・LINE送信の実配線はcloud_function_send_store_deletion_confirmations.pyが担う)。
- aircon-pasha/course-set-pasha/kura-pashaの`deletion_candidate.py`は別コレクション
  (`user_profile/{user_id}`等)を逆引きする構成だが、本ventureは店舗情報を単一の
  `stores/{storeId}`ドキュメントに集約する構成(design 2節)のため、選定ロジックは
  単一の店舗状態を直接参照できる形で実装する(別コレクションへの逆引きが不要)。
- design 5節の簡略化方針(1回の送信失敗で連絡不能とみなす、「直近4回の履歴を遡る」判定は
  行わない)に従う。メール代替経路は実送信サービス接続(オーナー承認待ち)まで引き続き
  モック止まりのため、本モジュールでは一切呼び出さない。

設計の参照元: store-deletion-candidate-final-confirmation-design.md 4節・5節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Sequence

# 4節: 休止モード4通目(final)送信からさらに1年、無反応が続いた場合に削除候補化する。
DELETION_CANDIDATE_DELAY = timedelta(days=365)

STORE_DELETION_FINAL_CONFIRMATION_MESSAGE = (
    "【予約とれる君】データ保有についてのご案内\n"
    "\n"
    "休止モードへの移行後、長期間にわたりご利用・ご返信の確認が取れなかったため、"
    "プライバシーポリシーに基づき、お預かりしている店舗情報の保有継続について"
    "確認のご連絡です。\n"
    "\n"
    "引き続き保有をご希望の場合やサービスの再開をご希望の場合は、このトークルームへの"
    "ご返信、または改めてのプランご登録にてご連絡ください。\n"
    "特にご連絡がない場合、当社の定めるデータ保存期間ポリシーに従って取り扱います。"
)


def render_store_deletion_final_confirmation_message() -> str:
    """文言をそのまま返す(aircon-pashaのrender_deletion_candidate_final_confirmation_
    message()と同じく、具体的な削除予定日には言及しない設計。design 5節は削除実行バッチ
    自体を設計対象外としているため)。"""
    return STORE_DELETION_FINAL_CONFIRMATION_MESSAGE


@dataclass(frozen=True)
class StoreDeletionCandidateState:
    """design 4節の選定条件が参照する、店舗1件分の最小限の状態。

    呼び出し側(cloud_function_send_store_deletion_confirmations.StoreDeletionState等)は
    本クラスのフィールド名と同じ属性を持つ別のクラスをそのまま渡せる(dormant_mode_
    scheduler.DormantScheduleStateと同じ、ダックタイピングを前提にした役割分担)。
    """

    store_id: str
    dormant_renotify_count: int
    dormant_final_renotify_sent_at: Optional[datetime]
    suspension_reason: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    store_deletion_confirmation_sent_at: Optional[datetime] = None


def is_store_deletion_candidate(state: StoreDeletionCandidateState, now: datetime) -> bool:
    """design 4節の4条件をすべて満たすかを判定する。

    (1) 休止モード4通目(final)まで送信済み(dormant_renotify_count == 3)。
    (2) final送信から365日以上経過。
    (3) 最終確認が未送信(冪等性ガード)。
    (4) final送信後に「反応」(stripe_customer_id設定、またはsuspension_reasonがNoneへ
        復帰)があったとみなせる状態になっていないこと。
    """
    if state.dormant_renotify_count != 3:
        return False
    if state.dormant_final_renotify_sent_at is None:
        return False
    if now - state.dormant_final_renotify_sent_at < DELETION_CANDIDATE_DELAY:
        return False
    if state.store_deletion_confirmation_sent_at is not None:
        return False
    if state.stripe_customer_id is not None:
        return False
    if state.suspension_reason is None:
        return False
    return True


def list_store_deletion_candidates(
    states: Sequence[StoreDeletionCandidateState], now: datetime
) -> list[str]:
    """design 4節で「次回実装候補」としていた`list_store_deletion_candidates()`本体。
    is_store_deletion_candidate()を満たすstore_idをstore_id昇順で返す(呼び出し順の
    非決定性を避けるため、aircon-pasha/deletion_candidate.list_deletion_candidates()と
    同じ方針)。
    """
    return sorted(
        state.store_id for state in states if is_store_deletion_candidate(state, now)
    )
