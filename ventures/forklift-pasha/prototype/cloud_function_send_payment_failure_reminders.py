#!/usr/bin/env python3
"""payment-failure-reminder-scheduler-design.md 6節が「呼び出し側(Cloud Scheduler経由の
日次バッチ)が行う想定」として残していた、`payment_failure_reminder_scheduler.
run_due_payment_failure_reminders()`・`run_due_payment_suspension_owner_notifications()`を
実際に起動する薄いCloud Functionsエントリポイントを実装したもの(README.mdフェーズ171、
フェーズ170「次回候補(2)」対応)。

位置づけ:
- cloud_function_send_trial_end_emails.py(フェーズ133)・course-set-pasha/
  cloud_function_send_payment_failure_reminders.pyと同じ「本体は依存注入でテスト可能、
  `main(request)`だけが実`functions_framework`リクエストオブジェクトを扱う薄い配線」構成を
  踏襲する。
- design 6節の想定どおり、Cloud Scheduler(日次)がHTTPトリガーとして起動する。Stripe
  Webhookとは異なりCloud Scheduler自身の起動がトリガーであるため、リクエストボディ・署名
  ヘッダのいずれも参照しない。
- `get_payment_failure_reminder_runtime_dependencies()`は実Firestore接続(fleet_operator
  ストア)・実メール送信API接続のいずれも実GCPプロジェクト・実メール送信手段の確定
  (オーナー承認待ち、pending-approval.md 2026-10-10 18:00 UTC記載の範囲)後でなければ
  構築できないため、cloud_function_send_trial_end_emails.pyと同じ考え方で検証用の
  InMemory実装を返す。承認・実接続後は、この関数の中身を実クライアントを返すように
  差し替えるだけでmain()・run_due_payment_failure_reminders()/
  run_due_payment_suspension_owner_notifications()いずれも変更せずに接続できる。
- `main()`はリマインド送信・運営者向け通知の2処理を1回のCloud Scheduler起動でまとめて
  実行し、結果(sent/failed/skipped_no_emailの件数)をログ出力した上で、呼び出し元
  (Cloud Scheduler)には常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行
  される設計(payment_failure_reminder_scheduler.py参照)のため、本関数が5xxでCloud
  Schedulerにリトライを促す必要はない。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from payment_failure_reminder_scheduler import (  # noqa: E402
    SendPaymentFailureRemindersResult,
    SendPaymentSuspensionOwnerNotificationsResult,
    run_due_payment_failure_reminders,
    run_due_payment_suspension_owner_notifications,
)
from trial_end_email_scheduler import InMemoryEmailSenderClient  # noqa: E402
from trial_management import InMemoryFleetOperatorStore  # noqa: E402

logger = logging.getLogger(__name__)


def get_payment_failure_reminder_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_send_trial_end_emails.
    get_trial_end_email_runtime_dependencies()と対称の構成)。

    実Firestore接続(fleet_operatorストア)・実メール送信API接続はいずれも実GCPプロジェクト・
    実メール送信手段の確定後でなければ構築できないため(オーナー承認待ち、
    pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    なお`InMemoryFleetOperatorStore()`はこの呼び出しごとに新規生成されるため、実Cloud
    Functions環境でも呼び出しをまたいで状態(`payment_failure_reminder_sent_at`・
    `payment_suspension_owner_notified_at`等)が保持されない既知の限界が残る
    (cloud_function_send_trial_end_emails.pyの同種エントリポイントと同じ限界で、実
    Firestore接続後に解消される)。
    """
    return {
        "store": InMemoryFleetOperatorStore(),
        "email_client": InMemoryEmailSenderClient(),
    }


def main(request, *, runtime_dependencies: Optional[dict] = None):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    design 6節の想定どおり、Cloud Scheduler(日次)がHTTPトリガーとして起動する。
    `request`はいずれのフィールドも参照しない(起動自体がトリガーであり、署名検証対象の
    payloadを持たない)。

    `runtime_dependencies`省略時は`get_payment_failure_reminder_runtime_dependencies()`の
    戻り値(呼び出しごとに新規のInMemory実装)を使うため、実Cloud Functions環境・既存呼び出し
    元の挙動は変わらない。cloud_function_send_trial_end_emails.main()と同じ依存注入パターン
    により、事前に状態を設定済みのストアをテスト・簡易ローカルサーバーから注入できるようにした。
    """
    now = datetime.now(timezone.utc)
    deps = (
        runtime_dependencies
        if runtime_dependencies is not None
        else get_payment_failure_reminder_runtime_dependencies()
    )
    reminder_result: SendPaymentFailureRemindersResult = run_due_payment_failure_reminders(
        now=now, **deps
    )
    owner_result: SendPaymentSuspensionOwnerNotificationsResult = (
        run_due_payment_suspension_owner_notifications(now=now, **deps)
    )
    logger.info(
        "payment_failure_reminders: sent=%d failed=%d skipped_no_email=%d",
        len(reminder_result.sent),
        len(reminder_result.failed),
        len(reminder_result.skipped_no_email),
    )
    logger.info(
        "payment_suspension_owner_notifications: sent=%d failed=%d",
        len(owner_result.sent),
        len(owner_result.failed),
    )
    return "OK", 200


def _demo() -> None:
    class _StubRequest:
        pass

    body, status_code = main(_StubRequest())
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
