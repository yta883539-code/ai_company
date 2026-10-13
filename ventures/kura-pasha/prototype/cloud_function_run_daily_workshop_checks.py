#!/usr/bin/env python3
"""
aircon-pashaフェーズ309「次回候補(2)」の横断点検で発見した欠落への対応(フェーズ192)。
daily-scheduler-design.md(フェーズ112)で設計した「Cloud Function G:
run_daily_workshop_checks」(daily_scheduler.py)には選定ロジック・送信配線本体は実装済み
だったが、aircon-pashaのcloud_function_send_deletion_candidate_final_confirmations.pyに
相当する薄いCloud Functionsエントリポイント(Cloud Schedulerから実際に起動する`main()`)が
本venture単体では未実装のまま残っていた。本ファイルはその欠落を埋めるもの。

位置づけ:
- aircon-pashaの同種ファイル・本venture自身のcloud_function_webhook.pyと同じ「本体は
  依存注入でテスト可能、main(request)だけが実functions_frameworkリクエストオブジェクトを
  扱う薄い配線」構成を踏襲する。
- daily-scheduler-design.mdの想定どおり、Cloud Scheduler(日次・暫定JST 04:00)がHTTP
  トリガーとして起動する。Stripe/LINE Webhookとは異なりCloud Scheduler自身の起動が
  トリガーであるため、リクエストボディ・署名ヘッダのいずれも参照しない。
- `get_daily_workshop_checks_runtime_dependencies()`は実Firestore接続・実LINE Push
  Message API接続のいずれも実GCPプロジェクト・実LINE公式アカウント開設後でなければ構築
  できないため(オーナー承認待ち、pending-approval.md参照)、cloud_function_webhook.
  get_runtime_dependencies()と同じ考え方で検証用のInMemory実装を返す。承認・実接続後は、
  この関数の中身を実クライアントを返すように差し替えるだけでmain()・
  run_daily_workshop_checks()双方を変更せずに接続できる。
- `main()`は結果(trial_end_reports/payment_failure_reminders/payment_suspension_owner_
  notificationsそれぞれのsent/failed件数)をログ出力した上で、呼び出し元(Cloud
  Scheduler)には常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行される
  設計(daily_scheduler.py参照)のため、本関数が5xxでCloud Schedulerにリトライを促す
  必要はない。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from daily_scheduler import RunDailyWorkshopChecksResult, run_daily_workshop_checks  # noqa: E402
from payment_suspension_owner_notification import OWNER_LINE_USER_ID_PLACEHOLDER  # noqa: E402
from subscription_cancellation_notification import InMemoryLinePushClient  # noqa: E402
from usage_counter_workshop import (  # noqa: E402
    InMemoryUserProfileStore,
    InMemoryWorkshopStore,
)

logger = logging.getLogger(__name__)


def get_daily_workshop_checks_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_webhook.get_runtime_
    dependencies()・aircon-pashaのget_deletion_candidate_final_confirmation_runtime_
    dependencies()と対称の構成)。

    実Firestore接続(workshopコレクション)・実LINE Push Message API接続はいずれも実
    GCPプロジェクト・実LINE公式アカウント開設後でなければ構築できないため(オーナー承認
    待ち、pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    `InMemoryWorkshopStore()`/`InMemoryUserProfileStore()`はこの呼び出しごとに新規生成
    されるため、実Cloud Functions環境でも呼び出しをまたいで状態(trial_end_notified_at等)
    が保持されない既知の限界が残る(aircon-pasha側と同種の限界で、実Firestore接続後に
    解消される)。`user_profile_store`はフェーズ233(deletion_candidate_final_
    confirmation.py)で新たに必要になった依存。
    """
    return {
        "workshop_store": InMemoryWorkshopStore(),
        "user_profile_store": InMemoryUserProfileStore(),
        "push_client": InMemoryLinePushClient(),
        "owner_line_user_id": OWNER_LINE_USER_ID_PLACEHOLDER,
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    daily-scheduler-design.mdの想定どおり、Cloud Scheduler(日次・暫定JST 04:00)が
    HTTPトリガーとして起動する。`request`はいずれのフィールドも参照しない(起動自体が
    トリガーであり、署名検証対象のpayloadを持たない)。
    """
    now = datetime.now(timezone.utc)
    deps = get_daily_workshop_checks_runtime_dependencies()
    result: RunDailyWorkshopChecksResult = run_daily_workshop_checks(now=now, **deps)
    logger.info(
        "daily_workshop_checks: trial_end_sent=%d trial_end_failed=%d "
        "payment_failure_sent=%d payment_failure_failed=%d "
        "owner_notifications_sent=%d owner_notifications_failed=%d "
        "deletion_confirmations_sent=%d deletion_confirmations_unreachable=%d "
        "deletion_confirmations_failed=%d",
        len(result.trial_end_reports.sent),
        len(result.trial_end_reports.failed),
        len(result.payment_failure_reminders.sent),
        len(result.payment_failure_reminders.failed),
        len(result.payment_suspension_owner_notifications.sent),
        len(result.payment_suspension_owner_notifications.failed),
        len(result.deletion_candidate_final_confirmations.sent),
        len(result.deletion_candidate_final_confirmations.marked_unreachable),
        len(result.deletion_candidate_final_confirmations.failed),
    )
    return "OK", 200


def _demo() -> None:
    class _StubRequest:
        pass

    body, status_code = main(_StubRequest())
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
