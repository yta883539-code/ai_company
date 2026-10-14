#!/usr/bin/env python3
"""cloud_function_run_daily_checks.pyのテスト(フェーズ315)。

README.mdフェーズ314「次回候補(2)」で指摘された、trial_end_scheduler.py・
payment_failure_reminder_scheduler.py・payment_suspension_scheduler.pyのCloud
Functionsエントリポイント欠落への対応を検証する。main()固有の配線部分(依存のデフォルト
組み立て・常に200を返すこと)に絞り、抽出・送信判定自体のロジックはtest_daily_
scheduler.pyで既にカバー済みのため、ここでは重複させない
(test_cloud_function_send_deletion_candidate_final_confirmations.pyと同じ方針)。
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_function_run_daily_checks import (  # noqa: E402
    get_daily_checks_runtime_dependencies,
    main,
)
from daily_scheduler import run_daily_checks  # noqa: E402
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402
from user_id_linking import InMemoryUserProfileStore  # noqa: E402


class _StubRequest:
    """Cloud SchedulerのHTTPトリガーリクエストのスタブ。本関数はいずれのフィールドも
    参照しないため、属性を一切持たない空のオブジェクトで足りる。"""


class GetRuntimeDependenciesTest(unittest.TestCase):
    def test_returns_in_memory_store_and_push_client(self):
        deps = get_daily_checks_runtime_dependencies()

        self.assertIsInstance(deps["profile_store"], InMemoryUserProfileStore)
        self.assertIsInstance(deps["push_client"], InMemoryLinePushClient)

    def test_each_call_returns_a_fresh_store_instance(self):
        # 呼び出しをまたいで状態が保持されない既知の限界(docstring参照)を裏付ける。
        deps1 = get_daily_checks_runtime_dependencies()
        deps2 = get_daily_checks_runtime_dependencies()

        self.assertIsNot(deps1["profile_store"], deps2["profile_store"])

    def test_output_is_accepted_by_run_daily_checks(self):
        deps = get_daily_checks_runtime_dependencies()

        result = run_daily_checks(now=datetime(2026, 10, 14, 4, 0, 0), **deps)

        # 候補が存在しない空のInMemoryUserProfileStoreのため、いずれも0件。
        self.assertEqual(result.trial_end_notifications.sent, [])
        self.assertEqual(result.payment_failure_reminders.sent, [])
        self.assertEqual(result.payment_suspensions.suspended, [])


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
