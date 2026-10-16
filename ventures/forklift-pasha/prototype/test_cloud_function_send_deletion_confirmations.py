#!/usr/bin/env python3
"""cloud_function_send_deletion_confirmations.pyのmain()境界値テスト(フェーズ153)。

cloud_function_send_trial_end_emails.pyのテスト(フェーズ147)と同じ構成で、
runtime_dependencies省略時・注入時それぞれの挙動、および`_UnconfiguredEmailSender`が
安全側のフォールバック(常に送信失敗=unreachable)として働くことを確認する。

実行方法: python3 prototype/test_cloud_function_send_deletion_confirmations.py
"""

import sys
from datetime import datetime, timedelta, timezone

from cloud_function_send_deletion_confirmations import (
    main as send_deletion_confirmations_main,
)
from trial_management import InMemoryFleetOperatorStore


class _StubRequest:
    """main(request)のテスト用スタブ。Cloud Scheduler起動時、本関数はrequestの
    いずれのフィールドも参照しないため(cloud_function_send_deletion_confirmations.main()
    docstring参照)、空のオブジェクトで十分。"""


class _StaticEmailSender:
    """テスト用: 渡した集合に含まれるinternal_idのみ送信成功とする
    (test_deletion_candidate.py `_StaticEmailSender`と同型)。"""

    def __init__(self, succeed_for):
        self._succeed_for = set(succeed_for)

    def send(self, internal_id, email):
        if email is None:
            return False
        return internal_id in self._succeed_for


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- main(): runtime_dependencies省略時は常に200(既定のInMemoryストアは空なので
    # 削除候補も存在しない) ---
    body, status = send_deletion_confirmations_main(_StubRequest())
    results.append(_check("main(): runtime_dependencies省略時は200", status, 200))
    results.append(_check("main(): runtime_dependencies省略時のレスポンスボディ", body, "OK"))

    # --- main(): runtime_dependencies注入時、365日超の解約済み事業者が送信成功する ---
    now = datetime.now(timezone.utc)
    injected_store = InMemoryFleetOperatorStore()
    injected_store.set_email("fo_injected_1", "owner@example.com")
    injected_store.set_canceled_at("fo_injected_1", now - timedelta(days=366))
    injected_dependencies = {
        "store": injected_store,
        "email_sender": _StaticEmailSender(succeed_for={"fo_injected_1"}),
    }
    injected_body, injected_status = send_deletion_confirmations_main(
        _StubRequest(), runtime_dependencies=injected_dependencies
    )
    results.append(_check("main(): runtime_dependencies注入時も200", injected_status, 200))
    results.append(_check(
        "main(): 365日超の解約済み事業者はsent_atが設定される",
        injected_store.get_deletion_confirmation_sent_at("fo_injected_1") is not None,
        True,
    ))
    results.append(_check(
        "main(): 送信成功時はunreachable_atは設定されない",
        injected_store.get_deletion_confirmation_unreachable_at("fo_injected_1"),
        None,
    ))

    # --- main(): runtime_dependencies注入時でも365日未満の解約済み事業者は対象外 ---
    not_due_store = InMemoryFleetOperatorStore()
    not_due_store.set_email("fo_injected_2", "owner2@example.com")
    not_due_store.set_canceled_at("fo_injected_2", now - timedelta(days=30))
    second_dependencies = {
        "store": not_due_store,
        "email_sender": _StaticEmailSender(succeed_for={"fo_injected_2"}),
    }
    send_deletion_confirmations_main(_StubRequest(), runtime_dependencies=second_dependencies)
    results.append(_check(
        "main(): 365日未満(解約から30日)の事業者には送信されない",
        not_due_store.get_deletion_confirmation_sent_at("fo_injected_2"),
        None,
    ))

    # --- main(): 既定のget_deletion_confirmation_runtime_dependencies()は
    # _UnconfiguredEmailSenderを使うため、候補が存在すれば常にunreachable_atが設定される
    # (安全側のフォールバック、design docstring参照) ---
    from cloud_function_send_deletion_confirmations import (
        get_deletion_confirmation_runtime_dependencies,
    )

    deps = get_deletion_confirmation_runtime_dependencies()
    deps["store"].set_email("fo_injected_3", "owner3@example.com")
    deps["store"].set_canceled_at("fo_injected_3", now - timedelta(days=400))
    send_deletion_confirmations_main(_StubRequest(), runtime_dependencies=deps)
    results.append(_check(
        "main(): 既定の_UnconfiguredEmailSenderは常に送信失敗(unreachable_at設定)",
        deps["store"].get_deletion_confirmation_unreachable_at("fo_injected_3") is not None,
        True,
    ))
    results.append(_check(
        "main(): _UnconfiguredEmailSender利用時はsent_atは設定されない",
        deps["store"].get_deletion_confirmation_sent_at("fo_injected_3"),
        None,
    ))

    passed = sum(1 for r in results if r)
    print(f"\n{len(results)}件中{passed}件成功")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
