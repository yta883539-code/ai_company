#!/usr/bin/env python3
"""
store-deletion-execution-design.md(フェーズ続き323)で設計した、削除候補に対する実際の
削除実行のオーケストレーションロジック、および削除実行対象の統合レポートを実装したもの。

位置づけ:
- store_deletion_candidate.py(選定ロジック・連絡不能レポート)の続きとして、削除実行
  そのものを扱う。
- design 2節の方針どおり、本モジュールはいかなるスケジューラ・Cloud Functionsからも
  呼び出されない(そのための`main(request)`配線を意図的に用意しない)。削除実行は
  本リポジトリとの対話セッションでオーナーが`store_id`を指定して直接関数を呼ぶ想定。
- 実際のFirestore接続・ページング・WriteBatch実装は実Firestore接続後(オーナー承認待ち)
  の課題として残る(design 4節)。本モジュールは依存注入可能なProtocolとInMemory実装で、
  削除順序・再試行可能性・confirmed_by_ownerガードのみを検証する。

設計の参照元: store-deletion-execution-design.md 3節・4節
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, Sequence

from store_deletion_candidate import (
    StoreDeletionCandidateState,
    UnreachableStoreDeletionCandidate,
    list_store_deletion_candidates,
    list_unreachable_store_deletion_candidates,
)

# data-retention-policy.md「サブコレクションとの削除順序」節の採用方針どおりの順序。
# stores/{storeId}本体ドキュメントは必ずこの5件を削除した後に削除する。
SUBCOLLECTION_DELETION_ORDER = (
    "bookingSlots",
    "conversations",
    "notificationLogEntries",
    "notificationLogUniqueTopics",
    "escalationWindows",
)


class DeletionNotConfirmedError(Exception):
    """confirmed_by_owner=Trueが明示的に渡されなかった場合に発生させる例外。

    design 4節の安全策: 将来本関数が誤って条件判定なしに(スケジューラ等から)呼ばれても、
    オーナーの明示的な意思表示が伴わない限り実削除に進ませないためのガード。
    """


class SubcollectionDeleterProtocol(Protocol):
    """1サブコレクション分の全件削除を担うアダプタのインターフェース。

    実Firestore接続後は`collection.list_documents()`によるページング+`WriteBatch`
    (上限500件/バッチ)で実装する想定(design 4節)。本フェーズではInMemory実装のみ用意する。
    """

    name: str

    def delete_all(self) -> int:
        """配下の全ドキュメントを削除し、削除件数を返す。"""


class DeletionTargetStoreProtocol(Protocol):
    """`stores/{storeId}`本体ドキュメントの削除を担うアダプタのインターフェース。"""

    def delete(self) -> None:
        """本体ドキュメントを削除する。"""


@dataclass
class InMemorySubcollectionDeleter:
    """テスト・デモ用のInMemory実装。削除済みフラグと件数を保持する。"""

    name: str
    document_count: int = 0
    deleted: bool = field(default=False, init=False)

    def delete_all(self) -> int:
        self.deleted = True
        count = self.document_count
        self.document_count = 0
        return count


@dataclass
class InMemoryDeletionTargetStore:
    """テスト・デモ用のInMemory実装。削除済みフラグを保持する。"""

    store_id: str
    deleted: bool = field(default=False, init=False)

    def delete(self) -> None:
        self.deleted = True


@dataclass(frozen=True)
class DeletionExecutionResult:
    """execute_store_deletion()の実行結果。再試行可能性を保つため、途中で例外が発生した
    場合でもそれまでに完了したサブコレクション名を保持する(design 4節)。"""

    store_id: str
    completed_subcollections: tuple[str, ...]
    store_document_deleted: bool
    deleted_document_counts: dict

    @property
    def is_fully_deleted(self) -> bool:
        return (
            self.store_document_deleted
            and len(self.completed_subcollections) == len(SUBCOLLECTION_DELETION_ORDER)
        )


def execute_store_deletion(
    store_id: str,
    store_doc: DeletionTargetStoreProtocol,
    subcollections: Sequence[SubcollectionDeleterProtocol],
    *,
    confirmed_by_owner: bool,
) -> DeletionExecutionResult:
    """削除候補1件を実際に削除する(design 4節)。

    呼び出し側は、オーナーが対話セッションで当該store_idの削除を明示的に指示した場合のみ
    confirmed_by_owner=Trueを渡すこと。それ以外の経路(スケジューラ・自動判定等)からは
    一切呼び出さない設計とする(design 2節)。

    subcollectionsはSUBCOLLECTION_DELETION_ORDERと同じ順序・同じ名前の集合を渡すこと
    (順序の妥当性チェックのため)。
    """
    if not confirmed_by_owner:
        raise DeletionNotConfirmedError(
            f"store_id={store_id!r}: confirmed_by_owner=Trueが渡されていないため削除を"
            "実行しません(オーナーが対話セッションで個別に指示した場合のみ実行する設計)。"
        )

    given_names = tuple(deleter.name for deleter in subcollections)
    if given_names != SUBCOLLECTION_DELETION_ORDER:
        raise ValueError(
            "subcollectionsはSUBCOLLECTION_DELETION_ORDERと同じ順序・同じ名前の集合で"
            f"渡す必要があります。渡された順序: {given_names!r}"
        )

    completed: list[str] = []
    deleted_counts: dict = {}
    # 子(5サブコレクション)を先に全件削除し、最後に親ドキュメントを削除する
    # (data-retention-policy.md「サブコレクションとの削除順序」節の採用方針)。
    # 途中で例外が発生しても、stores/{storeId}本体が残っている限りstore_idの手がかりを
    # 失わず、completed_subcollectionsを見て再実行時にスキップできる。
    for deleter in subcollections:
        deleted_counts[deleter.name] = deleter.delete_all()
        completed.append(deleter.name)

    store_doc.delete()

    return DeletionExecutionResult(
        store_id=store_id,
        completed_subcollections=tuple(completed),
        store_document_deleted=True,
        deleted_document_counts=deleted_counts,
    )


def render_deletion_execution_review_report(
    states: Sequence[StoreDeletionCandidateState], now: datetime
) -> str:
    """design 3節の統合レポート。削除実行対象を3区分でオーナーに提示する読み取り専用の
    レポートで、本関数自体は削除を一切実行しない。"""

    unreachable = list_unreachable_store_deletion_candidates(states, now)
    unreachable_ids = {candidate.store_id for candidate in unreachable}
    # list_store_deletion_candidates()はstore_deletion_confirmation_unreachable_atを
    # 見ないため、既に連絡不能と判定済みの店舗(次回スケジューラ実行時の再送対象として
    # 残り続ける)も含まれてしまう。2区分目(連絡不能)と重複表示しないよう、本レポートの
    # 3区分目では除外する。
    new_candidates = [
        store_id
        for store_id in list_store_deletion_candidates(states, now)
        if store_id not in unreachable_ids
    ]
    sent_awaiting_response = sorted(
        state.store_id
        for state in states
        if state.store_deletion_confirmation_sent_at is not None
        and state.store_deletion_confirmation_unreachable_at is None
    )

    lines = ["削除実行レビューレポート", ""]

    lines.append(f"1. 最終確認送信済み・未応答: {len(sent_awaiting_response)}件")
    for store_id in sent_awaiting_response:
        lines.append(f"   - {store_id}")

    lines.append(f"2. 連絡不能(LINE push失敗・owner_user_id未設定等): {len(unreachable)}件")
    for candidate in unreachable:
        lines.append(
            f"   - {candidate.store_id}: 連絡不能判定から{candidate.days_since_unreachable}日経過"
            f"(理由: {candidate.unreachable_reason_label})"
        )

    lines.append(f"3. (参考)最終確認未送信の新規削除候補: {len(new_candidates)}件")

    lines.append("")
    lines.append(
        "本リストは自動削除の対象ではありません。削除を実行する場合は、対話セッションで"
        "個別の店舗IDを指定してオーナーが明示的に指示してください(execute_store_deletion()は"
        "confirmed_by_owner=Trueを明示的に渡した場合のみ削除を行います)。"
    )
    return "\n".join(lines)


def _demo() -> None:
    now = datetime(2027, 1, 1)
    store = InMemoryDeletionTargetStore(store_id="store-demo")
    subcollections = [
        InMemorySubcollectionDeleter(name=name, document_count=3)
        for name in SUBCOLLECTION_DELETION_ORDER
    ]
    result = execute_store_deletion(
        "store-demo", store, subcollections, confirmed_by_owner=True
    )
    print(result)
    print(store.deleted)


if __name__ == "__main__":
    _demo()
