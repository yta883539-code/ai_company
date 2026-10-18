#!/usr/bin/env python3
"""cloud_function_send_payment_failure_reminders.pyのmain()境界値テスト(フェーズ171)。

cloud_function_send_trial_end_emails.main()(フェーズ147)と同じ依存注入パターン
(`runtime_dependencies`引数)をcloud_function_send_payment_failure_reminders.main()にも
適用したことを確認する。1回のCloud Scheduler起動でリマインド送信・運営者向け通知の2処理が
まとめて実行されることも併せて確認する。

実行方法: python3 prototype/test_cloud_function_send_payment_failure_reminders.py
"""

import sys
from datetime import datetime, timedelta, timezone

from cloud_function_send_payment_failure_reminders import (
    main as send_payment_failure_reminders_main,
)
from trial_end_email_scheduler import InMemoryEmailSenderClient
from trial_management import InMemoryFleetOperatorStore


class _StubRequest:
    """main(request)のテスト用スタブ。Cloud Scheduler起動時、本関数はrequestの
    いずれのフィールドも参照しないため(cloud_function_send_payment_failure_reminders.main()
    docstring参照)、空のオブジェクトで十分。"""


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- main(): runtime_dependencies省略時は常に200(既存挙動、回帰確認) ---
    body, status = send_payment_failure_reminders_main(_StubRequest())
    results.append(_check("main(): runtime_dependencies省略時は200", status, 200))
    results.append(_check("main(): runtime_dependencies省略時のレスポンスボディ", body, "OK"))

    # --- main(): runtime_dependencies注入時、リマインド対象へ実際に送信される ---
    now = datetime.now(timezone.utc)
    reminder_store = InMemoryFleetOperatorStore()
    reminder_store.set_email("fo_injected_1", "owner@example.com")
    reminder_store.set_upgraded_at("fo_injected_1", now - timedelta(days=60))
    reminder_store.set_payment_failure_detected_at("fo_injected_1", now - timedelta(days=4))
    reminder_email_client = InMemoryEmailSenderClient()
    reminder_dependencies = {
        "store": reminder_store,
        "email_client": reminder_email_client,
    }

    reminder_body, reminder_status = send_payment_failure_reminders_main(
        _StubRequest(), runtime_dependencies=reminder_dependencies
    )
    results.append(_check("main(): runtime_dependencies注入時も200", reminder_status, 200))
    results.append(_check(
        "main(): runtime_dependencies注入時、猶予期間4日経過の事業者へリマインドが"
        "実際に送信される(InMemoryEmailSenderClient.sentに反映)",
        len(reminder_email_client.sent),
        1,
    ))
    results.append(_check(
        "main(): リマインド送信先メールアドレスがreminder_storeの登録値と一致する",
        reminder_email_client.sent[0][0] if reminder_email_client.sent else None,
        "owner@example.com",
    ))

    # --- main(): runtime_dependencies注入時、制限モード移行済みの事業者には運営者通知も
    #     同一呼び出しで送信される(OWNER_NOTIFICATION_EMAIL_PLACEHOLDER宛) ---
    from payment_failure_reminder_scheduler import OWNER_NOTIFICATION_EMAIL_PLACEHOLDER

    owner_store = InMemoryFleetOperatorStore()
    owner_store.set_email("fo_injected_2", "owner2@example.com")
    owner_store.set_upgraded_at("fo_injected_2", now - timedelta(days=60))
    owner_store.set_payment_failure_detected_at("fo_injected_2", now - timedelta(days=9))
    owner_email_client = InMemoryEmailSenderClient()
    owner_dependencies = {
        "store": owner_store,
        "email_client": owner_email_client,
    }

    send_payment_failure_reminders_main(
        _StubRequest(), runtime_dependencies=owner_dependencies
    )
    owner_recipients = [sent[0] for sent in owner_email_client.sent]
    results.append(_check(
        "main(): 1回の起動で制限モード移行済み事業者向けの運営者通知も送信される",
        OWNER_NOTIFICATION_EMAIL_PLACEHOLDER in owner_recipients,
        True,
    ))
    results.append(_check(
        "main(): 制限モード移行済みの事業者には顧客向けリマインドは送信されない"
        "(猶予期間超過につきPAYMENT_SUSPENDED側の役割)",
        owner_store.get_payment_failure_reminder_sent_at("fo_injected_2"),
        None,
    ))

    # --- main(): runtime_dependencies注入時でも未到達の事業者にはいずれも送信されない ---
    not_due_store = InMemoryFleetOperatorStore()
    not_due_store.set_email("fo_injected_3", "owner3@example.com")
    not_due_store.set_upgraded_at("fo_injected_3", now - timedelta(days=60))
    not_due_store.set_payment_failure_detected_at("fo_injected_3", now - timedelta(days=1))
    not_due_email_client = InMemoryEmailSenderClient()
    not_due_dependencies = {
        "store": not_due_store,
        "email_client": not_due_email_client,
    }
    send_payment_failure_reminders_main(
        _StubRequest(), runtime_dependencies=not_due_dependencies
    )
    results.append(_check(
        "main(): runtime_dependencies注入時、未到達(検知から1日)の事業者には送信されない",
        len(not_due_email_client.sent),
        0,
    ))

    passed = sum(1 for r in results if r)
    print(f"\n{len(results)}件中{passed}件成功")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
