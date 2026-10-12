#!/usr/bin/env python3
"""
payment-suspension-owner-notification-design.md「Cloud Function F:
send_payment_suspension_owner_notifications」が「呼び出し側(Cloud Scheduler経由の日次
バッチ)が行う想定」として残していた、`payment_suspension_owner_notification.
run_due_payment_suspension_owner_notifications()`を実際に起動する薄いCloud Functions
エントリポイントを実装したもの(README.mdフェーズ291、フェーズ289の次回候補(2)で
残っていた2件のうち2件目)。

位置づけ:
- cloud_function_send_payment_failure_reminders.py(フェーズ290)と同じ「本体は依存注入で
  テスト可能、`main(request)`だけが実`functions_framework`リクエストオブジェクトを
  扱う薄い配線」構成を踏襲する。
- payment-suspension-owner-notification-design.mdの想定どおり、Cloud Scheduler(日次)が
  HTTPトリガーとして起動する。Stripe/LINE Webhookとは異なりCloud Scheduler自身の起動が
  トリガーであるため、リクエストボディ・署名ヘッダのいずれも参照しない。
- `get_payment_suspension_owner_notification_runtime_dependencies()`は実Firestore接続
  (usage_counter)・実LINE Push Message API接続のいずれも実GCPプロジェクト・実LINE公式
  アカウント開設(オーナー承認待ち、pending-approval.md参照)後でなければ構築できないため、
  cloud_function_send_payment_failure_reminders.pyと同じ考え方で検証用のInMemory実装を
  返す。承認・実接続後は、この関数の中身を実クライアントを返すように差し替えるだけで
  main()・run_due_payment_suspension_owner_notifications()双方を変更せずに接続できる。
- `main()`は結果(sent/failedの件数)をログ出力した上で、呼び出し元(Cloud Scheduler)には
  常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行される設計
  (payment_suspension_owner_notification.py参照)のため、本関数が5xxでCloud Schedulerに
  リトライを促す必要はない。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_function_webhook import InMemoryUsageCounter  # noqa: E402
from payment_suspension_owner_notification import (  # noqa: E402
    SendPaymentSuspensionOwnerNotificationsResult,
    run_due_payment_suspension_owner_notifications,
)
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402

logger = logging.getLogger(__name__)


def get_payment_suspension_owner_notification_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_send_payment_failure_
    reminders.get_payment_failure_reminder_runtime_dependencies()と対称の構成)。

    実Firestore接続(usage_counter)・実LINE Push Message API接続はいずれも実GCP
    プロジェクト・実LINE公式アカウント開設後でなければ構築できないため(オーナー承認待ち、
    pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    なお`InMemoryUsageCounter()`はこの呼び出しごとに新規生成されるため、実Cloud
    Functions環境でも呼び出しをまたいで状態(`payment_suspension_owner_notified_at`等)が
    保持されない既知の限界が残る(cloud_function_send_payment_failure_reminders.pyの
    同種エントリポイントと同じ限界で、実Firestore接続後に解消される)。
    """
    return {
        "store": InMemoryUsageCounter(),
        "push_client": InMemoryLinePushClient(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    payment-suspension-owner-notification-design.mdの想定どおり、Cloud Scheduler(日次)が
    HTTPトリガーとして起動する。`request`はいずれのフィールドも参照しない(起動自体が
    トリガーであり、署名検証対象のpayloadを持たない)。
    """
    now = datetime.now(timezone.utc)
    deps = get_payment_suspension_owner_notification_runtime_dependencies()
    result: SendPaymentSuspensionOwnerNotificationsResult = (
        run_due_payment_suspension_owner_notifications(now=now, **deps)
    )
    logger.info(
        "payment_suspension_owner_notifications: sent=%d failed=%d",
        len(result.sent),
        len(result.failed),
    )
    return "OK", 200


def _demo() -> None:
    class _StubRequest:
        pass

    body, status_code = main(_StubRequest())
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
