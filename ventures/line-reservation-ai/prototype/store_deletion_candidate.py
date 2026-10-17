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
from typing import Optional, Protocol, Sequence

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
    store_deletion_confirmation_unreachable_at: Optional[datetime] = None
    store_deletion_confirmation_unreachable_reason: Optional[str] = None


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


# store-deletion-candidate-unreachable-owner-review-design.md 3節が「次回候補」としていた
# 連絡不能の理由区分。send_store_deletion_confirmations()が書き込む値と一致させる。
UNREACHABLE_REASON_OWNER_LINE_USER_ID_NOT_SET = "owner_line_user_id_not_set"
UNREACHABLE_REASON_LINE_PUSH_DELIVERY_FAILED = "line_push_delivery_failed"

_UNREACHABLE_REASON_LABELS = {
    UNREACHABLE_REASON_OWNER_LINE_USER_ID_NOT_SET: "オーナーのLINEユーザーID未設定",
    UNREACHABLE_REASON_LINE_PUSH_DELIVERY_FAILED: "LINE push送信失敗",
}
_UNREACHABLE_REASON_UNKNOWN_LABEL = "不明(本フィールド追加前に記録された候補)"


@dataclass(frozen=True)
class UnreachableStoreDeletionCandidate:
    """store-deletion-candidate-unreachable-owner-review-design.md 3節の読み取り専用
    レポート行。オーナーが対話セッションで個別に削除可否を判断するための一覧表示にのみ
    使う(削除実行・自動送信は一切行わない)。"""

    store_id: str
    store_deletion_confirmation_unreachable_at: datetime
    days_since_unreachable: int
    unreachable_reason: Optional[str] = None

    @property
    def unreachable_reason_label(self) -> str:
        """理由コードを対話セッション表示用の日本語ラベルに変換する。本フィールド追加前
        (フェーズ続き319以前)に連絡不能と記録された候補はunreachable_reasonがNoneのまま
        なので、既知の限界どおり「不明」として表示する(design 3節参照)。"""
        if self.unreachable_reason is None:
            return _UNREACHABLE_REASON_UNKNOWN_LABEL
        return _UNREACHABLE_REASON_LABELS.get(self.unreachable_reason, self.unreachable_reason)


class StoreDeletionConfirmationUnreachableStoreProtocol(Protocol):
    """「クリア配線」(aircon-pashaフェーズ175・フェーズ321、course-set-pashaフェーズ300の
    横展開)が使う、`store_deletion_confirmation_unreachable_at`/
    `store_deletion_confirmation_unreachable_reason`の読み書きのみを要求する最小限の
    Protocol。`store_profile_store.StoreProfileStoreProtocol`
    (ひいては`InMemoryStoreProfileStore`)はこれらのメソッドを既に持つため、構造的に
    (duck typing)本Protocolを満たす。"""

    def get_store_deletion_confirmation_unreachable_at(
        self, store_id: str
    ) -> Optional[datetime]:
        ...

    def set_store_deletion_confirmation_unreachable_at(
        self, store_id: str, value: Optional[datetime]
    ) -> None:
        ...

    def get_store_deletion_confirmation_unreachable_reason(
        self, store_id: str
    ) -> Optional[str]:
        ...

    def set_store_deletion_confirmation_unreachable_reason(
        self, store_id: str, value: Optional[str]
    ) -> None:
        ...


