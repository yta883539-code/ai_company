#!/usr/bin/env python3
"""
フェーズ308(README.md)で設計したdeletion-candidate-final-confirmation-scheduler-design.md
(月次Cloud Scheduler構成)の「次回候補(2)」だった、`deletion_candidate_final_confirmation.
run_due_deletion_candidate_final_confirmations()`を実際に起動する薄いCloud Functions
エントリポイントを実装したもの。

位置づけ:
- conversation_event_processor_assembly.py(line-reservation-ai)・本venture自身の
  cloud_function_webhook.pyと同じ「本体は依存注入でテスト可能、main(request)だけが実
  functions_frameworkリクエストオブジェクトを扱う薄い配線」構成を踏襲する。
- deletion-candidate-final-confirmation-scheduler-design.mdの想定どおり、Cloud Scheduler
  (月次・暫定JST 05:00)がHTTPトリガーとして起動する。Stripe/LINE Webhookとは異なり
  Cloud Scheduler自身の起動がトリガーであるため、リクエストボディ・署名ヘッダのいずれも
  参照しない(payloadを持たない)。
- `get_deletion_candidate_final_confirmation_runtime_dependencies()`は実Firestore接続
  (`user_profile`コレクション)・実LINE Push Message API接続のいずれも実GCPプロジェクト・
  実LINE公式アカウント開設(オーナー承認待ち、pending-approval.md参照)後でなければ実
  クライアントを構築できないため、現時点ではcloud_function_webhook.get_runtime_
  dependencies()と同じ考え方で検証用のInMemory実装を返す。承認・実接続後は、この関数の
  中身を実クライアントを返すように差し替えるだけでmain()・run_due_deletion_candidate_
  final_confirmations()双方を変更せずに接続できる。
- `main()`は結果(sent/marked_unreachable/failedの件数)をログ出力した上で、呼び出し元
  (Cloud Scheduler)には常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行
  される設計(deletion_candidate_final_confirmation.py参照)のため、本関数が5xxで
  Cloud Schedulerにリトライを促す必要はない(cloud_function_webhook.main()が署名検証
  失敗時のみ401を返すのとは異なり、本関数は起動自体に失敗要因〈署名・payload不正等〉が
  存在しないことによる仕様上の違い)。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deletion_candidate_final_confirmation import (  # noqa: E402
    SendDeletionCandidateFinalConfirmationsResult,
    run_due_deletion_candidate_final_confirmations,
)
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402
from user_id_linking import InMemoryUserProfileStore  # noqa: E402

logger = logging.getLogger(__name__)


def get_deletion_candidate_final_confirmation_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_webhook.get_runtime_
    dependencies()と対称の構成)。

    実Firestore接続(`user_profile`コレクション)・実LINE Push Message API接続は
    いずれも実GCPプロジェクト・実LINE公式アカウント開設後でなければ構築できないため
    (オーナー承認待ち、pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    なお`InMemoryUserProfileStore()`はこの呼び出しごとに新規生成されるため、実Cloud
    Functions環境でも呼び出しをまたいで状態(`deletion_confirmation_sent_at`等)が
    保持されない既知の限界が残る(conversation_event_processor_assembly.get_process_
    conversation_event_runtime_dependencies()側と同種の限界で、実Firestore接続後に
    解消される)。
    """
    return {
        "store": InMemoryUserProfileStore(),
        "push_client": InMemoryLinePushClient(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    deletion-candidate-final-confirmation-scheduler-design.mdの想定どおり、Cloud
    Scheduler(月次・暫定JST 05:00)がHTTPトリガーとして起動する。`request`はいずれの
    フィールドも参照しない(起動自体がトリガーであり、署名検証対象のpayloadを持たない)。
    """
    now = datetime.now(timezone.utc)
    deps = get_deletion_candidate_final_confirmation_runtime_dependencies()
    result: SendDeletionCandidateFinalConfirmationsResult = (
        run_due_deletion_candidate_final_confirmations(now=now, **deps)
    )
    logger.info(
        "deletion_candidate_final_confirmations: sent=%d marked_unreachable=%d failed=%d",
        len(result.sent),
        len(result.marked_unreachable),
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
