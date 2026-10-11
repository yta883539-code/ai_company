#!/usr/bin/env python3
"""cloud_function_run_daily_workshop_checks.pyのテスト(フェーズ192)。

aircon-pashaのtest_cloud_function_send_deletion_candidate_final_confirmations.pyと同じ
方針で、main()固有の配線部分(依存のデフォルト組み立て・常に200を返すこと)に絞る。
抽出・送信判定自体のロジックはtest_daily_scheduler.pyで既にカバー済みのため、ここでは
重複させない。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_function_run_daily_workshop_checks import (  # noqa: E402
    get_daily_workshop_checks_runtime_dependencies,
    main,
)
from daily_scheduler import run_daily_workshop_checks  # noqa: E402
from payment_suspension_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER  # noqa: E402
from subscription_cancellation_notification import InMemoryLinePushClient  # noqa: E402
from usage_counter_workshop import InMemoryWorkshopStore  # noqa: E402


class _StubRequest:
    """Cloud SchedulerのHTTPトリガーリクエストのスタブ。本関数はいずれのフィールドも
    参照しないため、属性を一切持たない空のオブジェクトで足りる。"""


class GetRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_in_memory_store_and_push_client(self):
        deps = get_daily_workshop_checks_runtime_dependencies()

        self.assertIsInstance(deps["workshop_store"], InMemoryWorkshopStore)
        self.assertIsInstance(deps["push_client"], InMemoryLinePushClient)
        self.assertEqual(deps["owner_line_user_id"], OWNER_LINE_USER_ID_PLACEHOLDER)

    def test_each_call_returns_a_fresh_store_instance(self):
        # 呼び出しをまたいで状態が保持されない既知の限界(docstring参照)を裏付ける。
        deps1 = get_daily_workshop_checks_runtime_dependencies()
        deps2 = get_daily_workshop_checks_runtime_dependencies()

        self.assertIsNot(deps1["workshop_store"], deps2["workshop_store"])

    def test_output_is_accepted_by_run_daily_workshop_checks(self):
        import datetime as dt

        deps = get_daily_workshop_checks_runtime_dependencies()

        result = run_daily_workshop_checks(now=dt.datetime(2026, 10, 11, 4, 0, 0), **deps)

        # workshopが存在しない空のInMemoryWorkshopStoreのため、いずれも0件。
        self.assertEqual(result.trial_end_reports.sent, [])
        self.assertEqual(result.payment_failure_reminders.sent, [])
        self.assertEqual(result.payment_suspension_owner_notifications.sent, [])


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