def clear_store_deletion_confirmation_unreachable_at(
    store: StoreDeletionConfirmationUnreachableStoreProtocol, store_id: str,
) -> bool:
    """オーナーの再フォロー時に呼ぶ「クリア配線」(aircon-pashaフェーズ321・
    course-set-pashaフェーズ300と同じ考え方の本venture版)。

    `send_store_deletion_confirmations()`はオーナーのLINE push送信が1回失敗した時点で
    (「直近4回の履歴を遡る」判定は行わない簡略化方針、本ファイル冒頭の位置づけ参照)
    `store_deletion_confirmation_unreachable_at`を設定するが、これをクリアする経路が
    従来存在しなかったため、一度ブロックされたオーナーが再フォローしても削除候補が
    「連絡不能」のまま塩漬けになり、次回バッチでも`store_deletion_confirmation_sent_at`が
    未設定である限り`is_store_deletion_candidate()`に再評価され続けるだけで、正常な
    LINE push経路には二度と戻れない問題があった。本関数は、設定済みの場合のみ
    `store_deletion_confirmation_unreachable_at`・`store_deletion_confirmation_unreachable_
    reason`の両方をクリアし、変更があったかどうか(`True`/`False`)を返す(aircon-pasha/
    course-set-pashaの同名関数と同じ、呼び出し側がログ確認できる冪等設計)。未設定
    (そもそも一度も連絡不能になったことがない、または既にクリア済み)の場合は何もせず
    `False`を返す。

    呼び出し配線は`cloud_function_process_event.ConversationEventProcessor.
    process_follow_event()`のオーナー再フォロー分岐(`clear_blocked_but_billing_owner_
    notified_at()`と並ぶ位置)から行う。本ventureは店舗情報を単一の`stores/{storeId}`
    ドキュメントに集約する構成(design 2節)のため、aircon-pasha・course-set-pashaと異なり
    別引数(`deletion_store`等)を追加する必要はなく、既存の`store_profile`をそのまま渡せる。
    """
    if store.get_store_deletion_confirmation_unreachable_at(store_id) is None:
        return False
    store.set_store_deletion_confirmation_unreachable_at(store_id, None)
    store.set_store_deletion_confirmation_unreachable_reason(store_id, None)
    return True


def list_unreachable_store_deletion_candidates(
    states: Sequence[StoreDeletionCandidateState], now: datetime
) -> list[UnreachableStoreDeletionCandidate]:
    """store-deletion-candidate-unreachable-owner-review-design.md 3節の選定ロジック。

    data-retention-policy.mdが「連絡不能」と定める、LINE push・メール代替経路のいずれでも
    最終確認ができなかった店舗(store_deletion_confirmation_unreachable_atが設定済み)を
    store_id昇順で一覧化する。本関数は読み取り専用で、削除実行や通知送信は行わない。
    """
    candidates = [
        UnreachableStoreDeletionCandidate(
            store_id=state.store_id,
            store_deletion_confirmation_unreachable_at=state.store_deletion_confirmation_unreachable_at,
            days_since_unreachable=(
                now - state.store_deletion_confirmation_unreachable_at
            ).days,
            unreachable_reason=state.store_deletion_confirmation_unreachable_reason,
        )
        for state in states
        if state.store_deletion_confirmation_unreachable_at is not None
    ]
    return sorted(candidates, key=lambda candidate: candidate.store_id)


def render_unreachable_store_deletion_candidates_report(
    candidates: Sequence[UnreachableStoreDeletionCandidate],
) -> str:
    """store-deletion-candidate-unreachable-owner-review-design.md 4節のレポート文言。
    オーナーとの対話セッション内で表示することを想定し(外部への自動送信は行わない)、
    自動削除の対象ではないこと・個別判断が必要であることを明示する。
    """
    if not candidates:
        return "連絡不能の削除候補店舗はありません。"

    lines = [
        f"連絡不能の削除候補店舗: {len(candidates)}件(オーナーによる個別確認が必要)",
        "",
    ]
    for candidate in candidates:
        lines.append(
            f"- {candidate.store_id}: 連絡不能判定から{candidate.days_since_unreachable}日経過"
            f"(判定日時: {candidate.store_deletion_confirmation_unreachable_at.isoformat()}、"
            f"理由: {candidate.unreachable_reason_label})"
        )
    lines.append("")
    lines.append(
        "本リストは自動削除の対象ではありません。オーナーが対話セッションで個別に"
        "削除可否を判断してください(data-retention-policy.md参照)。"
    )
    return "\n".join(lines)
