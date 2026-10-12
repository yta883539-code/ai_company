#!/usr/bin/env python3
"""trial-end-notification-design.md 6節が「呼び出し側(Cloud Scheduler経由の日次バッチ)が
行う想定」として残していた、`trial_end_email_scheduler.run_due_trial_end_emails()`を実際に
起動する薄いCloud Functionsエントリポイントを実装したもの(README.mdフェーズ133、
フェーズ132「次回候補(2)」対応)。

位置づけ:
- course-set-pasha/cloud_function_send_payment_failure_reminders.pyと同じ「本体は依存注入で
  テスト可能、`main(request)`だけが実`functions_framework`リクエストオブジェクトを
  扱う薄い配線」構成を踏襲する。
- trial-end-notification-design.md 1節(B)の想定どおり、Cloud Scheduler(日次)がHTTPトリガー
  として起動する。Stripe Webhookとは異なりCloud Scheduler自身の起動がトリガーであるため、
  リクエストボディ・署名ヘッダのいずれも参照しない。
- `get_trial_end_email_runtime_dependencies()`は実Firestore接続(fleet_operatorストア)・
  実メール送信API接続のいずれも実GCPプロジェクト・実メール送信手段の確定
  (オーナー承認待ち、pending-approval.md 2026-10-10 18:00 UTC記載)後でなければ構築できない
  ため、検証用のInMemory実装を返す。承認・実接続後は、この関数の中身を実クライアントを
  返すように差し替えるだけで`main()`・`run_due_trial_end_emails()`双方を変更せずに接続できる。
- `main()`は結果(sent/failed/skipped_no_emailの件数)をログ出力した上で、呼び出し元
  (Cloud Scheduler)には常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行される
  設計(trial_end_email_scheduler.py参照)のため、本関数が5xxでCloud Schedulerにリトライを
  促す必要はない。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trial_end_email_scheduler import (  # noqa: E402
    InMemoryEmailSenderClient,
    SendTrialEndEmailsResult,
    run_due_trial_end_emails,
)
from trial_management import InMemoryFleetOperatorStore  # noqa: E402

logger = logging.getLogger(__name__)


def get_trial_end_email_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(course-set-pasha/
    get_payment_failure_reminder_runtime_dependencies()と対称の構成)。

    実Firestore接続(fleet_operatorストア)・実メール送信API接続はいずれも実GCPプロジェクト・
    実メール送信手段の確定(送信元ドメイン・SMTP/メールAPIの選定)後でなければ構築できないため
    (オーナー承認待ち、pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    なお`InMemoryFleetOperatorStore()`はこの呼び出しごとに新規生成されるため、実Cloud
    Functions環境でも呼び出しをまたいで状態(`trial_end_notified_at`等)が保持されない
    既知の限界が残る(course-set-pasha/get_payment_failure_reminder_runtime_dependencies()の
    同種エントリポイントと同じ限界で、実Firestore接続後に解消される)。`access_url_provider`は
    未実装のアクセストークンストアに依存するため、ここでは`None`(未接続)のまま渡し、
    `render_trial_end_email_body()`側のフォールバック文言に委ねる(次回候補)。
    """
    return {
        "operator_store": InMemoryFleetOperatorStore(),
        "email_client": InMemoryEmailSenderClient(),
        "access_url_provider": None,
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    trial-end-notification-design.md 1節(B)の想定どおり、Cloud Scheduler(日次)がHTTP
    トリガーとして起動する。`request`はいずれのフィールドも参照しない(起動自体がトリガーで
    あり、署名検証対象のpayloadを持たない)。
    """
    now = datetime.now(timezone.utc)
    deps = get_trial_end_email_runtime_dependencies()
    result: SendTrialEndEmailsResult = run_due_trial_end_emails(now=now, **deps)
    logger.info(
        "trial_end_emails: sent=%d failed=%d skipped_no_email=%d",
        len(result.sent),
        len(result.failed),
        len(result.skipped_no_email),
    )
    return "OK", 200


def _demo() -> None:
    class _StubRequest:
        pass

    body, status_code = main(_StubRequest())
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
