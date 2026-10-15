#!/usr/bin/env python3
"""deletion-candidate-design.md(フェーズ152)で設計した削除候補の洗い出し・最終確認送信・
連絡不能オーナーレビュー用レポートを実行可能なコードに落とし込んだもの。

位置づけ: 他venture(aircon-pasha・course-set-pasha・kura-pasha・line-reservation-ai)の
`deletion_candidate.py`/`deletion_candidate_final_confirmation.py`と同じ役割だが、本venture
は`stripe_webhook.py`(フェーズ129・130)が既に`canceled_at`を冪等に設定・クリアしている
ため、別途の`deletion_candidate_at`フィールドやstale-event-guardは不要で、
`canceled_at + 365日`を都度計算する関数のみで足りる(design 2節)。実際のメール送信
サービス接続・削除実行バッチのデプロイはオーナー承認待ちの範囲として残す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Protocol

from trial_management import FleetOperatorStoreProtocol

# design 3節: data-retention-policy.mdの保存期間ポリシー(他venture同様の暫定値)
_DELETION_CANDIDATE_DELAY = timedelta(days=365)


def list_deletion_candidates(
    store: FleetOperatorStoreProtocol, now: datetime,
) -> List[str]:
    """design 4節: `canceled_at`が設定済みかつ`now >= canceled_at + 365日`の
    internal_id一覧をinternal_id昇順で返す(読み出し専用。削除・通知は行わない)。
    """
    return sorted(
        internal_id
        for internal_id in store.all_internal_ids()
        if (canceled_at := store.get_canceled_at(internal_id)) is not None
        and now >= canceled_at + _DELETION_CANDIDATE_DELAY
    )


def render_deletion_candidate_final_confirmation_message() -> str:
    """削除候補となった事業者へ送るメール本文の下書き(design 4節)。実際の送信文面
    最終稿化・送信元ドメイン確定はメール送信サービス接続(オーナー承認待ち)後の課題として
    残す。"""
    return (
        "ご契約から一定期間が経過し、現在ご利用を解約されている状態が続いております。"
        "このままご利用のご予定がない場合、保存しているデータ(事業者情報・車両情報)を"
        "削除いたします。再開をご希望の場合やご不明点がある場合は、本メールにご返信ください。"
    )


class EmailSenderProtocol(Protocol):
    """実メール送信サービス接続前の検証用インターフェース(design 4節)。"""

    def send(self, internal_id: str, email: "str | None") -> bool:
        """送信に成功したら`True`、失敗(email未設定含む)なら`False`を返す。"""
        ...


def select_due_deletion_candidate_final_confirmations(
    store: FleetOperatorStoreProtocol, candidates: List[str],
) -> List[str]:
    """design 4節: 送信済み・連絡不能いずれかが既に設定済みの候補を除外する
    (再送しない、他venture同種関数と同じ冪等方針)。"""
    return [
        internal_id
        for internal_id in candidates
        if store.get_deletion_confirmation_sent_at(internal_id) is None
        and store.get_deletion_confirmation_unreachable_at(internal_id) is None
    ]


@dataclass
class SendDeletionCandidateFinalConfirmationsResult:
    """`send_deletion_candidate_final_confirmations()`の結果(design 4節)。"""

    sent: List[str] = field(default_factory=list)
    unreachable: List[str] = field(default_factory=list)


def send_deletion_candidate_final_confirmations(
    store: FleetOperatorStoreProtocol,
    candidates: List[str],
    email_sender: EmailSenderProtocol,
    now: datetime,
) -> SendDeletionCandidateFinalConfirmationsResult:
    """design 4節: `candidates`(通常は`select_due_deletion_candidate_final_
    confirmations()`で絞り込んだ一覧)それぞれについて`email_sender.send()`を呼び、
    成功なら`sent_at`、失敗(email未設定含む)なら`unreachable_at`を設定する。
    """
    result = SendDeletionCandidateFinalConfirmationsResult()
    for internal_id in candidates:
        email = store.get_email(internal_id)
        if email_sender.send(internal_id, email):
            store.set_deletion_confirmation_sent_at(internal_id, now)
            result.sent.append(internal_id)
        else:
            store.set_deletion_confirmation_unreachable_at(internal_id, now)
            result.unreachable.append(internal_id)
    return result


@dataclass
class UnreachableDeletionCandidate:
    """`list_unreachable_deletion_candidates()`が返す1件分(design 4節)。"""

    internal_id: str
    unreachable_at: datetime
    days_since_unreachable: int


def list_unreachable_deletion_candidates(
    store: FleetOperatorStoreProtocol, now: datetime,
) -> List[UnreachableDeletionCandidate]:
    """design 4節: `deletion_confirmation_unreachable_at`が設定済みの事業者一覧を
    internal_id昇順で返す(読み取り専用レポート生成用)。"""
    results: List[UnreachableDeletionCandidate] = []
    for internal_id in sorted(store.all_internal_ids()):
        unreachable_at = store.get_deletion_confirmation_unreachable_at(internal_id)
        if unreachable_at is None:
            continue
        results.append(
            UnreachableDeletionCandidate(
                internal_id=internal_id,
                unreachable_at=unreachable_at,
                days_since_unreachable=(now - unreachable_at).days,
            )
        )
    return results


def render_unreachable_deletion_candidates_report(
    candidates: List[UnreachableDeletionCandidate],
) -> str:
    """design 4節: オーナーが対話セッションで削除可否を判断するための読み取り専用
    レポート(自動削除・自動送信は一切行わない旨の注記を含む、他venture同種関数と
    同じ方針)。"""
    if not candidates:
        return "連絡不能の削除候補事業者はありません。"
    lines = [f"連絡不能の削除候補事業者: {len(candidates)}件"]
    for candidate in candidates:
        lines.append(
            f"- {candidate.internal_id}: "
            f"判定日時={candidate.unreachable_at.isoformat()} "
            f"(連絡不能判定から{candidate.days_since_unreachable}日経過)"
        )
    lines.append(
        "本リストは自動削除の対象ではなく、オーナーが対話セッションで個別に削除可否を"
        "判断します。"
    )
    return "\n".join(lines)
