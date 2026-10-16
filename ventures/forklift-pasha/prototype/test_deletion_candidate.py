#!/usr/bin/env python3
"""deletion_candidate.pyの境界値テスト(フェーズ152)。pure stdlibのみで実行する
(trial_management.py等と同じ方針)。

実行方法: python3 prototype/test_deletion_candidate.py
"""

import sys
from datetime import datetime, timedelta

from deletion_candidate import (
    EmailSenderProtocol,
    UNREACHABLE_REASON_NO_EMAIL,
    UNREACHABLE_REASON_SEND_FAILED,
    UnreachableDeletionCandidate,
    list_deletion_candidates,
    list_unreachable_deletion_candidates,
    render_deletion_candidate_final_confirmation_message,
    render_unreachable_deletion_candidates_report,
    select_due_deletion_candidate_final_confirmations,
    send_deletion_candidate_final_confirmations,
)
from trial_management import InMemoryFleetOperatorStore


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


class _StaticEmailSender(EmailSenderProtocol):
    """テスト用: 渡した集合に含まれるinternal_idのみ送信成功とする。"""

    def __init__(self, succeed_for):
        self._succeed_for = set(succeed_for)

    def send(self, internal_id, email):
        if email is None:
            return False
        return internal_id in self._succeed_for


def main():
    results = []
    now = datetime(2026, 10, 15, 22, 0, 0)

    # --- list_deletion_candidates: 未解約は対象外 ---
    store = InMemoryFleetOperatorStore()
    store.set_email("op1", "op1@example.com")
    results.append(_check(
        "未解約は削除候補にならない",
        list_deletion_candidates(store, now),
        [],
    ))

    # --- list_deletion_candidates: 解約後365日未満は対象外 ---
    store.set_canceled_at("op1", now - timedelta(days=364))
    results.append(_check(
        "解約後365日未満は削除候補にならない",
        list_deletion_candidates(store, now),
        [],
    ))

    # --- list_deletion_candidates: 解約後365日以上で対象 ---
    store.set_canceled_at("op1", now - timedelta(days=365))
    results.append(_check(
        "解約後365日以上は削除候補になる(境界値)",
        list_deletion_candidates(store, now),
        ["op1"],
    ))

    # --- list_deletion_candidates: 複数事業者をinternal_id昇順で返す ---
    store.set_email("op0", "op0@example.com")
    store.set_canceled_at("op0", now - timedelta(days=400))
    results.append(_check(
        "複数候補はinternal_id昇順",
        list_deletion_candidates(store, now),
        ["op0", "op1"],
    ))

    # --- select_due_deletion_candidate_final_confirmations: 未送信・未判定のみ対象 ---
    results.append(_check(
        "送信前は両方が対象",
        select_due_deletion_candidate_final_confirmations(store, ["op0", "op1"]),
        ["op0", "op1"],
    ))

    # --- send_deletion_candidate_final_confirmations: 成功/失敗の振り分け ---
    sender = _StaticEmailSender(succeed_for=["op0"])
    send_result = send_deletion_candidate_final_confirmations(
        store, ["op0", "op1"], sender, now,
    )
    results.append(_check("送信成功した候補", send_result.sent, ["op0"]))
    results.append(_check("送信失敗(連絡不能)した候補", send_result.unreachable, ["op1"]))
    results.append(_check(
        "送信済みはsent_atが設定される",
        store.get_deletion_confirmation_sent_at("op0"),
        now,
    ))
    results.append(_check(
        "送信失敗はunreachable_atが設定される",
        store.get_deletion_confirmation_unreachable_at("op1"),
        now,
    ))

    # --- select_due_deletion_candidate_final_confirmations: 再送しない(冪等) ---
    results.append(_check(
        "送信済み・連絡不能いずれも再送対象から除外される",
        select_due_deletion_candidate_final_confirmations(store, ["op0", "op1"]),
        [],
    ))

    # --- email未設定は常に連絡不能扱い ---
    store2 = InMemoryFleetOperatorStore()
    store2.set_canceled_at("op2", now - timedelta(days=400))
    send_result2 = send_deletion_candidate_final_confirmations(
        store2, ["op2"], _StaticEmailSender(succeed_for=["op2"]), now,
    )
    results.append(_check(
        "email未設定は送信成功リストに含まれない(常に連絡不能)",
        send_result2.unreachable,
        ["op2"],
    ))

    # --- list_unreachable_deletion_candidates / render ---
    results.append(_check(
        "連絡不能候補が0件なら専用の1行を返す",
        render_unreachable_deletion_candidates_report([]),
        "連絡不能の削除候補事業者はありません。",
    ))
    unreachable_candidates = list_unreachable_deletion_candidates(store, now)
    results.append(_check(
        "連絡不能候補一覧はop1のみ",
        [c.internal_id for c in unreachable_candidates],
        ["op1"],
    ))
    results.append(_check(
        "メールアドレス登録済みでの送信失敗はsend_failed理由コードが記録される",
        store.get_deletion_confirmation_unreachable_reason("op1"),
        UNREACHABLE_REASON_SEND_FAILED,
    ))
    results.append(_check(
        "メールアドレス未登録はno_email理由コードが記録される",
        store2.get_deletion_confirmation_unreachable_reason("op2"),
        UNREACHABLE_REASON_NO_EMAIL,
    ))
    results.append(_check(
        "理由コード追加前に記録された候補はunreachable_reasonがNoneのまま不明表示にフォールバックする",
        UnreachableDeletionCandidate(
            internal_id="op_legacy", unreachable_at=now, days_since_unreachable=0,
        ).unreachable_reason_label,
        "不明(本フィールド追加前に記録された候補)",
    ))
    report = render_unreachable_deletion_candidates_report(unreachable_candidates)
    results.append(_check("レポートに件数が含まれる", "1件" in report, True))
    results.append(_check("レポートに自動削除でない旨の注記が含まれる", "個別に削除可否を" in report, True))
    results.append(_check("レポートに連絡不能理由が含まれる", "理由: 送信失敗" in report, True))

    # --- render_deletion_candidate_final_confirmation_message: 空でない文面 ---
    results.append(_check(
        "最終確認メール文面の下書きが空でない",
        len(render_deletion_candidate_final_confirmation_message()) > 0,
        True,
    ))

    if all(results):
        print(f"\n全{len(results)}件パス")
        return 0
    failed = len([r for r in results if not r])
    print(f"\n{failed}件失敗 / 全{len(results)}件")
    return 1


if __name__ == "__main__":
    sys.exit(main())
