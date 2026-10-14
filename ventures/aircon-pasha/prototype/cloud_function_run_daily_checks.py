#!/usr/bin/env python3
"""
daily_scheduler.py(フェーズ315)の本体を実際に起動する薄いCloud Functionsエントリ
ポイント。cloud_function_send_deletion_candidate_final_confirmations.py・
kura-pasha/prototype/cloud_function_run_daily_workshop_checks.pyと同じ「本体は依存注入
でテスト可能、main(request)だけが実functions_frameworkリクエストオブジェクトを扱う薄い
配線」構成を踏襲する。

位置づけ:
- trial-end-scheduler-design.md・payment-failure-reminder-scheduler-design.mdの想定
  どおり、Cloud Scheduler(日次・暫定JST 04:00)がHTTPトリガーとして起動する。Stripe/LINE
  Webhookとは異なりCloud Scheduler自身の起動がトリガーであるため、リクエストボディ・
  署名ヘッダのいずれも参照しない。
- `get_daily_checks_runtime_dependencies()`は実Firestore接続(`user_profile`コレクション)・
  実LINE Push Message API接続のいずれも実GCPプロジェクト・実LINE公式アカウント開設(オーナー
  承認待ち、pending-approval.md参照)後でなければ構築できないため、cloud_function_webhook.
  get_runtime_dependencies()と同じ考え方で検証用のInMemory実装を返す。承認・実接続後は、
  この関数の中身を実クライアントを返すように差し替えるだけでmain()・run_daily_checks()
  双方を変更せずに接続できる。
- `main()`は結果(3系統それぞれのsent/failed件数)をログ出力した上で、呼び出し元(Cloud
  Scheduler)には常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行される設計
  (daily_scheduler.py参照)のため、本関数が5xxでCloud Schedulerにリトライを促す必要はない。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_scheduler import RunDailyChecksResult, run_daily_checks  # noqa: E402
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402
from user_id_linking import InMemoryUserProfileStore  # noqa: E402

logger = logging.getLogger(__name__)


def get_daily_checks_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_webhook.get_runtime_
    dependencies()・cloud_function_send_deletion_candidate_final_confirmations.
    get_deletion_candidate_final_confirmation_runtime_dependencies()と対称の構成)。

    実Firestore接続(`user_profile`コレクション)・実LINE Push Message API接続はいずれも
    実GCPプロジェクト・実LINE公式アカウント開設後でなければ構築できないため(オーナー承認
    待ち、pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    `InMemoryUserProfileStore()`はこの呼び出しごとに新規生成されるため、実Cloud
    Functions環境でも呼び出しをまたいで状態(`trial_end_notified_at`等)が保持されない
    既知の限界が残る(他venture・本venture自身の同種Cloud Functionsと共通の限界で、実
    Firestore接続後に解消される)。
    """
    return {
        "profile_store": InMemoryUserProfileStore(),
        "push_client": InMemoryLinePushClient(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    trial-end-scheduler-design.md・payment-failure-reminder-scheduler-design.mdの想定
    どおり、Cloud Scheduler(日次・暫定JST 04:00)がHTTPトリガーとして起動する。`request`は
    いずれのフィールドも参照しない(起動自体がトリガーであり、署名検証対象のpayloadを
    持たない)。
    """
    now = datetime.now(timezone.utc)
    deps = get_daily_checks_runtime_dependencies()
    result: RunDailyChecksResult = run_daily_checks(now=now, **deps)
    logger.info(
        "daily_checks: trial_end_sent=%d trial_end_failed=%d "
        "payment_failure_reminder_sent=%d payment_failure_reminder_failed=%d "
        "payment_suspension_suspended=%d payment_suspension_failed=%d",
        len(result.trial_end_notifications.sent),
        len(result.trial_end_notifications.failed),
        len(result.payment_failure_reminders.sent),
        len(result.payment_failure_reminders.failed),
        len(result.payment_suspensions.suspended),
        len(result.payment_suspensions.failed),
    )
    return "OK", 200


def _demo() -> None:
    class _StubRequest:
        pass

    body, status_code = main(_StubRequest())
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
