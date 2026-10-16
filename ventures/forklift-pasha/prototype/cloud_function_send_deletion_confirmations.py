#!/usr/bin/env python3
"""deletion-candidate-design.md(フェーズ152)5節が「削除実行バッチのCloud Scheduler化は
既存の承認待ち事項の範囲内」として残していた、`deletion_candidate.py`の各関数(削除候補の
洗い出し→未送信分の絞り込み→最終確認送信)を実際に起動する薄いCloud Functionsエントリ
ポイントを実装したもの(README.mdフェーズ153)。

位置づけ:
- cloud_function_send_trial_end_emails.py・checkout_session.main()・stripe_webhook.main()と
  同じ「本体は依存注入でテスト可能、`main(request)`だけが実`functions_framework`リクエスト
  オブジェクトを扱う薄い配線」構成を踏襲する。
- trial-end-notification-design.md 1節(B)経路と同様、Cloud Scheduler(日次)がHTTPトリガー
  として起動する想定のため、リクエストボディ・署名ヘッダのいずれも参照しない。
- `get_deletion_confirmation_runtime_dependencies()`は実Firestore接続(fleet_operatorストア)・
  実メール送信API接続のいずれも実GCPプロジェクト・実メール送信手段の確定(オーナー承認待ち、
  pending-approval.md 2026-10-06 22:00 UTC・2026-10-10 18:00 UTC記載)後でなければ構築できない
  ため、検証用のInMemory実装を返す。実メール送信手段が未確定の間は`_UnconfiguredEmailSender`
  が常に送信失敗(`unreachable_at`設定)を返す安全側のフォールバックとする(データの誤削除や
  「送信済みなのに実際には届いていない」という状態を防ぐため、楽観的にTrueを返すより安全)。
  承認・実接続後は、この関数の中身を実クライアントを返すように差し替えるだけで`main()`・
  `deletion_candidate.py`側の各関数双方を変更せずに接続できる。
- `main()`は結果(sent/unreachable件数)をログ出力した上で、呼び出し元(Cloud Scheduler)には
  常に200を返す(実削除は一切行わない読み取り専用+送信のみのバッチであり、失敗が残っても
  次回起動時に自然に再試行される設計のため、5xxでCloud Schedulerにリトライを促す必要はない)。
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deletion_candidate import (  # noqa: E402
    EmailSenderProtocol,
    SendDeletionCandidateFinalConfirmationsResult,
    list_deletion_candidates,
    select_due_deletion_candidate_final_confirmations,
    send_deletion_candidate_final_confirmations,
)
from trial_management import InMemoryFleetOperatorStore  # noqa: E402

logger = logging.getLogger(__name__)


class _UnconfiguredEmailSender(EmailSenderProtocol):
    """実メール送信サービス接続前の既定実装(design 5節: 送信手段未確定の間の安全側
    フォールバック)。常に送信失敗を返すため、`send_deletion_candidate_final_confirmations()`
    経由で呼ばれた候補は全件`deletion_confirmation_unreachable_at`が設定され、
    `list_unreachable_deletion_candidates()`のオーナー向けレポートに現れる(オーナーが
    実メール送信接続後に再送対象として扱えるようにする)。"""

    def send(self, internal_id: str, email: "str | None") -> bool:
        return False


def get_deletion_confirmation_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(get_trial_end_email_runtime_dependencies()と
    対称の構成)。

    実Firestore接続(fleet_operatorストア)・実メール送信API接続はいずれも実GCPプロジェクト・
    実メール送信手段の確定後でなければ構築できないため(オーナー承認待ち、pending-approval.md
    参照)、現時点では検証用のInMemory実装を返す。`InMemoryFleetOperatorStore()`はこの呼び出し
    ごとに新規生成されるため、実Cloud Functions環境でも呼び出しをまたいで状態
    (`deletion_confirmation_sent_at`等)が保持されない既知の限界が残る(他エントリポイントと
    同じ限界で、実Firestore接続後に解消される)。
    """
    return {
        "store": InMemoryFleetOperatorStore(),
        "email_sender": _UnconfiguredEmailSender(),
    }


def main(request, *, runtime_dependencies: Optional[dict] = None):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    Cloud Scheduler(日次想定)がHTTPトリガーとして起動する。`request`はいずれのフィールドも
    参照しない(起動自体がトリガーであり、署名検証対象のpayloadを持たない)。

    `runtime_dependencies`省略時は`get_deletion_confirmation_runtime_dependencies()`の戻り値
    (呼び出しごとに新規のInMemory実装)を使うため、実Cloud Functions環境・既存呼び出し元の
    挙動は変わらない。他エントリポイント(フェーズ146・147)と同じ依存注入パターンにより、
    事前に`canceled_at`・emailを登録済みのストアをテスト・簡易ローカルサーバーから注入
    できるようにした。
    """
    now = datetime.now(timezone.utc)
    deps = (
        runtime_dependencies
        if runtime_dependencies is not None
        else get_deletion_confirmation_runtime_dependencies()
    )
    store = deps["store"]
    email_sender = deps["email_sender"]
    candidates = list_deletion_candidates(store, now)
    due = select_due_deletion_candidate_final_confirmations(store, candidates)
    result: SendDeletionCandidateFinalConfirmationsResult = (
        send_deletion_candidate_final_confirmations(store, due, email_sender, now)
    )
    logger.info(
        "deletion_confirmations: candidates=%d due=%d sent=%d unreachable=%d",
        len(candidates),
        len(due),
        len(result.sent),
        len(result.unreachable),
    )
    return "OK", 200


def _demo() -> None:
    class _StubRequest:
        pass

    body, status_code = main(_StubRequest())
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
