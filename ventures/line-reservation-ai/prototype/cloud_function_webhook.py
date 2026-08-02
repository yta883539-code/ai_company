#!/usr/bin/env python3
"""
webhook-async-processing-design.mdで設計した「Cloud Function A: receive_webhook」の
ハンドラロジックを、初めて実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のGCPプロジェクト作成・Cloud Functions/Cloud Tasksのデプロイは「アカウント作成」に
  該当し、引き続きオーナー承認待ち(pending-approval.md参照)。本モジュールはそれとは別に、
  「Aのハンドラが何を判断し、どの引数でCloud Tasksを呼ぶか」というロジック自体を
  実クラウド接続なしで検証可能にしたもの。Cloud Tasksクライアントは`TaskQueueClient`
  プロトコルとして差し替え可能にしてあり(engine.pyのllm_callスタブと同じ考え方)、
  承認後は`InMemoryTaskQueueClient`を実際の`google.cloud.tasks_v2`クライアントに
  差し替えるだけで動作させられるように設計している。
- 実装対象はAのみ(署名検証・イベント構造チェック・Cloud Tasksへのenqueue判断・即時200)。
  Cloud Function B(process_conversation_event、LLM呼び出し〜push送信)は、実LLM呼び出し
  自体がオーナー承認待ちのため引き続き未着手(README.mdの次の課題参照)。

設計の参照元: webhook-async-processing-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol


# ---------------------------------------------------------------------------
# Cloud Tasksクライアントのプロトコル(実クライアントとInMemory版の共通インターフェース)
# ---------------------------------------------------------------------------

class TaskAlreadyExistsError(Exception):
    """同名タスクが既にキューに存在する場合に送出される(Cloud Tasks側の重複排除を模す)。"""


class TaskQueueClient(Protocol):
    def create_task(self, task_name: str, payload: dict) -> None:
        """task_nameが既存であればTaskAlreadyExistsErrorを送出する想定。"""
        ...


class InMemoryTaskQueueClient:
    """Cloud Tasksの決定的タスク名による重複排除を模した検証用クライアント。

    実際のgoogle.cloud.tasks_v2.CloudTasksClient.create_task()は、同名タスクの
    再作成時にAlreadyExists(google.api_core.exceptions.AlreadyExists)を返す。
    ここではその挙動だけを再現する。
    """

    def __init__(self) -> None:
        self.created: dict[str, dict] = {}

    def create_task(self, task_name: str, payload: dict) -> None:
        if task_name in self.created:
            raise TaskAlreadyExistsError(task_name)
        self.created[task_name] = payload


# ---------------------------------------------------------------------------
# タスク名の導出(webhook-async-processing-design.md「二重処理対策」節の結論)
# ---------------------------------------------------------------------------

def make_task_name(webhook_event_id: str) -> str:
    """LINEのwebhookEventId(ULID)からCloud Tasksの決定的タスク名を導出する。

    Cloud Tasksのタスク名は英数字・ハイフン・アンダースコアのみ、500文字以内という
    制約がある。ULID自体が[0-9A-Z]のみで構成されるため変換は不要だが、想定外の
    文字が混入した場合に備えて許可文字のみへの簡易チェックを行う。
    """
    if not webhook_event_id:
        raise ValueError("webhook_event_id must be a non-empty string")
    task_name = f"line-event-{webhook_event_id}"
    if len(task_name) > 500:
        raise ValueError("task_name exceeds Cloud Tasks 500-character limit")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if not set(task_name) <= allowed:
        raise ValueError(f"task_name contains characters unsupported by Cloud Tasks: {task_name!r}")
    return task_name


# ---------------------------------------------------------------------------
# 1イベント単位の処理結果
# ---------------------------------------------------------------------------

@dataclass
class EventHandleResult:
    webhook_event_id: Optional[str]
    enqueued: bool
    reason: str  # "enqueued" | "skipped_redelivery" | "skipped_duplicate_task"


def handle_webhook_event(event: dict, queue_client: TaskQueueClient) -> EventHandleResult:
    """LINEのWebhookイベント1件を処理する(署名検証済み・イベント配列を展開した後の単位)。

    設計上の判断(webhook-async-processing-design.md準拠):
    1. `deliveryContext.isRedelivery`がTrueならCloud Tasksへのenqueue自体を早期スキップする
       (安価な防御層、Cloud Tasks側の重複排除を待たない)。
    2. `webhookEventId`から決定的タスク名を導出しenqueueする。Cloud Tasks側の重複排除で
       同名タスクの二重作成が防がれる(第1の防御層をすり抜けた場合の保険)。
    3. ここではLLM呼び出し・会話フロー処理(Cloud Function B側)は一切行わない。
    """
    webhook_event_id = event.get("webhookEventId")
    if not webhook_event_id:
        raise ValueError("event is missing required field 'webhookEventId'")

    if event.get("deliveryContext", {}).get("isRedelivery"):
        return EventHandleResult(webhook_event_id, enqueued=False, reason="skipped_redelivery")

    task_name = make_task_name(webhook_event_id)
    try:
        queue_client.create_task(task_name, payload=event)
    except TaskAlreadyExistsError:
        return EventHandleResult(webhook_event_id, enqueued=False, reason="skipped_duplicate_task")

    return EventHandleResult(webhook_event_id, enqueued=True, reason="enqueued")


# ---------------------------------------------------------------------------
# Cloud Function Aのエントリポイント本体
# ---------------------------------------------------------------------------

@dataclass
class WebhookReceiverResult:
    status_code: int
    results: list = field(default_factory=list)


def verify_line_signature(body: bytes, signature_header: Optional[str], channel_secret: str) -> bool:
    """X-Line-Signatureの検証(HMAC-SHA256 + Base64、LINE公式ドキュメント準拠のスタブ)。

    実装自体はPython標準ライブラリ(hmac, hashlib, base64)のみで完結し外部認証は不要なため、
    ここでは実装まで行う。channel_secret(チャネルシークレット)の取得自体はLINE公式アカウント
    開設(オーナー承認待ちのアカウント作成)後に得られる値のため、実際の検証はその後に行う。
    """
    import base64
    import hashlib
    import hmac

    if not signature_header:
        return False
    computed = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed_b64 = base64.b64encode(computed).decode("utf-8")
    return hmac.compare_digest(computed_b64, signature_header)


def webhook_receiver(
    body: bytes,
    signature_header: Optional[str],
    channel_secret: str,
    events: list[dict],
    queue_client: TaskQueueClient,
) -> WebhookReceiverResult:
    """Cloud Function Aの本体。LINE Platformへは常にできる限り速やかに200を返す。

    - 署名検証に失敗した場合のみ401相当を返す(この場合はenqueueを一切行わない)。
    - 署名検証後は、個々のイベント処理でエラーが起きても(例: webhookEventId欠落という
      通常発生しないはずの異常系)そのイベントだけスキップし、200自体は返す設計とする
      (LINE側からの不要な再送の連鎖を避けるため。異常はログ出力想定だが、本モジュールの
      責務外のためログ出力先の設計はデプロイ環境確定後の課題として残す)。
    """
    if not verify_line_signature(body, signature_header, channel_secret):
        return WebhookReceiverResult(status_code=401, results=[])

    results = []
    for event in events:
        try:
            results.append(handle_webhook_event(event, queue_client))
        except ValueError:
            continue

    return WebhookReceiverResult(status_code=200, results=results)


def _demo() -> None:
    queue = InMemoryTaskQueueClient()
    channel_secret = "demo-secret"

    import base64
    import hashlib
    import hmac
    import json

    events = [
        {"webhookEventId": "01J8ZC9Q1QK7X3S6VN9R2E4T8P", "type": "message",
         "source": {"userId": "U123"}, "deliveryContext": {"isRedelivery": False}},
        {"webhookEventId": "01J8ZC9Q1QK7X3S6VN9R2E4T8P", "type": "message",
         "source": {"userId": "U123"}, "deliveryContext": {"isRedelivery": False}},
        {"webhookEventId": "01J8ZC9Q2ABCDEF0123456789Z", "type": "message",
         "source": {"userId": "U456"}, "deliveryContext": {"isRedelivery": True}},
    ]
    body = json.dumps({"events": events}).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("utf-8")

    result = webhook_receiver(body, signature, channel_secret, events, queue)
    print(f"status_code={result.status_code}")
    for r in result.results:
        print(f"  webhookEventId={r.webhook_event_id} enqueued={r.enqueued} reason={r.reason}")
    print(f"queued tasks: {list(queue.created.keys())}")

    bad_result = webhook_receiver(body, "invalid-signature", channel_secret, events, queue)
    print(f"invalid signature -> status_code={bad_result.status_code}")


if __name__ == "__main__":
    _demo()
