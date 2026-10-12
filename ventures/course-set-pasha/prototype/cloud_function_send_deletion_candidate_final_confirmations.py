#!/usr/bin/env python3
"""
data-retention-policy.md「削除候補化後の最終確認」節・deletion_candidate_final_
confirmation.run_due_deletion_candidate_final_confirmations()を実際に起動する薄い
Cloud Functionsエントリポイント(aircon-pasha/cloud_function_send_deletion_candidate_
final_confirmations.pyの横展開)。

位置づけ:
- cloud_function_webhook.py・cloud_function_send_trial_end_notifications.py等と同じ
  「本体は依存注入でテスト可能、main(request)だけが実functions_frameworkリクエスト
  オブジェクトを扱う薄い配線」構成を踏襲する。
- data-retention-policy.md「削除の実行方法(MVP)」の想定どおり、Cloud Scheduler(月次)が
  HTTPトリガーとして起動する。Stripe/LINE Webhookとは異なりCloud Scheduler自身の起動が
  トリガーであるため、リクエストボディ・署名ヘッダのいずれも参照しない(payloadを持たない)。
- `get_deletion_candidate_final_confirmation_runtime_dependencies()`は実Firestore接続
  (`user_profile`コレクション)・実LINE Push Message API接続のいずれも実GCPプロジェクト・
  実LINE公式アカウント開設(オーナー承認待ち、pending-approval.md参照)後でなければ実
  クライアントを構築できないため、現時点ではcloud_function_webhook.get_runtime_
  dependencies()と同じ考え方で検証用のInMemory実装を返す。承認・実接続後は、この関数の
  中身を実クライアントを返すように差し替えるだけでmain()・run_due_deletion_candidate_
  final_confirmations()双方を変更せずに接続できる。
- 本venture固有の2store構成(deletion_candidate_final_confirmation.pyのモジュール
  docstring参照)のため、依存辞書は`deletion_store`(InMemoryProfileDeletionCandidateStore)・
  `profile_store`(InMemoryUserProfileStore)・`push_client`の3キーを持つ(aircon-pashaの
  `store`単独とは異なる、本venture独自の差異)。
- `main()`は結果(sent/marked_unreachable/failedの件数)をログ出力した上で、呼び出し元
  (Cloud Scheduler)には常に200を返す。失敗(failed)が残っても次回起動時に自然に再試行
  される設計(deletion_candidate_final_confirmation.py参照)のため、本関数が5xxで
  Cloud Schedulerにリトライを促す必要はない。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from application_form_submission_flow import InMemoryUserProfileStore  # noqa: E402
from deletion_candidate import InMemoryProfileDeletionCandidateStore  # noqa: E402
from deletion_candidate_final_confirmation import (  # noqa: E402
    SendDeletionCandidateFinalConfirmationsResult,
    run_due_deletion_candidate_final_confirmations,
)
from trial_end_scheduler import InMemoryLinePushClient  # noqa: E402

logger = logging.getLogger(__name__)


def get_deletion_candidate_final_confirmation_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(cloud_function_send_trial_end_
    notifications.get_trial_end_notification_runtime_dependencies()と対称の構成)。

    実Firestore接続(`user_profile`コレクション)・実LINE Push Message API接続は
    いずれも実GCPプロジェクト・実LINE公式アカウント開設後でなければ構築できないため
    (オーナー承認待ち、pending-approval.md参照)、現時点では検証用のInMemory実装を返す。

    なお`InMemoryProfileDeletionCandidateStore()`・`InMemoryUserProfileStore()`はこの
    呼び出しごとに新規生成されるため、実Cloud Functions環境でも呼び出しをまたいで状態
    (`deletion_confirmation_sent_at`等)が保持されない既知の限界が残る
    (cloud_function_send_trial_end_notifications側と同種の限界で、実Firestore接続後に
    解消される)。
    """
    return {
        "deletion_store": InMemoryProfileDeletionCandidateStore(),
        "profile_store": InMemoryUserProfileStore(),
        "push_client": InMemoryLinePushClient(),
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    data-retention-policy.md「削除の実行方法(MVP)」の想定どおり、Cloud Scheduler
    (月次)がHTTPトリガーとして起動する。`request`はいずれのフィールドも参照しない
    (起動自体がトリガーであり、署名検証対象のpayloadを持たない)。
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
