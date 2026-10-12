#!/usr/bin/env python3
"""cloud_function_send_payment_suspension_owner_notifications.pyのテスト
(README.mdフェーズ291)。

main()固有の配線部分(依存のデフォルト組み立て・常に200を返すこと)に絞り、
オーナー通知対象の抽出・送信判定自体のロジックはtest_payment_suspension_owner_
notification.pyで既にカバー済みのため、ここでは重複させない
(test_cloud_function_send_payment_failure_reminders.pyと同じ方針)。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_function_send_payment_suspension_owner_notifications import (  # noqa: E402
    get_payment_suspension_owner_notification_runtime_dependencies,
    main,
)
from cloud_function_webhook import InMemoryUsageCounter  # noqa: E402
from payment_suspension_owner_notification import (  # noqa: E402
    run_due_payment_suspension_owner_notifications,
)
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402


class _StubRequest:
    """Cloud SchedulerのHTTPトリガーリクエストのスタブ。本関数はいずれのフィールドも
    参照しないため、属性を一切持たない空のオブジェクトで足りる。"""


class GetRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_in_memory_store_and_push_client(self):
        deps = get_payment_suspension_owner_notification_runtime_dependencies()

        self.assertIsInstance(deps["store"], InMemoryUsageCounter)
        self.assertIsInstance(deps["push_client"], InMemoryLinePushClient)

    def test_each_call_returns_a_fresh_store_instance(self):
        # 呼び出しをまたいで状態が保持されない既知の限界(docstring参照)を裏付ける。
        deps1 = get_payment_suspension_owner_notification_runtime_dependencies()
        deps2 = get_payment_suspension_owner_notification_runtime_dependencies()

        self.assertIsNot(deps1["store"], deps2["store"])

    def test_output_is_accepted_by_run_due_payment_suspension_owner_notifications(self):
        import datetime as dt

        deps = get_payment_suspension_owner_notification_runtime_dependencies()

        result = run_due_payment_suspension_owner_notifications(
            now=dt.datetime(2026, 10, 12, 0, 0, 0, tzinfo=dt.timezone.utc), **deps
        )

        # 顧客が存在しない空のInMemoryUsageCounterのため、いずれも0件。
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
