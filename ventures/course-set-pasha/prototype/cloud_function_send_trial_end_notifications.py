#!/usr/bin/env python3
"""
trial-end-scheduler-design.md「Cloud Function D: send_trial_end_notifications」が
「呼び出し側(Cloud Scheduler経由の日次バッチ)が行う想定」として残していた、
`trial_end_scheduler.run_due_trial_end_notifications()`を実際に起動する薄いCloud
Functionsエントリポイントを実装したもの(README.mdフェーズ289)。

位置づけ:
- aircon-pashaの`cloud_function_send_deletion_candidate_final_confirmations.py`・
  kura-pashaの`cloud_function_run_daily_workshop_checks.py`と同じ「本体は依存注入で
  テスト可能、`main(request)`だけが実`functions_framework`リクエストオブジェクトを
  扱う薄い配線」構成を踏襲する。
- trial-end-scheduler-design.mdの想定どおり、Cloud Scheduler(日次)がHTTPトリガーとして
  起動する。Stripe/LINE Webhookとは異なりCloud Scheduler自身の起動がトリガーであるため、
  リクエストボディ・署名ヘッダのいずれも参照しない。
- `get_trial_end_notification_runtime_dependencies()`は実Firestore接続(usage_counter)・
  実LINE Push Message API接続のいずれも実GCPプロジェクト・実LINE公式アカウント開設
  (オーナー承認待ち、pending-approval.md参照)後でなければ構築できないため、
  `cloud_function_webhook.get_runtime_dependencies()`と同じ考え方で検証用のInMemory
  実装を返す。承認・実接続後は、この関数の中身を実クライアントを返すように差し替える
  だけでmain()・run_due_trial_end_notifications()双方を変更せずに接続できる。
- `main()`は結果(sent/failedの件数)をログ出力した上で、呼び出し元(Cloud Scheduler)には
  常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行される設計
  (trial_end_scheduler.py参照)のため、本関数が5xxでCloud Schedulerにリトライを促す
  必要はない。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cloud_function_webhook import InMemoryUsageCounter  # noqa: E402
from trial_end_scheduler import (  # noqa: E402
    InMemoryLinePushClient,
    SendTrialEndNotificationsResult,
    run_due_trial_end_notifications,
)

logger = logging.getLogger(__name__)


def get_trial_end_notification_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_webhook.get_runtime_
    dependencies()と対称の構成)。

    実Firestore接続(usage_counter)・実LINE Push Message API接続はいずれも実GCP
    プロジェクト・実LINE公式アカウント開設後でなければ構築できないため(オーナー承認待ち、
    pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    なお`InMemoryUsageCounter()`はこの呼び出しごとに新規生成されるため、実Cloud
    Functions環境でも呼び出しをまたいで状態(`trial_end_notified_at`等)が保持されない
    既知の限界が残る(aircon-pashaの同種エントリポイントと同じ限界で、実Firestore接続後に
    解消される)。
    """
    return {
        "store": InMemoryUsageCounter(),
        "push_client": InMemoryLinePushClient(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    trial-end-scheduler-design.mdの想定どおり、Cloud Scheduler(日次)がHTTPトリガーとして
    起動する。`request`はいずれのフィールドも参照しない(起動自体がトリガーであり、
    署名検証対象のpayloadを持たない)。
    """
    now = datetime.now(timezone.utc)
    deps = get_trial_end_notification_runtime_dependencies()
    result: SendTrialEndNotificationsResult = run_due_trial_end_notifications(
        now=now, **deps
    )
    logger.info(
        "trial_end_notifications: sent=%d failed=%d",
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
