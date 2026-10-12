#!/usr/bin/env python3
"""cloud_function_send_payment_failure_reminders.pyのテスト(README.mdフェーズ290)。

main()固有の配線部分(依存のデフォルト組み立て・常に200を返すこと)に絞り、
決済失敗リマインドの抽出・送信判定自体のロジックはtest_payment_failure_reminder_
scheduler.pyで既にカバー済みのため、ここでは重複させない
(test_cloud_function_send_trial_end_notifications.pyと同じ方針)。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_function_send_payment_failure_reminders import (  # noqa: E402
    get_payment_failure_reminder_runtime_dependencies,
    main,
)
from cloud_function_webhook import InMemoryPortalLinkProvider, InMemoryUsageCounter  # noqa: E402
from payment_failure_reminder_scheduler import run_due_payment_failure_reminders  # noqa: E402
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402


class _StubRequest:
    """Cloud SchedulerのHTTPトリガーリクエストのスタブ。本関数はいずれのフィールドも
    参照しないため、属性を一切持たない空のオブジェクトで足りる。"""


class GetRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_in_memory_store_push_client_and_portal_link_provider(self):
        deps = get_payment_failure_reminder_runtime_dependencies()

        self.assertIsInstance(deps["store"], InMemoryUsageCounter)
        self.assertIsInstance(deps["push_client"], InMemoryLinePushClient)
        self.assertIsInstance(deps["portal_link_provider"], InMemoryPortalLinkProvider)

    def test_each_call_returns_a_fresh_store_instance(self):
        # 呼び出しをまたいで状態が保持されない既知の限界(docstring参照)を裏付ける。
        deps1 = get_payment_failure_reminder_runtime_dependencies()
        deps2 = get_payment_failure_reminder_runtime_dependencies()

        self.assertIsNot(deps1["store"], deps2["store"])

    def test_output_is_accepted_by_run_due_payment_failure_reminders(self):
        import datetime as dt

        deps = get_payment_failure_reminder_runtime_dependencies()

        result = run_due_payment_failure_reminders(
            now=dt.datetime(2026, 10, 12, 0, 0, 0, tzinfo=dt.timezone.utc), **deps
        )

        # ユーザーが存在しない空のInMemoryUsageCounterのため、いずれも0件。
        self.assertEqual(result.sent, [])
        self.assertEqual(result.failed, [])


class MainEntryPointTest(unittest.TestCase):
    """main()(functions_frameworkエントリポイント)のテスト。"""

    def test_returns_200_ok_regardless_of_request_contents(self):
        body, status_code = main(_StubRequest())

        self.assertEqual(status_code, 200)
        self.assertEqual(body, "OK")

    def test_does_not_raise_when_called_repeatedly(self):
        # Cloud Schedulerからの定期起動を想定し、連続呼び出しでも例外が伝播しないことを
        # 確認する(依存が未接続のInMemory実装のみでも安全に起動できる)。
        for _ in range(3):
            body, status_code = main(_StubRequest())
            self.assertEqual((body, status_code), ("OK", 200))


if __name__ == "__main__":
    unittest.main()
