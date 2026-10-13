#!/usr/bin/env python3
"""cloud_function_send_trial_end_emails.pyのmain()境界値テスト(フェーズ147)。

checkout_session.main()(フェーズ146)・stripe_webhook.main()(フェーズ147)と同じ
依存注入パターン(`runtime_dependencies`引数)をcloud_function_send_trial_end_emails.main()
にも適用したことを確認する。これまでmain()自体を直接呼ぶテストは無く、`_demo()`による
手元確認(InMemoryFleetOperatorStore()が空のため常にsent=0件)にとどまっていた。

実行方法: python3 prototype/test_cloud_function_send_trial_end_emails.py
"""

import sys
from datetime import datetime, timedelta, timezone

from cloud_function_send_trial_end_emails import main as send_trial_end_emails_main
from trial_end_email_scheduler import InMemoryEmailSenderClient
from trial_management import TRIAL_PERIOD_DAYS, InMemoryFleetOperatorStore


class _StubRequest:
    """main(request)のテスト用スタブ。Cloud Scheduler起動時、本関数はrequestの
    いずれのフィールドも参照しないため(cloud_function_send_trial_end_emails.main()
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
    body, status = send_trial_end_emails_main(_StubRequest())
    results.append(_check("main(): runtime_dependencies省略時は200", status, 200))
    results.append(_check("main(): runtime_dependencies省略時のレスポンスボディ", body, "OK"))

    # --- main(): runtime_dependencies注入時、トライアル終了対象者へ実際に送信される ---
    # (フェーズ147: checkout_session.main()・stripe_webhook.main()と同じパターンにより、
    # 事前にtrial_start_at・emailを登録済みのoperator_storeを注入できるようになった)
    # main()内部はdatetime.now(timezone.utc)(実際の現在時刻)を使うため、本テストの
    # 基準点もdatetime.now(timezone.utc)から取り、安全マージン(+1日)を加えたうえで
    # TRIAL_PERIOD_DAYS日分遡ることで、テスト実行タイミングによらず確実に期限到達済みと
    # 判定されるようにする。
    now = datetime.now(timezone.utc)
    injected_operator_store = InMemoryFleetOperatorStore()
    injected_operator_store.set_email("fo_injected_1", "owner@example.com")
    injected_operator_store.set_trial_start_at(
        "fo_injected_1", now - timedelta(days=TRIAL_PERIOD_DAYS + 1)
    )
    injected_email_client = InMemoryEmailSenderClient()
    injected_dependencies = {
        "operator_store": injected_operator_store,
        "email_client": injected_email_client,
        "access_url_provider": None,
    }

    # main()内部はdatetime.now(timezone.utc)で現在時刻を取得する(nowの注入口は無い、
    # main() docstring参照)ため、本テストではtrial_start_atを十分過去に設定することで
    # 実行時刻によらず送信対象に該当させる。
    injected_body, injected_status = send_trial_end_emails_main(
        _StubRequest(), runtime_dependencies=injected_dependencies
    )
    results.append(_check("main(): runtime_dependencies注入時も200", injected_status, 200))
    results.append(_check(
        "main(): runtime_dependencies注入時、期限到達済み事業者へ実際に送信される"
        "(InMemoryEmailSenderClient.sentに反映)",
        len(injected_email_client.sent),
        1,
    ))
    results.append(_check(
        "main(): 送信先メールアドレスがinjected_operator_storeの登録値と一致する",
        injected_email_client.sent[0][0] if injected_email_client.sent else None,
        "owner@example.com",
    ))

    # --- main(): runtime_dependencies注入時でも未到達の事業者には送信されない ---
    not_due_operator_store = InMemoryFleetOperatorStore()
    not_due_operator_store.set_email("fo_injected_2", "owner2@example.com")
    not_due_operator_store.set_trial_start_at("fo_injected_2", now - timedelta(days=1))
    second_email_client = InMemoryEmailSenderClient()
    second_dependencies = {
        "operator_store": not_due_operator_store,
        "email_client": second_email_client,
        "access_url_provider": None,
    }
    send_trial_end_emails_main(_StubRequest(), runtime_dependencies=second_dependencies)
    results.append(_check(
        "main(): runtime_dependencies注入時、未到達(trial_start_atから1日)の事業者には"
        "送信されない",
        len(second_email_client.sent),
        0,
    ))

    passed = sum(1 for r in results if r)
    print(f"\n{len(results)}件中{passed}件成功")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
